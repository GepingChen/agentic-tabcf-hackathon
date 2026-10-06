"""Local CSV callbacks must work without the optional ZeroGPU dependencies."""

import sys

import gradio as gr

from dcfa_website_demo.app import build_app
from dcfa_website_demo.dialogue import CSVConversation
from dcfa_website_demo.gemini import GeminiWebsiteCompilation
from dcfa_website_demo.upload_cleanup import _safe_unlink_upload


def test_cleanup_preserves_files_outside_temp_root(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setenv("GRADIO_TEMP_DIR", str(uploads))
    inside = uploads / "input.csv"
    outside = tmp_path / "private.csv"
    inside.write_text("upload")
    outside.write_text("private")
    link = uploads / "outside-link.csv"
    link.symlink_to(outside)

    for path in (None, str(inside), str(inside), str(outside), str(link)):
        _safe_unlink_upload(path)

    assert not inside.exists()
    assert outside.read_text() == "private"
    assert link.is_symlink()


def test_local_csv_lifecycle_without_spaces(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "spaces", None)
    monkeypatch.setitem(sys.modules, "dcfa_website_demo.zerogpu", None)
    monkeypatch.setenv("GRADIO_TEMP_DIR", str(tmp_path))
    calls = []
    trace = {
        "confirmed_roles": {
            role: {"column": column, "column_position": index + 1, "definition": "Test role"}
            for index, (role, column) in enumerate(
                zip(("outcome", "treatment", "instrument"), ("Y", "X", "Z"), strict=True)
            )
        }
    }
    compilation = GeminiWebsiteCompilation("Y", "X", "Z", "mean", "center", None, None, trace)

    def execute(*args, **kwargs):
        calls.append(1)
        return tuple(gr.update(value="Callback fixture") for _ in range(9))

    monkeypatch.setattr(
        "dcfa_website_demo.local_dialogue.local_handlers",
        lambda **kwargs: (
            lambda profile: None,
            lambda *args: ("Review plan", compilation),
            execute,
        ),
    )
    app = build_app(
        local_csv_dialogue=True, fixed_analysis_mode="api_only", output_root=tmp_path / "results"
    )
    functions = {fn.fn.__name__: fn.fn for fn in app.fns.values() if fn.fn}
    session = CSVConversation()
    functions["reset_session"](session)
    path = tmp_path / "input.csv"
    path.write_text("Y,X,Z\n" + "".join(f"{i},{i + 1},{i + 2}\n" for i in range(128)))
    functions["invalidate"](session, str(path), "", "", "", True)
    functions["local_talk"](
        session, str(path), "", "", "", "", True, "Y, X, Z. Mean at center.", "api_only"
    )
    functions["local_talk"](session, str(path), "", "", "", "", True, "Confirm", "api_only")
    assert calls == []
    list(
        functions["local_generate"](
            session, str(path), "", "", "", True, 20260920, session.revision, "api_only"
        )
    )
    assert calls == [1]
    assert session.status == "completed"
    assert session.validated is None
    assert not path.exists()
    functions["reset_session"](session)
