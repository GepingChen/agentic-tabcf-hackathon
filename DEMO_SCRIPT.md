# Two-to-three-minute demonstration script

Use the existing genuine TabPFN-3.5 result as a clearly labeled **saved replay**
for this short walkthrough. Prepare the review screen and result views before
recording; do not make a new paid call just to capture the video. If showing a
live execution separately, disclose any wait or fast-forward. The timings below
are presentation time, not a claim about analysis speed.

- **0:00–0:25 — Start with the analyst's question.** “If we raise the price, how
  would sales change? Prices and sales can move together for reasons other than
  the price change itself. This tool is for analysts who already have an
  appropriate instrumental-variable research design.” Show the question, then
  introduce the cigarette example as an exploratory comparison of state–year
  per-capita sales, not individual smoking.
- **0:25–0:55 — Make the question checkable.** Show the public CSV and plan:
  outcome Y, price X, instrument Z, no adjustment variables W, existing log
  storage and prices of 100→120 CPI-deflated cents per pack. Show clarification
  if information is missing. “Gemini helps prepare the plan. I check the columns,
  units and comparison before confirming.” Point out the separate data-transfer
  consent and dedicated confirmation button; Gemini receives the conversation
  and column names, while Prior Labs receives the selected rows.
- **0:55–1:35 — Read the saved result.** Keep the replay label visible. “An average
  alone can miss how the distribution changes. Here we compare lower, middle and
  upper positions, plus the probability of exceeding a threshold I specified.”
  Show both outcome distribution curves (CDFs), the 25th/50th/75th percentiles and
  price-120-minus-price-100 differences. Show the probability above 120 packs per
  person per year only from the saved run that requested it. Explain that the
  threshold is illustrative and the percentiles do not identify effects on
  individuals or groups. Keep unresolved values and warnings visible.
- **1:35–2:05 — Explain the work and trace a result.** “TabPFN-3.5 supplies the
  predictive models in both stages. The existing TabCF method computes the
  intervention comparisons; the report presents the checked results. Gemini does
  not calculate the causal numbers.” Show the model version and follow one
  displayed result to its evidence reference in the downloaded bundle. Show an
  ordinary follow-up reusing the saved report without another fit.
- **2:05–2:35 — Show the limits.** Show an existing refusal of a request with W,
  or explain the restriction without claiming to have demonstrated it. “This is
  not causal analysis for any CSV. Unsupported comparisons stop; diagnostics do
  not prove the instrument is valid.” Note unresolved income, state/year effects
  and within-state dependence in this example. Retain `development_only`; make
  no individual-effect, significance or policy-benefit claim.
- **2:35–2:55 — Close with what was built and how to inspect it.** “TabCF predates
  this entry. Our hackathon work connects a reviewed question to TabPFN-3.5
  computation and a traceable report.” Show the bundle's install instructions,
  public/synthetic examples. If showing the separate local five-seed comparison,
  retain regressions or missing pairs. API and GPU timing reflects different execution environments;
  the comparison does not establish general superiority or user time savings.

Recording checks: use only authorized shareable data, hide credentials, and do
not portray a replay as a live call or a mechanics smoke as statistical validation.
Do not invent a refusal clip or a numerical finding that the saved evidence lacks.
For the saved-result segment, open [the offline example report](reports/cigarette-tabpfn35.html).
It includes the genuine v3 TabPFN-3.5 cigarette results, readable figures and
expandable evidence without requiring a live service or credentials.
