"""Local credential-file adapters for the existing reviewed CSV conversation."""

from pathlib import Path

from dcfa_website_demo.dialogue import compile_csv_turn


def local_handlers(*, output_root: Path, fixed_analysis_mode: str | None = None):
    from dcfa_website_demo.app import (
        WebsiteFinalizationError,
        execute_prepared_local_csv,
        format_portfolio_result,
        gemini_api_key_file_from_environment,
        portfolio_ui_updates,
    )
    from dcfa_website_demo.daily import archive_daily_result, execute_daily_dataset

    def authorize(profile):
        # This adapter is only bound by the loopback local entry, never by a Space.
        del profile

    def chat(history, columns, overrides, credential, on_request):
        del credential
        return compile_csv_turn(
            history,
            columns,
            overrides,
            api_key_file=gemini_api_key_file_from_environment(),
            on_request=on_request,
        )

    def execute(validated, compilation, seed, profile, *, analysis_mode):
        del profile
        if fixed_analysis_mode and analysis_mode != fixed_analysis_mode:
            raise ValueError("This entry point uses a fixed model policy.")
        result = execute_prepared_local_csv(
            validated,
            compilation,
            seed,
            model_path=Path("unused"),
            output_root=output_root,
            dataset_executor=lambda kwargs: execute_daily_dataset(
                mode=analysis_mode,
                compiled_kwargs=kwargs,
                managed_settings={},
            ),
        )
        try:
            from dcfa_website_demo.dialogue import plan_html

            if result.output_dir is not None:
                (result.output_dir / "confirmed_plan.html").write_text(plan_html(compilation))
            return portfolio_ui_updates(
                format_portfolio_result(result),
                buttons_enabled=True,
                archive_path=archive_daily_result(result),
            )
        except Exception as exc:
            raise WebsiteFinalizationError(
                "Report finalization failed; no refit was attempted."
            ) from exc

    return authorize, chat, execute
