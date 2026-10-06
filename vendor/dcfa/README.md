<h1 align="center">Agentic TabCF</h1>

<p align="center">
  <strong>An auditable causal agent for continuous-treatment distributional IV analysis</strong>
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2605.05993"><img src="https://img.shields.io/badge/arXiv-2605.05993-b31b1b.svg" alt="arXiv:2605.05993"></a>
  <a href="https://github.com/GepingChen/TabCF"><img src="https://img.shields.io/badge/Method-TabCF-2563eb.svg" alt="TabCF method"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-0f766e.svg" alt="Python 3.11+">
</p>

<p align="center">
  <a href="https://huggingface.co/spaces/GPChen01/dcfa-zerogpu"><strong>Live ZeroGPU demo</strong></a>
  ·
  <a href="https://gepingchen.github.io/projects/dcfa/"><strong>Prepared demo</strong></a>
  ·
  <a href="https://colab.research.google.com/github/GepingChen/DCFA/blob/main/notebooks/DCFA_Custom_Analysis_Colab.ipynb"><strong>Open in Colab</strong></a>
  ·
  <a href="https://arxiv.org/abs/2605.05993"><strong>Read the paper</strong></a>
</p>

**Agentic TabCF** is the agentic system hosted in the `DCFA` repository and
implemented as the `dcfa` package. It builds on the method introduced in our
arXiv paper,
**[TabCF: Distributional Control Function Estimation with Tabular Foundation
Models](https://arxiv.org/abs/2605.05993)**. The paper introduces TabCF for
distributional control-function estimation; this repository adds a bounded agent
layer that compiles natural-language questions, runs deterministic causal tools,
checks diagnostics and support, and binds every displayed number to verifiable
evidence.

> **LLMs compile intent. Deterministic tools compute. Evidence gates decide what
> can be shown.**

<p align="center">
  <a href="plots/tabcf_agent_overview_4k.png">
    <img src="plots/tabcf_agent_overview_editable.svg" alt="Agentic TabCF architecture: bounded language compilation, explicit agent runtime, deterministic TabCF-IV engine, evidence validation, and visitor or audit outputs" width="100%">
  </a>
</p>

<p align="center"><sub>Click the architecture figure to open the 4K version. The editable SVG and deterministic generator are in <a href="plots/">plots/</a>.</sub></p>

## Why Agentic TabCF?

Many causal-agent demos blur together language-model reasoning, statistical
estimation, and presentation. Agentic TabCF keeps those responsibilities separate:

1. **A bounded compiler** turns a natural-language request into an immutable,
   typed analysis specification. For an uploaded CSV, Gemini sees the question or conversation,
   three header names, optional role overrides, and symbolic treatment labels—not
   data rows or actual intervention values.
2. **An explicit runtime** validates roles, state transitions, approvals, and
   failures. Unsupported requests fail closed instead of silently changing the
   estimand or model.
3. **Deterministic TabCF-IV tools** perform every numerical calculation, from
   control-function construction to interventional distributions, means,
   quantiles, risks, and directed contrasts.
4. **An evidence and audit layer** binds results to data and specification hashes,
   versions, support status, warnings, unrounded values, and source artifacts.
   An independent verifier checks the saved bundle without refitting.

## Supported analysis

The public workflow intentionally supports one causal design:

| Role | v1 contract |
|---|---|
| Outcome `Y` | One continuous outcome |
| Treatment `X` | One continuous treatment |
| Instrument `Z` | One scalar instrument |
| Baseline covariates `W` | None; non-empty `W` is rejected before Stage 1 |

Within that scope, the agent can return interventional means, medians and other
quantiles, threshold risks, and directed contrasts. It preserves weak-IV and
support warnings, blocks interventions outside joint support before Stage 2, and
serves ordinary follow-ups from a validated cache rather than refitting.

It is **not** a general causal-method router, an IV-discovery system, an
invalid-instrument repair tool, or an autonomous policy-deployment system.
Empirical diagnostics do not prove instrument validity or identification.

## Try the project

Choose the path that matches what you want to inspect:

| Path | What happens | Providers and data boundary |
|---|---|---|
| **[Live ZeroGPU demo](https://huggingface.co/spaces/GPChen01/dcfa-zerogpu)** | Opens a saved real cigarette report immediately; also runs authenticated presets or a bounded Y/X/Z CSV with 3.5 API and quota-only v2 backup | Viewing the saved example needs no login, API key or GPU; live CSV uses Gemini; development-only |
| **[Prepared demo](https://gepingchen.github.io/projects/dcfa/)** | Replays one hash-bound, independently verified synthetic result | Static GitHub Pages; no provider call at view time |
| **[Colab workflow](https://colab.research.google.com/github/GepingChen/DCFA/blob/main/notebooks/DCFA_Custom_Analysis_Colab.ipynb)** | Runs one bounded custom CSV analysis in your own ephemeral runtime | Your question goes to Google; only separately authorized Y/X/Z rows and prediction grids go to Prior Labs |
| **Local operator demo** | Runs the guided Gradio workflow and preserves full audit artifacts | Uses your repository-external Gemini and TabPFN Client credentials |

### Space CSV conversation (repository implementation)

Upload a permitted three-column CSV, authorize processing, and describe the analysis.
Use **Send message** to answer any missing-role or objective questions. The review card
shows X/Y/Z column names, original one-based column positions, user-provided meanings
(or “Not provided”), and the directed analysis objective. You can correct it through
another message or the optional role overrides. Only **Confirm and generate report**
starts the default API-first analysis; typing confirmation in chat never executes the analysis.

The temporary Gemini key stays in the current page's password field between turns;
it is cleared when generation starts, on reset, or after 15 idle minutes. Duplicate
Spaces still use their owner's Secret. Each turn sends conversation text, headers,
and overrides to Gemini, never CSV rows or actual intervention values. Do not put
credentials, sensitive data, or data rows into the conversation. There is one
provider request per submitted turn, no automatic retry, and no fixed mandatory
number of turns. Invalid replies retain the completed conversation for correction.

The final report view includes the reviewed plan; the ZIP includes its
`confirmed_plan.html` appendix and the final role definitions/request count in
`gemini_compilation.json`, without exporting the full conversation. Reset to start
another analysis; report follow-up chat is not included.

The ZeroGPU, Colab, and local managed-service paths are `development_only`. Provider
availability, quotas, charges, and Colab resources are not guaranteed. Do not use
sensitive, confidential, personally identifiable, or otherwise unshareable data.

### Local setup

The local analysis UI (`dcfa-ui`, alias `dcfa-website-demo`) defaults to
**3.5 API first with quota-only v2 fallback**. The **Analysis mode** selector also
offers **3.5 API only** (stop on exhaustion) and **TabPFN v2 only** (direct CUDA v2).
Changing mode updates the data recipients and clears the previous CSV consent;
confirm the selected policy before running. The mode is disabled during execution,
and an authorized fallback does not ask again. Results state the selected policy,
the actual model and whether a switch occurred. The managed profile uses one
estimator, Thinking off and `v3.5_default`. Review the data recipients before confirming: rows go to Prior
Labs for 3.5 and to Hugging Face for remote v2. On the Space, v2 runs in the same
ZeroGPU runtime. Confirmed exhaustion starts a fresh v2 analysis; ordinary rate
limits, authentication failures and other errors never change models.

Install `requirements-website-demo.lock`, provide the external credentials below,
and run `.venv/bin/dcfa-ui`. The default remote v2 target is
`GPChen01/dcfa-zerogpu`. The page checks endpoint availability before execution.
The Space owner supplies `DCFA_TABPFN_API_KEY` through Hugging Face Secrets;
visitors do not enter a statistical model key. The Space source uses the same
selector and its in-process GPU runner, but this selector update has not been
deployed; the existing live Space still uses API-first automatically. See
[daily policy and v2 configuration](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/docs/WEBSITE_DEMO.md#daily-analysis-policy).
`dcfa-dev-ui` and `tabcf-demo` remain explicit sklearn mechanics demonstrations;
research entrypoints and previously saved results do not automatically migrate.


For everyday core development, you can reuse an existing compatible Conda
environment without creating `.venv` or installing DCFA into that environment.
See [shared local environments](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/docs/LOCAL_ENVIRONMENTS.md) for commands,
compatibility limits, and the distinction from the pinned setup below.

Clone the pinned TabCF submodule and install the core development environment:

```bash
git clone --recurse-submodules https://github.com/GepingChen/DCFA.git
cd DCFA
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -e . --no-deps
```

Run a credential-free mechanics demo:

```bash
.venv/bin/dcfa tabcf-demo \
  --scenario strong_iv \
  --output-dir artifacts/local/tabcf-strong-v1
```

This command explicitly uses the local
`sklearn_quantile_fallback`. Its output is `development_only`, is **not a TabCF
result**, and cannot enter locked Track T evidence.

To run the default TabPFN-3.5 API workflow, install the combined environment and place both
credentials outside the repository:

```bash
.venv/bin/python -m pip install -r requirements-website-demo.lock
.venv/bin/python -m pip install -e . --no-deps
chmod 600 ~/.config/dcfa/gemini_api_key
chmod 600 ~/.config/dcfa/tabpfn_api_key
.venv/bin/dcfa-ui
```

Open `http://127.0.0.1:7860`. See
[`docs/WEBSITE_DEMO.md`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/docs/WEBSITE_DEMO.md) for credential setup, readiness
checks, Docker/Compose operation, transfer boundaries, and failure semantics.

## Architecture at a glance

```text
natural-language question + Y/X/Z data
  -> bounded language compiler
  -> immutable typed specification
  -> explicit agent state machine
  -> input, role, backend, diagnostic, and joint-support gates
  -> Stage 1: estimate F(X | Z) and construct control rank V
  -> Stage 2: estimate E[Y | X,V] and F(Y | X,V)
  -> deterministic integration over V
  -> canonical validated result bundle
  -> evidence ledger + audit trail + independent verifier
  -> visitor-safe answer and operator audit artifacts
```

The upstream statistical core remains pinned in
[`third_party/TabCF`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/third_party/TabCF). DCFA wraps its inspected interfaces; it
does not rewrite the TabCF core or invent support for baseline covariates.

## Evidence tracks

The repository separates three questions that must not be merged into one claim:

| Track | Question | Current evidence boundary |
|---|---|---|
| **T — estimator** | How does TabCF recover continuous-treatment interventional distributions? | Local fallback and managed-client runs test mechanics only; locked TabCF evidence still requires a reproducible checkpoint- and image-hashed runtime |
| **H — decision** | How should a frozen three-action policy be evaluated? | Implemented on generated and semi-synthetic fixtures; no approved real Hillstrom run is claimed |
| **A — agent** | Does explicit agent orchestration improve workflow reliability when tools are held fixed? | A 24-case × 5-run recorded-tool benchmark is implemented; it is not a paired live-LLM comparison |

Hillstrom is an isolated randomized-policy evaluation environment. It is **not a
TabCF validation dataset**, is never encoded as a continuous-treatment problem,
and is not exposed through the public Agentic TabCF workflow.

## What is implemented

- immutable typed specifications, schemas, errors, evidence, audit, and cache;
- a deterministic no-`W` TabCF-IV vertical slice with strict support gates;
- explicit local, managed-client, and locked-runtime backend contracts with no
  silent fallback;
- a bounded Gemini compiler and explicit agent state machine;
- a visitor-safe Gradio projection plus full machine-audit artifacts;
- a hash-bound static replay and a pinned, output-free Colab notebook;
- an isolated Hillstrom policy-value adapter with freeze-before-test leakage
  gates and DR/IPW/direct estimators;
- a recorded Track A benchmark with identical tools and fixtures;
- independent artifact verification that never refits a model.

For the exact protocol versions, verified artifacts, and external blockers, see
[`docs/IMPLEMENTATION_STATUS.md`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/docs/IMPLEMENTATION_STATUS.md).

## Repository map

| Path | Purpose |
|---|---|
| [`src/dcfa/`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/src/dcfa/) | Shared contracts, evidence, CLI, runtime, TabCF-IV, and Hillstrom adapters |
| [`src/dcfa_website_demo/`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/src/dcfa_website_demo/) | Bounded Gemini + managed TabPFN presentation workflow |
| [`src/dcfa_showcase/`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/src/dcfa_showcase/) | Static prepared-replay freeze and verifier |
| [`src/dcfa_colab/`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/src/dcfa_colab/) | Secret-scoped Colab adapter |
| [`evaluation/`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/evaluation/) | Frozen benchmark cases and provider profiles |
| [`showcase/prepared_demo_v1/`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/showcase/prepared_demo_v1/) | Public-safe verified replay bundle |
| [`notebooks/`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/notebooks/) | Pinned custom-analysis Colab workflow |
| [`tests/`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/tests/) | Unit, statistical, leakage, agent-behavior, and integration gates |
| [`plots/`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/plots/) | Architecture figure, 4K export, and deterministic generator |
| [`third_party/TabCF`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/third_party/TabCF) | Pinned upstream TabCF source |

For deeper orientation, read the
[`architecture`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/docs/ARCHITECTURE.md),
[`identification boundaries`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/docs/IDENTIFICATION_BOUNDARIES.md),
[`codebase map`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/docs/CODEBASE_MAP.md), and
[`decision log`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/docs/DECISIONS.md).

## Verification

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/python -m pytest
.venv/bin/dcfa --help
python -m dcfa_showcase verify showcase/prepared_demo_v1
git diff --check
```

A smoke test proves mechanics only. It does not establish statistical quality,
coverage, identification, policy improvement, or release readiness. Generated
outputs are immutable and belong under ignored `artifacts/local/` paths; use a
fresh versioned destination for every run.

## License

Project-authored software code is available under the [MIT License](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/LICENSE)
(copyright 2026 Geping Chen). The pinned [`third_party/TabCF`](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/third_party/TabCF)
submodule retains its [own MIT license](https://github.com/GepingChen/TabCF/blob/main/LICENSE)
and attribution.

The [cigarette-demand example](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/examples/cigarette_demand_small/README.md) includes
a prepared extract from `Ecdat::Cigarette`. Its [source and attribution notes](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/examples/cigarette_demand_small/SOURCE.md)
and [GPL-2.0 text](https://github.com/GepingChen/DCFA/blob/88d68314bf1e99943753f899f30ec2a547c7eed1/examples/cigarette_demand_small/GPL-2.0.txt) accompany the
source package terms. The package metadata does not establish a separate
license for the original observations; this repository's MIT license does not
relicense those data rows.

## Citation

If this project or the underlying method is useful in your work, please cite the
TabCF paper:

```bibtex
@article{chen2026tabcf,
  title   = {TabCF: Distributional Control Function Estimation with Tabular Foundation Models},
  author  = {Chen, Geping and Li, Chunlin and Yang, Tianzhong and Zhu, Zhengyuan and Zhou, Jing},
  journal = {arXiv preprint arXiv:2605.05993},
  year    = {2026}
}
```

TabCF method and paper code: <https://github.com/GepingChen/TabCF>
