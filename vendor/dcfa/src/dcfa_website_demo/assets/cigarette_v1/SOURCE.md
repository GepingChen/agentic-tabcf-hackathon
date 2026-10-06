# Data provenance and preparation

Data prepared on 2026-09-20 for the DCFA Space's bounded CSV workflow.
Example question revised on 2026-09-21; CSV selection, transformations and bytes
are unchanged. See [DESIGN.md](DESIGN.md) for the exact-price distributional design.

## Source and attribution

The data are the public **Ecdat::Cigarette** panel, credited to Professor Jonathan
Gruber (MIT). Its documentation references Stock, J. H. and Watson, M. W. (2003),
*Introduction to Econometrics*, chapter 10. It contains 528 state-year observations
covering 48 states in 1985–1995.

- [Ecdat dataset documentation](https://vincentarelbundock.github.io/Rdatasets/doc/Ecdat/Cigarette.html)
- [Exact source CSV used](https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/cc03c29690889dbe83089f5206e2422db8c3f71f/csv/Ecdat/Cigarette.csv)
- [AER::CigarettesSW documentation and IV examples](https://vincentarelbundock.github.io/Rdatasets/doc/AER/CigarettesSW.html)
- [Ecdat package DESCRIPTION](https://github.com/cran/Ecdat/blob/master/DESCRIPTION)

The retrieved Ecdat 0.4.7 package declares **GPL (>= 2)**. Retain this attribution
and [GPL-2.0.txt](GPL-2.0.txt) when redistributing this prepared extract under those
package terms. The package metadata does not state a separate dataset-specific
license. This note does not assign ownership of the original observations or
override their source terms. The full raw input is not duplicated in this folder.

## Relationship to TabCF

The checked-in TabCF empirical loader uses AER::CigarettesSW, with only 1985 and
1995 (96 rows). Its mapping is Y = log(packs), X = log(price / cpi), and
Z = (taxs - tax) / cpi. See
[the loader](../../third_party/TabCF/empirical/run_empirical_mean.py) and
[its shipped analysis data](../../third_party/TabCF/artifacts/aggregated_csv/empirical/cigarettes/cigarettes_analysis_data.csv).

Ecdat calls the corresponding sales and price columns `packpc` and `avgprs`.
We use those fields with the same transforms and add 1990 from Ecdat. This is a
related small demonstration, not the exact TabCF paper sample. The source revision
in the URL above identifies the input; no new frozen research protocol is created.

## Selection and transformation recipe

1. Read the source CSV, interpreting its header normally.
2. Select rows whose `year` is one of `1985`, `1990`, `1995`.
3. Sort ascending by integer `year`, then alphabetically by the two-letter `state`.
   Keep all 48 states in every selected year. The `(state, year)` pair is the
   observation key; it can be recovered from this ordering and the source file.
4. Create the following columns, in this exact order, using natural logarithms:

   | Output column | Source expression | Unit |
   | --- | --- | --- |
   | `log_packs_per_capita` | `log(packpc)` | Log annual packs per capita |
   | `log_real_price` | `log(avgprs / cpi)` | Log CPI-deflated cents per pack |
   | `real_sales_tax` | `(taxs - tax) / cpi` | CPI-deflated cents per pack |

5. Export only these three numeric columns as UTF-8 comma-separated text with one
   header row and no index. Preserve floating-point precision; displayed preview
   rounding is not applied to the CSV.

No imputation, residualization, resampling, jitter, winsorization, outcome-based
selection or synthetic rows are used. State, year, population and income are
intentionally absent from the upload: this example explicitly specifies the
three-variable model, rather than silently dropping requested covariates.

The 1985/1995 overlap was matched by `(state, year)` to TabCF's shipped data.
The maximum absolute Y/X/Z differences were respectively approximately
`4.44e-15`, `6.22e-15` and `1.82e-13`, consistent with numerical serialization.
These are data-transformation checks, not estimated treatment effects.

## Interpretation boundary

The tax-price-demand setup has a substantive economic motivation: price is
endogenous, and a sales-tax component can shift price. Validity additionally
requires exclusion and exogeneity assumptions. Cross-state shopping, income,
state policies, time trends and within-state dependence are not addressed by the
current three-column Space workflow. An unconditional pooled model should not be
presented as the full textbook specification or a confirmed policy effect.

No paper result, elasticity, causal headline estimate, confidence interval or
timing measurement is supplied in this example folder. The user will perform the
first live run. Support failure is an admissible result and must not be repaired
by manipulating the sample until a preferred answer appears.
