"""Command-line entry point for the prepared static showcase."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dcfa_showcase.prepared import (
    export_prepared_showcase,
    freeze_prepared_demo,
    verify_prepared_showcase,
)
from dcfa_website_demo.app import execute_portfolio_scenario
from dcfa_website_demo.csv_upload import STANDARD_DEMO_ROWS, STANDARD_DEMO_SEED


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze and verify the static DCFA replay.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("directory", type=Path)
    freeze.add_argument("--release-commit", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("directory", type=Path)
    export.add_argument("--source-run-directory", type=Path, required=True)
    live = subparsers.add_parser("run-live")
    live.add_argument("directory", type=Path)
    live.add_argument("--output-root", type=Path, required=True)
    live.add_argument("--tabpfn-token-file", type=Path, required=True)
    live.add_argument("--gemini-key-file", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("directory", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "freeze":
        payload = freeze_prepared_demo(args.directory, release_commit=args.release_commit)
        result = {"status": "frozen", "prepared_demo_id": payload["prepared_demo_id"]}
    elif args.command == "export":
        result = export_prepared_showcase(
            args.directory,
            source_run_directory=args.source_run_directory,
        )
    elif args.command == "run-live":
        prompt = (args.directory / "prepared_prompt.txt").read_text(encoding="utf-8").rstrip("\n")
        live_result = execute_portfolio_scenario(
            "strong_iv",
            STANDARD_DEMO_ROWS,
            STANDARD_DEMO_SEED,
            question=prompt,
            output_root=args.output_root,
            token_file=args.tabpfn_token_file,
            gemini_api_key_file=args.gemini_key_file,
        )
        if live_result.response.status != "completed" or live_result.output_dir is None:
            raise RuntimeError(
                "The frozen prepared run did not complete; no showcase was exported."
            )
        result = export_prepared_showcase(
            args.directory,
            source_run_directory=live_result.output_dir,
        )
    else:
        result = verify_prepared_showcase(args.directory)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
