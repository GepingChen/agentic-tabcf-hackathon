# Licensing of this hackathon repository

The project entry is released under **Apache License 2.0**. The full license is
in the root `LICENSE`; the entry package declares `Apache-2.0` in `pyproject.toml`.
Separate components retain the licenses and attribution listed below.

| Component | Applicable terms | Location |
|---|---|---|
| New entry Python code and new submission documentation | Apache-2.0, copyright 2026 Geping Chen | `LICENSE`, `src/agentic_tabcf_entry/__init__.py` |
| Retained DCFA statistical/runtime source, upload-cleanup correction and wheels | MIT, copyright 2026 Geping Chen | `vendor/dcfa/LICENSE`, `PARENT_MIT_LICENSE`, parent wheel license/metadata |
| Runtime JSON prompts/configuration copied from DCFA | Retained parent MIT terms | `src/agentic_tabcf_entry/configs/`, `PARENT_MIT_LICENSE` |
| Original TabCF method/source attribution | Retained MIT terms; the separate original source tree is not installed by this managed entry | `TABCF_MIT_LICENSE`, `tabcf_commit.txt`, `SOURCE_LAYOUT.md` |
| Public cigarette data extract and original source documentation | Ecdat declares GPL (>= 2); retain source attribution and accompanying GPL text | `examples/cigarette/SOURCE.md`, `examples/cigarette/GPL-2.0.txt` |
| Original saved result/evidence and the presentation derived from it | Retain provenance, warnings and applicable input/service terms; no claim that Apache supersedes those terms | `results/cigarette-35/attempt-1-api/`, `reports/cigarette-tabpfn35.html` |
| TabPFN model weights and provider services | Provider terms; model weights and provider software are not redistributed here | Prior Labs and Google terms referenced below |

The root Apache license does not replace MIT dependency notices, relicense the
source dataset, or grant rights to model weights/services. The executable entry
does not import GPL program code; the separately identified CSV is example data.
No rights-holder identity or additional permission is inferred from a new label.

MIT is listed among licenses permitted for inclusion in Apache Software Foundation
products. That is useful compatibility guidance; this repository is not an ASF
project and ASF policy is not a guarantee of hackathon acceptance.

- [Apache third-party license policy: Category A](https://www.apache.org/legal/resolved.html#category-a)
- [Applying Apache License 2.0](https://www.apache.org/legal/apply-license.html)
- [Hackathon requirements](https://platform.priorlabs.ai/hackathon-3.5)
- [Prior Labs general terms](https://priorlabs.ai/general-terms-and-conditions)
- [Prior Labs acceptable use policy](https://priorlabs.ai/aup)
- [Gemini API terms](https://ai.google.dev/gemini-api/terms)

This layout supplies an Apache-2.0 project entry with separately disclosed
dependencies and data. The organizer decides contest eligibility. Publishing
this source repository does not accept contest terms or submit an official entry.
