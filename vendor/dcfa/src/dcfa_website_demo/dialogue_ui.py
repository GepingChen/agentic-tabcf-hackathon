"""Gradio bindings for the Space's pre-report CSV conversation."""

from __future__ import annotations

import html
import time
from typing import Any

import gradio as gr

from dcfa.errors import DCFAError, ErrorCode
from dcfa_website_demo.dialogue import SESSION_SECONDS, CSVConversation, prepare_turn


def bind_csv_dialogue(
    *,
    app: Any,
    authorize: Any,
    chat_handler: Any,
    execute_handler: Any,
    components: tuple[Any, ...],
    result_outputs: tuple[Any, ...],
    temporary_key_enabled: bool,
    analysis_mode: Any,
    policy_notice: Any,
    local_session: bool = False,
    fixed_analysis_mode: str | None = None,
) -> None:
    (
        upload,
        key,
        outcome,
        treatment,
        instrument,
        consent,
        message,
        seed,
        send,
        chat,
        plan,
        notice,
        confirm,
        reset,
    ) = components
    state = gr.State(value=None, time_to_live=SESSION_SECONDS, delete_callback=cleanup_session)
    app.load(fn=lambda: CSVConversation(), outputs=state, api_name=False)
    timer = gr.Timer(15)
    revision = gr.Number(value=0, visible=False, precision=0)
    controls = (
        upload,
        outcome,
        treatment,
        instrument,
        consent,
        message,
        seed,
        send,
        reset,
        analysis_mode,
    )
    outputs = (state, chat, plan, notice, confirm, key, *controls, revision)

    def projection(
        session,
        text="",
        *,
        clear_key=False,
        clear_message=False,
        clear_file=False,
        clear_consent=False,
    ):
        interactive = not session.busy and session.status != "completed"
        updates = [gr.update(interactive=interactive) for _ in controls]
        updates[8] = gr.update(interactive=not session.busy)
        updates[9] = gr.update(interactive=not session.busy)
        if clear_consent:
            updates[4] = gr.update(value=False, interactive=interactive)
        updates[7] = gr.update(
            interactive=interactive,
            variant="secondary" if session.status == "ready" else "primary",
        )
        if session.cached_answer and not session.busy:
            updates[5] = gr.update(interactive=True)
            updates[7] = gr.update(interactive=True)
        if clear_message:
            updates[5] = gr.update(value="", interactive=interactive or bool(session.cached_answer))
        if clear_file:
            updates[0] = gr.update(value=None, interactive=interactive)
        from dcfa_website_demo.daily import MODE_CHOICES

        policy_label = dict((value, label) for label, value in MODE_CHOICES)[session.analysis_mode]
        card = session.plan_html
        if card:
            card += "<p><strong>Analysis policy:</strong> " + html.escape(policy_label) + "</p>"
        return (
            session,
            gr.update(value=session.history, visible=bool(session.history)),
            card,
            text,
            gr.update(
                interactive=session.status == "ready" and not session.busy,
                visible=session.status == "ready" or session.busy,
            ),
            gr.update(
                **({"value": ""} if clear_key else {}),
                interactive=temporary_key_enabled and interactive,
            ),
            *updates,
            session.revision,
        )

    def check_owner(session, profile):
        authorize(profile)
        owner = getattr(profile, "username", None)
        if session.owner is not None and session.owner != owner:
            raise ValueError("The signed-in account changed. Reset this conversation.")
        session.owner = owner

    def talk(
        session,
        path,
        credential,
        y,
        x,
        z,
        approved,
        text,
        profile: gr.OAuthProfile | None = None,
        selected_mode="api_preferred",
    ):
        session = session or CSVConversation()
        try:
            check_owner(session, profile)
            if credential and credential in text:
                raise ValueError("Keep the API key in the password field, not the conversation.")
            if session.status == "completed" and session.cached_answer:
                if session.expired():
                    session.cached_answer = None
                    raise ValueError("This conversation expired. Reset to start again.")
                session.history = [
                    {"role": "user", "content": text},
                    {
                        "role": "assistant",
                        "content": "Cached report; no refit or provider request. Reset for a "
                        "different analysis.\n\n" + session.cached_answer,
                    },
                ]
                session.touched = time.monotonic()
                return projection(session, clear_message=True, clear_key=True)
            if chat_handler is None:
                raise ValueError("The Space dialogue provider is unavailable.")
            from dcfa_website_demo.daily import AnalysisMode

            if fixed_analysis_mode and selected_mode != fixed_analysis_mode:
                raise ValueError("This entry point uses a fixed model policy.")
            session.analysis_mode = AnalysisMode(selected_mode).value
            prepare_turn(
                session,
                path,
                text,
                {"outcome": y, "treatment": x, "instrument": z},
                approved,
                lambda history, columns, overrides: chat_handler(
                    history,
                    columns,
                    overrides,
                    credential,
                    session.count_request,
                ),
            )
            return projection(session, clear_message=True)
        except (DCFAError, ValueError, OSError) as exc:
            return projection(session, str(exc))

    def generate(
        session,
        path,
        y,
        x,
        z,
        approved,
        selected_seed,
        reviewed_revision,
        profile: gr.OAuthProfile | None = None,
        selected_mode="api_preferred",
    ):
        session = session or CSVConversation()
        claimed = False
        try:
            check_owner(session, profile)
            if not approved:
                raise ValueError("Confirm data authorization before generating the report.")
            if path != session.upload_path or session.overrides != {
                "outcome": y,
                "treatment": x,
                "instrument": z,
            }:
                raise ValueError("Inputs changed. Send a message to prepare the updated plan.")
            if reviewed_revision != session.revision:
                raise ValueError("The plan changed. Review the current card before confirming.")
            if selected_mode != session.analysis_mode:
                raise ValueError("The model policy changed. Review and authorize it again.")
            session.claim(ready=True)
            claimed = True
            from dcfa_website_demo.app import _running_outputs, portfolio_ui_updates

            # Clear the browser credential before allocating a GPU. The execution uses no key.
            yield (
                *projection(session, "Generating report…", clear_key=True),
                *portfolio_ui_updates(_running_outputs(), buttons_enabled=False)[:6],
            )
            result = execute_handler(
                session.validated,
                session.compilation,
                selected_seed,
                profile,
                analysis_mode=session.analysis_mode,
            )
            if session.compilation.distribution is not None and result[0].get("value"):
                session.cached_answer = result[0]["value"] + "\n\n" + (result[3].get("value") or "")
            session.status = "completed"
            session.release()
            cleanup_session(session)
            yield (
                *projection(
                    session,
                    "Analysis finished. Review the result, or reset to start another analysis.",
                    clear_key=True,
                    clear_file=True,
                ),
                *result[:6],
            )
        except (DCFAError, ValueError, OSError, RuntimeError, TypeError) as exc:
            result_updates = tuple(gr.skip() for _ in result_outputs[:6])
            if claimed:
                from dcfa_website_demo.app import WebsiteFinalizationError

                terminal = isinstance(exc, WebsiteFinalizationError)
                session.status = "completed" if terminal else "ready"
                if terminal:
                    cleanup_session(session)
                session.release()
                from dcfa_website_demo.app import _execution_error_outputs

                error = (
                    exc
                    if isinstance(exc, DCFAError)
                    else DCFAError(
                        ErrorCode.BACKEND_LOAD_FAILED, str(exc), stage="website_demo.csv_execution"
                    )
                )
                result_updates = portfolio_ui_updates(
                    _execution_error_outputs(error), buttons_enabled=True
                )[:6]
            yield (
                *projection(
                    session,
                    str(exc),
                    clear_key=claimed,
                    clear_file=claimed and session.status == "completed",
                ),
                *result_updates,
            )

    def reset_session(session):
        session = session or CSVConversation()
        if session.busy:
            return projection(session, "Wait for the current request to finish.")
        cleanup_session(session)
        return projection(
            CSVConversation(revision=session.revision + 1, analysis_mode=session.analysis_mode),
            clear_key=True,
            clear_message=True,
            clear_file=True,
        )

    def invalidate(session, path, y, x, z, approved):
        session = session or CSVConversation()
        if session.busy:
            return tuple(gr.skip() for _ in outputs)
        changed_file = path != session.upload_path
        if changed_file:
            cleanup_session(session)
            session = CSVConversation(
                upload_path=path, revision=session.revision + 1, analysis_mode=session.analysis_mode
            )
        else:
            session.revision += 1
            session.compilation = None
            session.plan_html = ""
            session.status = "collecting"
            session.touched = time.monotonic()
        session.overrides = {"outcome": y, "treatment": x, "instrument": z}
        return projection(
            session, "Send a message to prepare the current inputs.", clear_key=changed_file
        )

    def expire(session):
        if session is not None and not session.expired():
            return tuple(gr.skip() for _ in outputs)
        cleanup_session(session)
        return projection(
            CSVConversation(
                revision=session.revision + 1 if session else 0,
                analysis_mode=session.analysis_mode if session else "api_preferred",
            ),
            "Conversation expired after 15 idle minutes.",
            clear_key=True,
            clear_message=True,
            clear_file=True,
        )

    def local_talk(session, path, credential, y, x, z, approved, text, selected_mode):
        return talk(session, path, credential, y, x, z, approved, text, None, selected_mode)

    def local_generate(session, path, y, x, z, approved, selected_seed, revision, selected_mode):
        yield from generate(
            session, path, y, x, z, approved, selected_seed, revision, None, selected_mode
        )

    event_args = dict(
        fn=local_talk if local_session else talk,
        inputs=(
            state,
            upload,
            key,
            outcome,
            treatment,
            instrument,
            consent,
            message,
            analysis_mode,
        ),
        outputs=outputs,
        api_name=False,
        trigger_mode="once",
        concurrency_id="csv-dialogue",
    )

    def show_talking():
        return (
            *((gr.update(interactive=False),) * (2 + len(controls))),
            "Preparing your analysis plan with Gemini… Please wait. "
            "No statistical analysis is running yet. "
            "Controls will return when the request finishes.",
        )

    for submit in (send.click, message.submit):
        submit(
            fn=show_talking,
            inputs=None,
            outputs=(confirm, key, *controls, notice),
            queue=False,
            api_name=False,
        ).success(**event_args)
    confirm.click(
        fn=local_generate if local_session else generate,
        inputs=(
            state,
            upload,
            outcome,
            treatment,
            instrument,
            consent,
            seed,
            revision,
            analysis_mode,
        ),
        outputs=(*outputs, *result_outputs[:6]),
        api_name=False,
        trigger_mode="once",
        concurrency_id="csv-dialogue",
        show_progress="hidden",
    ).success(
        fn=None,
        js="() => { document.getElementById('analysis-results')?.scrollIntoView("
        "{behavior: 'smooth', block: 'start'}); }",
        api_name=False,
    )
    reset.click(
        fn=reset_session,
        inputs=state,
        outputs=outputs,
        api_name=False,
        concurrency_id="csv-dialogue",
    ).success(
        fn=lambda: tuple(gr.update(value=None, visible=False) for _ in range(6)),
        outputs=result_outputs[:6],
        api_name=False,
    )

    def file_changed(session, path, y, x, z, approved):
        session = session or CSVConversation()
        if path == session.upload_path or (session.status == "completed" and path is None):
            return tuple(gr.skip() for _ in outputs)
        return invalidate(session, path, y, x, z, approved)

    upload.change(
        fn=file_changed,
        inputs=(state, upload, outcome, treatment, instrument, consent),
        outputs=outputs,
        api_name=False,
        concurrency_id="csv-dialogue",
    )
    chat.clear(
        fn=reset_session,
        inputs=state,
        outputs=outputs,
        api_name=False,
        concurrency_id="csv-dialogue",
    )
    for control in (outcome, treatment, instrument, consent):
        control.input(
            fn=invalidate,
            inputs=(state, upload, outcome, treatment, instrument, consent),
            outputs=outputs,
            api_name=False,
            concurrency_id="csv-dialogue",
        )

    def change_dialogue_mode(session, selected_mode):
        from dcfa_website_demo.daily import AnalysisMode, transfer_notice

        session = session or CSVConversation()
        if session.busy:
            return (*[gr.skip() for _ in outputs], gr.skip())
        selected_mode = AnalysisMode(selected_mode).value
        # A completed report keeps its original policy and cached numerical identity.
        if session.status != "completed":
            session.analysis_mode = selected_mode
            session.revision += 1
        return (
            *projection(
                session,
                "Review the selected policy and authorize data use again.",
                clear_consent=True,
            ),
            transfer_notice(
                selected_mode, v2_location=None if local_session else "this Hugging Face Space"
            ),
        )

    analysis_mode.input(
        change_dialogue_mode,
        inputs=(state, analysis_mode),
        outputs=(*outputs, policy_notice),
        api_name=False,
        concurrency_id="csv-dialogue",
    )
    # Keep expiry reporting separate from gr.State TTL so the page also clears its password field.
    timer.tick(fn=expire, inputs=state, outputs=outputs, api_name=False, queue=False)

    def touch(session):
        session = session or CSVConversation()
        session.touched = time.monotonic()
        return session

    for control in (message, key, seed):
        control.input(
            fn=touch, inputs=state, outputs=state, api_name=False, concurrency_id="csv-dialogue"
        )


def cleanup_session(session: CSVConversation) -> None:
    from dcfa_website_demo.zerogpu import _safe_unlink_upload

    if session is None:
        return
    _safe_unlink_upload(session.upload_path)
    session.validated = None
