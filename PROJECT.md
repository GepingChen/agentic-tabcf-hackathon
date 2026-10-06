# Project description

**Start with the [offline English example report](reports/cigarette-tabpfn35.html):**
download the HTML and double-click it, or open it with your browser's File menu.
No installation, API key, service or internet connection is needed. This is a
presentation of the saved v3 TabPFN-3.5 cigarette run, with expandable evidence;
it is not a new analysis. The focused source export includes this report and current documentation.
The separate local v6 ZIP retains the larger historical measurement package.

**“If we raise the price, how would sales change?”** Answering this requires more
than predicting sales from observed prices. For example, demand can affect both
price and sales, so their correlation need not measure the effect of a price
change. Agentic TabCF is a reviewed analysis workflow for analysts with an
appropriate instrumental-variable research design. It carries their question
through a checkable plan, statistical computation and a traceable report.

## Why look beyond an average?

Two outcome distributions can have the same average and still differ near their
lower or upper ends. Analysts may want to compare the 25th, 50th and 75th
percentiles, or ask how the probability of exceeding a specified sales threshold
changes between two prices. The threshold comes from the user's question; it is
not automatically a meaningful business, health or policy target.

A difference between two 25th percentiles compares positions in two distributions.
It does **not** identify the effect on a particular person, the same people at
both prices, or a subgroup called “low consumers.” These are distribution-level
comparisons under the maintained assumptions of the analysis.

## What each component does

| Component | Responsibility |
|---|---|
| **Gemini: question and plan** | Turns the conversation into proposed outcome/treatment/instrument roles, units and requested comparisons, asking for missing information. The user checks the plan and confirms with a dedicated button. It performs no numerical causal calculations. |
| **TabPFN-3.5: predictive models** | In Stage 1, models the treatment distribution given the instrument. In Stage 2, models the outcome mean and distribution given the treatment and the control ranks constructed by TabCF. It supplies predictions, not proof that the research design is valid. |
| **TabCF: statistical steps** | Constructs control ranks from Stage 1 and integrates Stage 2 predictions to estimate outcome distributions under the requested treatment values. Deterministic code derives quantiles, threshold probabilities and directed contrasts. |
| **Report layer: inspectable output** | Builds text, tables, plots and downloads from the validated result bundle, retaining evidence references, support status, empirical diagnostics and warnings. Ordinary follow-ups retrieve the cached report; a new analysis requires reset. |

For technical readers, Stage 1 estimates F(X|Z) and constructs V; Stage 2 estimates
E[Y|X,V] and F(Y|X,V). Integration over V produces the interventional summaries.
Reviewing the plan makes the requested comparison explicit; evidence references
let an analyst check where a number came from; support checks prevent a request
outside the supported range from becoming an unsupported answer.

**The TabCF statistical method predates this entry.** The hackathon work is the
managed TabPFN-3.5 workflow, user journey, development measurements and reproducible
packaging around that method. It is not a new invention of TabCF or evidence that
an agent improves the estimator's accuracy.

## Current scope and interpretation

The supported method is continuous-treatment distributional IV, with a continuous
outcome in this upload interface and no baseline adjustment variables (W). The
analyst must justify the IV and control-function assumptions for the question.
Unsupported treatment types, non-empty W and unsupported interventions are
rejected. Empirical diagnostics can flag problems; they cannot establish
instrument validity or causal identification. The [README](README.md) gives the
input limits, data-transfer requirements and installation steps.

The real cigarette example is an **exploratory comparison of equally weighted
state–year per-capita cigarette sales** under maintained IV assumptions. It asks
about prices of 100 versus 120 CPI-deflated cents per pack; the outcome is sales
in packs per person per year, not an individual's smoking amount. Income,
state/year effects and within-state dependence are not resolved by this bounded
no-W model. The optional threshold of 120 packs per person per year is illustrative,
not a health or policy standard. There are no claims of individual effects,
statistical significance or policy benefit. Point estimates do not provide
confidence intervals.

Hillstrom, general method routing, automatic IV discovery and autonomous policy
deployment are outside the submission. All results remain `development_only`;
this package does not establish release readiness or formal statistical validation.

## Separate local development measurements

The separate local ZIP's five-seed synthetic comparison uses a fixed known data-generating process and
shared inputs, requested quantities and grids. It compares existing v2 CUDA and
3.5 API execution, so timing includes different hosting environments. Null findings,
regressions, refusals and missing pairs remain visible in the separate local ZIP's comparison
results. This small development measurement is not formal Track T (TabCF estimator)
validation or evidence of agent superiority, a general accuracy advantage, or
user time savings.

Saved previews and live execution are separate: reading a replay requires no
provider call; a live run requires credentials and available account quota.
The [README](README.md) preserves the reproduction command, runtime identity,
source archives and mixed-license attribution needed to inspect the package.
