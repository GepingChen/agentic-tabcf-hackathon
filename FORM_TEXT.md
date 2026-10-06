# Copy-ready hackathon entry text

Prepared on 2026-10-06. This file is a draft, not a submitted entry.
The authenticated form has not been inspected; use the sections matching the
fields actually shown. Do not paste headings into a description-only field.

## Project title

Agentic TabCF: Distributional Causal Analysis with TabPFN

## One-line summary

A reviewed, evidence-linked workflow that uses TabPFN-3.5 to turn a continuous-treatment instrumental-variable question into outcome distributions, quantiles and threshold probabilities.

## Short description

Agentic TabCF helps analysts with an appropriate instrumental-variable research design ask how an outcome distribution would change under two continuous treatment values. Gemini prepares a plan; the analyst reviews roles, units and comparisons before confirming. TabPFN-3.5 supplies predictive models in both stages of the existing TabCF method. Deterministic tools compute and report the results, preserving evidence references, warnings and support limitations. The cigarette-demand example has an offline English report that requires no API key. Live execution requires the user's own Gemini and Prior Labs credentials and available quota. Ordinary follow-ups reuse the completed result without another fit. This is a development prototype; it does not discover valid instruments or establish identification.

## Full description

“If we raise the price, how would sales change?” Observed price–sales associations can reflect confounding, and an average alone can hide differences across outcome distributions. Agentic TabCF provides a reviewed workflow for analysts who already have an appropriate instrumental-variable design.

The user uploads an authorized three-column CSV, states the outcome, continuous treatment and instrument, and describes the comparison in plain language. Gemini prepares a specification and asks for missing information. The analyst reviews variable roles, units, requested intervention values and contrast direction, then confirms using a dedicated button. Gemini does not calculate causal numbers.

TabPFN-3.5 is central to both stages: Stage 1 models the treatment distribution conditional on the instrument and supplies the control ranks constructed by TabCF; Stage 2 models the outcome mean and distribution conditional on treatment and those ranks. Deterministic TabCF tools integrate the predictions and derive outcome distributions, quantiles, user-requested threshold probabilities and directed contrasts. Reports preserve evidence references, support information and warnings. Ordinary follow-ups reuse the completed result rather than fitting again.

The public cigarette-demand example compares equally weighted state–year per-capita sales at prices of 100 and 120 CPI-deflated cents per pack. A self-contained English HTML report presents the saved genuine TabPFN-3.5 result with charts and expandable evidence, without installation or API credentials. A public synthetic fixture is also included. Live execution uses the explicit v3.5_default API model and requires the user's own provider credentials and available quota; the contest entry does not silently fall back to an older model.

TabCF predates this entry. The hackathon contribution is the TabPFN-3.5 integration, reviewed conversational workflow, traceable reporting and reproducible packaging around that statistical method. The current interface supports continuous outcome/treatment, one instrument, exactly three numeric columns and 120–256 rows, with no baseline covariates W. Diagnostics do not prove instrument validity or identification. The real-data example remains exploratory and development_only, with unresolved income, state/year effects and within-state dependence. Quantile contrasts compare distributions, not individual effects. We claim neither statistical significance, policy benefit, general model superiority nor agent-induced accuracy gains.

The entry code and new materials are Apache-2.0. Bundled DCFA/TabCF code retains MIT notices; cigarette data and model/service terms remain separate and are disclosed in NOTICE. Please inspect README.md, PROJECT.md, the example report and the included source to reproduce and review the workflow.

## Links and personal fields

- Repository URL: https://github.com/GepingChen/agentic-tabcf-hackathon
- Video URL: optional; leave blank if no accessible recording exists.
- Additional demo URL, if offered: use an accessible version-identified example; a saved preview is not live execution.
- X/LinkedIn: optional; provide only profiles you want used for public attribution.
- Account/name/age/rights declarations: the participant must supply and review these facts.

Use the short description if the form has a restrictive length limit. The full
description is a separate alternative, not extra required form fields.
