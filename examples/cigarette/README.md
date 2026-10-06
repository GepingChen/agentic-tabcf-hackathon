# Public cigarette-demand example

This local hackathon entry uses a 144-row, three-column extract of
`Ecdat::Cigarette`. The source, exact selection/transformations and separate data
license are in [SOURCE.md](SOURCE.md) and [GPL-2.0.txt](GPL-2.0.txt).
The original data bytes have not been changed.

| Column | Role | Stored quantity |
|---|---|---|
| `log_packs_per_capita` | Outcome Y | Natural log of annual packs per capita |
| `log_real_price` | Continuous treatment X | Natural log of CPI-deflated cents per pack |
| `real_sales_tax` | Instrument Z | CPI-deflated cents per pack |

First read [the saved genuine TabPFN-3.5 report](../../reports/cigarette-tabpfn35.html).
Download the HTML and open it in a browser. This requires no installation or
provider call. It is an exploratory saved replay, not a new live analysis.

To run the local entry, follow [the repository README](../../README.md), using
external credential files. Upload `cigarette_144.csv`, set Advanced seed
`20260920`, and paste [PROMPTS.md](PROMPTS.md). Review roles, existing log storage,
the 100→120 original-unit price comparison, quartiles and requested threshold,
then click **Confirm and generate report** once. The local entry does not require
Space sign-in or password-field credentials. Live execution consumes quota.

Read [DESIGN.md](DESIGN.md) before interpreting the output. This is an equally
weighted aggregate state–year demonstration under maintained IV/control-function
assumptions, not individual smoking effects. Income, state/year effects and
within-state dependence remain unresolved. Diagnostics do not prove instrument
validity. Preserve support refusals, unresolved quantiles and all warnings.
