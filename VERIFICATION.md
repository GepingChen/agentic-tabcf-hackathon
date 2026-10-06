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
