# Agentic TabCF: Distributional Causal Analysis with TabPFN

[Public source repository](https://github.com/GepingChen/agentic-tabcf-hackathon)
· [Verification record](VERIFICATION.md) · [Licensing](LICENSING.md)

**“If we raise the price, how would sales change?”** Agentic TabCF takes an
analyst's continuous-treatment instrumental-variable question through a reviewed
plan, TabPFN-3.5 computation and an evidence-linked distribution report.

Start with [the offline English cigarette report](reports/cigarette-tabpfn35.html).
Download it and open it in a browser; GitHub's source view does not run HTML.
The report is self-contained and needs no installation, credentials or internet.
It is a **saved genuine TabPFN-3.5 replay**, not a new live execution.

## What each component does

- Gemini proposes roles, units and the requested comparison. The analyst reviews
  and confirms using a dedicated button; Gemini computes no causal numbers.
- TabPFN-3.5 supplies predictive models in both stages of the existing TabCF method.
  Stage 1 models F(X|Z), and TabCF constructs control ranks V. Stage 2 models
  E[Y|X,V] and F(Y|X,V).
- Deterministic code integrates predictions and derives distributions, quantiles,
  user-requested threshold probabilities and contrasts. Reports preserve warnings
  and evidence references. Ordinary follow-ups reuse the completed result.

TabCF predates this entry. The hackathon contribution is the managed 3.5 workflow,
reviewed conversation, reporting and reproducible packaging around that method.
See [PROJECT.md](PROJECT.md) for assumptions and limits, and
[DEMO_SCRIPT.md](DEMO_SCRIPT.md) for an optional short recording.

## Live run — Python 3.11

Run these commands from the repository root:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

Before launch, put your own existing Gemini and Prior Labs API keys in
`~/.config/dcfa/gemini_api_key` and `~/.config/dcfa/tabpfn_api_key`, respectively.
Create the directory if necessary and use your editor to enter the keys.
Keep them outside this repository; do not paste keys into a commit or recording.
Then run:

```bash
chmod 600 ~/.config/dcfa/gemini_api_key ~/.config/dcfa/tabpfn_api_key
.venv/bin/agentic-tabcf
```

Open <http://127.0.0.1:7860>. Set `PORT` if that port is occupied. Alternative
key-file paths use `DCFA_GEMINI_API_KEY_FILE` and `DCFA_TABPFN_TOKEN_FILE`.
Gemini receives conversation and column names; Prior Labs receives selected
Y/X/Z rows. Use only authorized inputs and review the transfer consent.
The entry fixes `api_only` / `v3.5_default`: quota exhaustion stops the analysis.
It does not buy credits or silently switch models.

The dependency lock installs the original accepted wheel pair under `wheels/`.
Readable source is supplied alongside it: the Apache entry under `src/`, and the
retained MIT parent under `vendor/dcfa/`. Entry configuration files come from the
accepted wheel. `parent_commit.txt` identifies the historical parent runtime;
current entry prose does not change that identity. `SOURCE_LAYOUT.md` explains
the export. No local runtime modifications are needed to start the entry.

## Reproduce the example

Upload `examples/cigarette/cigarette_144.csv`, set Advanced seed **20260920**, and
paste the prompt in [examples/cigarette/PROMPTS.md](examples/cigarette/PROMPTS.md).
Include its explicit probability-above-120 sentence to match the saved run.
Review log storage, original price units, 100→120 direction and quartiles before
clicking **Confirm and generate report** once. Textual confirmation does not fit.
A live call consumes provider quota; reading the saved report does not.

`examples/synthetic.csv` is a public generated 128-row fixture: Y is the outcome,
X the continuous treatment and Z the instrument, with no W. It demonstrates
mechanics and is not formal estimator validation.

The original cigarette result and evidence are under
`results/cigarette-35/attempt-1-api/`. The included browser acceptance record
documents the historical run. The larger five-seed comparison remains in the
separate local submission ZIP; it is not included in this focused source export.

## Scope and licensing

The upload interface accepts exactly three numeric columns, 120–256 rows,
continuous outcome/treatment and no baseline covariates W. The analyst must justify
the IV/control-function assumptions. Do not drop research-required covariates
merely to fit the interface. Unsupported requests are rejected. Empirical
diagnostics do not prove instrument validity or identification.

The cigarette example compares aggregate state–year per-capita sales under
maintained assumptions. Income, state/year effects and within-state dependence
remain unresolved. Quantile contrasts describe distributions, not particular
people or groups. All results remain `development_only`; there are no claims of
significance, individual effects, policy benefit or general model superiority.

Root [LICENSE](LICENSE) is Apache-2.0 for the entry and new materials. The
unchanged DCFA parent and TabCF reference code retain MIT; data and model/service
terms remain separate. Read [NOTICE](NOTICE), `PARENT_MIT_LICENSE`,
`TABCF_MIT_LICENSE` and the example's `SOURCE.md` / `GPL-2.0.txt`.
See [LICENSING.md](LICENSING.md) for the component-by-component scope and third-party
attribution. Publishing this repository is separate from accepting contest terms
or submitting an official entry; organizer acceptance is not asserted here.
