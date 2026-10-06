# Local entry: exact-price distribution prompt

Start the extracted entry using the README's external credential files. Open
the local app's **Upload CSV** conversation, authorize the data transfer,
upload `cigarette_144.csv`, and set Advanced seed `20260920`. This local entry
does not require Space sign-in or password-field credentials.

Paste this complete prompt to reproduce the saved report's requested quantities:

```text
Y = log_packs_per_capita; X = log_real_price; Z = real_sales_tax. No W.
Compare real price from 100 to 120 CPI-deflated cents per pack. X and Y are already natural logs. Do not transform the CSV again.
Show both CDFs and their CDF-derived approximate PDFs. Report the 25th, 50th and 75th quantiles and their differences in packs per person per year, price 120 minus price 100.
Use one analysis. Place warnings at the end in small text.
Also report the probability exceeding 120 packs per person per year and its change in percentage points.
```

The 120-pack threshold is illustrative, not a health or policy standard. If it
is not part of a new question, omit the last sentence; that new plan must not
contain a threshold probability. Percentiles compare distributions and do not
identify effects on particular people or groups.

Before execution, review Y/X/Z, no W, original prices, log-scale model inputs,
the CDFs/approximate PDFs, quartiles, requested threshold and second-minus-first
direction. Click **Confirm and generate report** once. Textual confirmation does
not execute. Download the verified ZIP after success. Ordinary follow-ups reuse
the cached report; reset for another analysis. Support refusal is an admissible
outcome. Never edit data or prices to force acceptance. Preserve unresolved
quantiles and all warnings.
