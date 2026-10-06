"""Run a comparison arm with an explicitly exported parent source version.

This file is a measurement driver, not a statistical implementation. PYTHONPATH
selects the identified parent; all computation and verification use that parent.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def main():
    from dcfa.canonical import to_primitive
    from dcfa.tabcf_iv import pipeline
    from dcfa_website_demo.daily import execute_daily_dataset
    from dcfa_website_demo.v2_remote import decode_payload

    directory = Path(sys.argv[1])
    request = json.loads((directory / "worker_request.json").read_text())
    kwargs = decode_payload(request["payload"])
    kwargs.update(
        output_root=directory,
        result_scenario="model_comparison",
        output_scenario="model-comparison",
    )
    original = pipeline.predict_backend
    stages = []

    def measured(*args, **kw):
        start = time.perf_counter()
        try:
            return original(*args, **kw)
        finally:
            stages.append(
                {
                    "stage": args[1],
                    "client_wall_seconds": time.perf_counter() - start,
                    "backend_observations": dict(getattr(args[0], "audit_details", ())),
                }
            )

    pipeline.predict_backend = measured
    started = time.perf_counter()
    result = execute_daily_dataset(
        mode=request["mode"], compiled_kwargs=kwargs, managed_settings={}
    )
    elapsed = time.perf_counter() - started
    daily = result.llm_trace["daily_execution"]
    daily["attempts"][-1]["client_wall_seconds"] = elapsed
    measurement = {
        "client_wall_seconds": elapsed,
        "provider_server_seconds": None,
        "stages": stages,
        "remote_stage_timing_available": False if request["mode"] == "v2_only" else None,
    }
    (result.output_dir / "execution_measurement.json").write_text(json.dumps(measurement, indent=2))
    (directory / "worker_result.json").write_text(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "response": to_primitive(result.response),
                "llm_trace": result.llm_trace,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
