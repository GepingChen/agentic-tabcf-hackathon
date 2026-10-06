# Copyright 2026 Geping Chen. Licensed under the Apache License, Version 2.0.
"""Thin local entry; all analysis remains in the MIT-licensed parent wheel."""

import os
from pathlib import Path

TITLE = "Agentic TabCF: Distributional Causal Analysis with TabPFN"


def main():
    config = Path(__file__).parent / "configs"
    for variable, filename in (
        ("DCFA_WEBSITE_GEMINI_CONFIG_FILE", "website_demo_gemini_v2.json"),
        ("DCFA_SPACE_CSV_DIALOGUE_CONFIG_FILE", "space_csv_dialogue_v1.json"),
    ):
        os.environ[variable] = str(config / filename)
    from dcfa_website_demo.service import run_service

    run_service(fixed_analysis_mode="api_only", presentation_title=TITLE, local_csv_dialogue=True)
