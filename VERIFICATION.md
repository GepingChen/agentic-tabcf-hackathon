# Publication verification — 2026-10-06

This repository publishes a development prototype and a saved genuine TabPFN-3.5
example. It does not promote a final statistical result or submit a contest entry.

- Re-ran the complete original parent test suite at `parent_commit.txt`:
  **274 passed**, 25 dependency/OAuth warnings, 143.30 seconds. The source was
  exported from the historical accepted package, with its original tests and
  fixtures, and run using `PYTHONPATH=src .../python -m pytest -q`. The first test
  environment lacked `spaces`; the existing development environment supplied it.
  The full completed run passed without altering the runtime or tests.
- Compared the public Python source/config/package assets to the original wheel
  contents: **71 members unchanged**. Original wheel files, dependency lock,
  data bytes and bound saved-result files were preserved.
- Independently verified the shipped cigarette result with the original source:
  **valid**, 656 evidence records, `TabPFN v3.5_default`, `development_only`, run
  `run_72e0e4a81aac75e7a91f3dbd`, bundle `bundle_1ad75ce59ff0d82cc0aaa651`.
- Started the fixed entry using FastAPI's TestClient: `/healthz` returned `ok`,
  `api_only` was the only supported mode, and the model was `v3.5_default`.
- Reviewed candidate Git files and embedded wheel members for credential patterns,
  local user paths, logs and caches. No matching secret/user path was found; logs
  and caches were excluded. This is scoped inspection, not a security proof.
- Current entry/documentation links resolve. Links inside historical bound package
  assets remain historical; their bytes were preserved to retain verification.
- The offline HTML was previously checked in a browser, including its result-to-
  evidence link. Its bytes are unchanged. The source export was also previously
  rebuilt into both wheels. No new provider execution was needed for publication.

To verify the saved example after installing the dependency lock, run from this
repository root:

```bash
.venv/bin/python -m dcfa.cli verify-artifacts results/cigarette-35/attempt-1-api
```

The full original tests are available from the parent source revision identified
in `parent_commit.txt`; the focused export contains the installable source rather
than the parent's unrelated experiments and fixtures. Local test logs remain
outside the public Git history. Historical `analysis_report.md` keeps its original
trailing space to preserve the existing artifact bytes; source/docs whitespace
checks are separate from this retained result.

## Local upload-cleanup correction — 0.1.1

The original dependency lock omitted the optional `spaces` package, but local CSV
cleanup imported the ZeroGPU wrapper. This made reset, upload invalidation and
post-analysis cleanup fail in a clean API-only installation. The historical full
suite above used an environment containing `spaces`, so it did not reveal this
packaging defect.

The shared upload-deletion helper now lives in a standard-library-only module.
Local and ZeroGPU callers share it, retaining resolved-path containment within
`GRADIO_TEMP_DIR`, missing-file handling and the existing ZeroGPU helper name.
The 0.1.1 wheels and lock include this correction; original wheels/results remain.

Verified on 2026-10-06:

- Parent targeted checks: `test_local_upload_cleanup.py` and
  `test_local_submission.py`, **4 passed**.
- Built both 0.1.1 wheels from the public source; their 77 source/config/asset
  members match the published source bytes.
- Installed `requirements.lock` into a new Python 3.11 venv. Both entry and DCFA
  report version **0.1.1**; `spaces` is absent; `pip check` passes.
- Ran the installed-wheel regression checks:
  `python -m pytest -q tests/test_local_upload_cleanup.py`, **2 passed**. They
  cover reset, upload invalidation, button-only execution, post-analysis cleanup
  and preservation of outside-root files/symlink targets. Provider responses and
  numerical execution are fixtures; these are lifecycle checks, not model evidence.
- Launched the installed `agentic-tabcf` command; `/healthz` returned `ok`, version
  0.1.1 and API-only mode. In a browser, entered text and clicked Reset conversation:
  the input cleared and no Error appeared. The service log contained no traceback.
- Changed Python files pass Ruff lint/format checks; source/docs diff checks pass.

No new Gemini/TabPFN request, statistical result promotion, Space deployment or
official contest submission was performed for this UI cleanup correction.
