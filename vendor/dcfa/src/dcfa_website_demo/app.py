"""Website-oriented Gradio demo for the auditable TabCF Analyst workflow."""

from __future__ import annotations

import html
import importlib.metadata
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from dcfa.agent.compiler import CompilationRequest
from dcfa.agent.runtime import AgentResponse, CausalAgentRuntime
from dcfa.canonical import content_id, sha256_digest
from dcfa.constants import EstimatorBackend, EvidenceStatus, ExecutionProfile
from dcfa.errors import DCFAError, ErrorCode
from dcfa.schemas import AnalysisSpecification, DatasetManifest
from dcfa.tabcf_iv.development_dgp import generate_development_iv
from dcfa.tabcf_iv.local_tabpfn import (
    LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
    make_local_tabpfn_v2_backend,
)
from dcfa.tabcf_iv.managed_client import (
    MANAGED_BACKEND_PARAMETERS,
    MANAGED_CLIENT_VERSION,
    TabPFNClientBackend,
)
from dcfa.tabcf_iv.managed_smoke import (
    load_managed_client_module,
    read_managed_token_file,
)
from dcfa.tabcf_iv.pipeline import AnalysisRun, TabCFAnalysisEngine
from dcfa_website_demo.csv_upload import (
    MAX_UPLOAD_ROWS,
    MIN_UPLOAD_ROWS,
    CSVDataBoundary,
    ValidatedCSVColumns,
    assign_csv_roles,
    read_authorized_csv_columns,
)
from dcfa_website_demo.gemini import (
    GeminiWebsiteCompilation,
    compile_website_question,
    write_compilation_trace,
)
from dcfa_website_demo.presentation import (
    answer_sentence,
    present_error,
    present_query,
    render_visitor_plot,
)

DEFAULT_OUTPUT_ROOT = Path("artifacts/local/website-demo")
DEFAULT_MANAGED_TOKEN_FILE = Path.home() / ".config" / "dcfa" / "tabpfn_api_key"
DEFAULT_GEMINI_API_KEY_FILE = Path.home() / ".config" / "dcfa" / "gemini_api_key"
MIN_DEMO_ROWS = 120
MAX_DEMO_ROWS = 256
MIN_DEMO_SEED = 0
MAX_DEMO_SEED = 2**32 - 1
_OUTPUT_RESERVATION_LOCK = threading.Lock()
_BUILD_REVISION_PATTERN = re.compile(r"^[0-9a-f]{7,12}$")
_LOGGER = logging.getLogger(__name__)
DEFAULT_CSV_QUESTION = (
    "The outcome column is Y. The continuous treatment column is X. The scalar instrument column "
    "is Z. Estimate the median outcome contrast for a high supported level of X versus a low "
    "supported level of X. Preserve all weak-instrument and support warnings, and return no "
    "numerical estimate if either intervention is outside observed support."
)
_FROZEN_PRESET_PROPOSAL = {
    "decision": "analyze",
    "reason": "Use the published preset median contrast specification.",
    "outcome": "Y",
    "treatment": "X",
    "instrument": "Z",
    "treatment_type": "continuous",
    "objective": "quantile_contrast",
    "x_label": "high",
    "comparison_x_label": "low",
    "level_label": "median",
}


@dataclass(frozen=True)
class DemoScenario:
    label: str
    description: str
    question: str
    instrument_strength: float
    intervention_quantiles: tuple[float, ...] = (0.1, 0.3, 0.5, 0.7, 0.9)
    violate_support: bool = False


@dataclass(frozen=True)
class PortfolioDemoResult:
    scenario: str
    response: AgentResponse
    plot_path: Path | None
    output_dir: Path | None
    llm_trace: dict[str, Any]


SCENARIOS: dict[str, DemoScenario] = {
    "strong_iv": DemoScenario(
        label="Supported workflow",
        description="A strong first stage reaches an evidence-linked answer.",
        question=(
            "How does the median outcome change between a low and a high supported "
            "treatment intervention?"
        ),
        instrument_strength=1.6,
    ),
    "weak_iv": DemoScenario(
        label="Weak-IV warning",
        description="The workflow completes while preserving empirical warnings.",
        question=(
            "Estimate the same median contrast, and keep any weak-instrument or support "
            "warnings attached to the answer."
        ),
        instrument_strength=0.02,
        intervention_quantiles=(0.3, 0.4, 0.5, 0.6, 0.7),
    ),
    "support_violation": DemoScenario(
        label="Outside-support block",
        description="An unsupported intervention stops before Stage 2 and returns no number.",
        question=("Estimate the median contrast at an intervention beyond the observed support."),
        instrument_strength=1.6,
        violate_support=True,
    ),
}


DEMO_CSS = """
:root {
  --demo-paper: #ffffff;
  --demo-surface: #ffffff;
  --demo-muted-surface: #f1f5f9;
  --demo-ink: #172033;
  --demo-muted: #526176;
  --demo-accent: #2563eb;
  --demo-accent-deep: #1d4ed8;
  --demo-line: #dce3ed;
  --demo-warning: #9a5d17;
  --demo-danger: #9b3f35;
}

body,
.gradio-container {
  background: var(--demo-paper) !important;
  color: var(--demo-ink) !important;
}

.gradio-container {
  width: 100% !important;
  max-width: 64rem !important;
  min-width: 0 !important;
  margin-inline: auto !important;
  padding: clamp(1rem, 2.5vw, 2rem) !important;
  box-sizing: border-box !important;
  font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif !important;
}

.gradio-container .main {
  padding: 0 !important;
  width: 100% !important;
  min-width: 0 !important;
  box-sizing: border-box !important;
}

/* Spaces can disable iframe document scrolling; keep an app-owned scroll area. */
.gradio-container:has(.demo-space) {
  height: 100dvh !important;
  max-height: 100dvh !important;
  min-height: 0 !important;
  overflow-y: auto !important;
}

.gradio-container:has(.demo-space) .main {
  flex-shrink: 0;
}

.demo-hero {
  padding: .5rem 0 1rem;
  border-bottom: 1px solid var(--demo-line);
}

.demo-hero h1 {
  max-width: 21ch !important;
  margin: 0 0 .75rem !important;
  color: var(--demo-ink) !important;
  font-size: clamp(2rem, 4vw, 3rem) !important;
  line-height: 1.02 !important;
  letter-spacing: -.045em !important;
}

.demo-hero-copy {
  max-width: 47rem;
  margin: 0 0 1rem;
  color: var(--demo-muted);
  font-family: inherit;
  font-size: clamp(1.02rem, 2vw, 1.18rem);
  line-height: 1.65;
}

.demo-transfer-note {
  max-width: 47rem;
  margin: .75rem 0 0;
  padding: .75rem .9rem;
  border-left: .25rem solid var(--demo-warning);
  background: #fff5e6;
  color: var(--demo-ink);
  font-size: .84rem;
  line-height: 1.55;
}

.demo-section-heading {
  margin: 0 0 .35rem !important;
  font-size: 1.15rem !important;
  letter-spacing: -.01em;
}

.demo-section-copy {
  margin-bottom: .35rem !important;
  color: var(--demo-muted) !important;
  font-size: .92rem !important;
}

.demo-workspace { margin-top: 1.25rem; gap: 1.5rem !important; }
.demo-input { min-width: 0 !important; }
.demo-results { min-width: 0 !important; gap: .9rem !important; }
.demo-results:has(> .hidden):not(:has(> :not(.hidden))) { display: none; }
#input-tabs > .tab-nav { margin-bottom: 1rem; }
#csv-upload { border: 1px dashed var(--demo-accent) !important; }
#csv-question textarea { font-size: 1rem !important; }
.demo-footer {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: .5rem;
  border-top: 1px solid var(--demo-line);
  margin-top: 1.5rem;
  padding-top: .8rem;
  color: var(--demo-muted);
  font-size: .75rem;
}
.demo-footer p { margin: 0; font-size: inherit; }

#run-demo-button.primary,
#run-csv-button.primary {
  min-height: 3rem;
  border: 1px solid var(--demo-accent-deep) !important;
  border-radius: .3rem !important;
  background: var(--demo-accent-deep) !important;
  color: white !important;
  font-weight: 750 !important;
}

#run-demo-button.primary:hover,
#run-csv-button.primary:hover {
  background: var(--demo-accent) !important;
}

.demo-status {
  padding: .9rem 1rem;
  border-left: .28rem solid var(--demo-accent);
  border-radius: .25rem;
  background: #eff6ff;
  color: var(--demo-ink);
  line-height: 1.55;
}

.demo-status strong {
  display: block;
  margin-bottom: .15rem;
}

.demo-status--warning {
  border-left-color: var(--demo-warning);
  background: #fff5e6;
}

.demo-status--blocked {
  border-left-color: var(--demo-danger);
  background: #fff0ee;
}

.demo-status--idle {
  border-left-color: var(--demo-line);
  background: var(--demo-muted-surface);
}

.state-graph {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;
  padding: 0;
  gap: .55rem;
  list-style: none;
}

.state-graph li {
  position: relative;
  padding: .7rem .8rem .7rem 2.2rem;
  border: 1px solid var(--demo-line);
  border-radius: .35rem;
  background: var(--demo-surface);
  color: var(--demo-muted);
  font-size: .82rem;
  font-weight: 650;
}

.state-graph li::before {
  position: absolute;
  top: 50%;
  left: .8rem;
  width: .65rem;
  height: .65rem;
  border-radius: 50%;
  background: var(--demo-line);
  content: "";
  transform: translateY(-50%);
}

.state-graph li.completed {
  color: var(--demo-ink);
}

.state-graph li.completed::before {
  background: var(--demo-accent);
}

.state-graph li.current {
  border-color: var(--demo-accent);
  background: #eff6ff;
  color: var(--demo-ink);
}

.state-graph li.current::before {
  background: var(--demo-accent);
  box-shadow: 0 0 0 .22rem #dbeafe;
}

.state-graph li.pending {
  color: var(--demo-muted);
}

.state-graph li.blocked::before {
  background: var(--demo-danger);
}

.state-reason {
  display: block;
  margin-top: .14rem;
  color: var(--demo-muted);
  font-size: .72rem;
  font-weight: 450;
}

.demo-answer {
  margin-top: .65rem;
}

.demo-answer h3 {
  margin-bottom: .55rem !important;
  color: var(--demo-muted) !important;
  font-size: .78rem !important;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.demo-answer p {
  max-width: 52rem;
  margin: .6rem 0 !important;
  font-family: inherit;
  font-size: .95rem !important;
  line-height: 1.55;
}

.demo-answer { overflow-x: auto; min-width: 0; }

.demo-answer table {
  width: 100%;
  min-width: 32rem;
  table-layout: auto;
  font-size: .9rem;
  line-height: 1.4;
}

.demo-answer table th, .demo-answer table td {
  padding: .45rem .7rem !important;
  height: auto !important;
  vertical-align: middle;
  white-space: nowrap;
  word-break: normal;
  overflow-wrap: normal;
  font-variant-numeric: tabular-nums;
}

.demo-answer code {
  overflow-wrap: anywhere;
  white-space: normal;
}

.demo-confirmation-plan { overflow-x: auto; }

.demo-confirmation-plan table {
  min-width: 32rem;
  width: 100%;
  table-layout: fixed;
  font-size: .82rem;
  overflow-wrap: anywhere;
}

.demo-confirmation-plan p {
  margin: .65rem 0 !important;
  font-family: inherit;
  font-size: .9rem;
  line-height: 1.5;
}

.demo-warning-list {
  margin: .55rem 0 0;
  padding-left: 1.15rem;
}

.demo-warning-list li + li {
  margin-top: .35rem;
}

.demo-evidence-card {
  height: 100%;
}

.demo-result-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: .8rem;
}

.demo-result-detail {
  padding: .9rem;
  border: 1px solid var(--demo-line);
  border-radius: .35rem;
  background: var(--demo-surface);
}

.demo-result-detail h3 {
  margin: 0 0 .45rem;
  font-size: .78rem;
  letter-spacing: .05em;
  text-transform: uppercase;
}

.demo-result-detail p {
  margin: .4rem 0 0;
  color: var(--demo-muted);
  font-size: .84rem;
  line-height: 1.5;
}

.demo-result-detail--development {
  border-left: .25rem solid var(--demo-warning);
  background: #fff5e6;
}

.demo-evidence-card h3 {
  margin: 0 0 .85rem;
  font-size: 1rem;
}

.demo-evidence-placeholder {
  color: var(--demo-muted);
  font-family: inherit;
}

@media (max-width: 48rem) {
  .gradio-container { padding: .8rem !important; }
  .state-graph { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .demo-result-details { grid-template-columns: 1fr; }
}
@media (max-width: 30rem) {
  .demo-hero { padding-top: .45rem; }
  .demo-hero-copy { line-height: 1.45; }
}
"""


def build_demo_theme() -> Any:
    """Build the shared restrained theme for local and ZeroGPU launch surfaces."""
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError(
            "Install the website demo with: python -m pip install -r requirements-website-demo.lock"
        ) from exc
    return gr.themes.Base(
        primary_hue="blue",
        secondary_hue="blue",
        neutral_hue="slate",
        radius_size="sm",
        font=("Inter", "ui-sans-serif", "system-ui", "sans-serif"),
        font_mono=("IBM Plex Mono", "ui-monospace", "monospace"),
    )


class WebsiteFinalizationError(RuntimeError):
    """A completed computation could not be published; restarting must be explicit."""


class _WebsiteAnalysisTool:
    """Presentation-only adapter that preserves the runtime's tool contract."""

    def __init__(self, output_dir: Path, engine: TabCFAnalysisEngine) -> None:
        self.output_dir = output_dir
        self.engine = engine
        self.last_run: AnalysisRun | None = None

    def analyze(
        self,
        data: dict[str, np.ndarray],
        specification: AnalysisSpecification,
        dataset_manifest: DatasetManifest,
        *,
        output_dir: Any = None,
    ) -> AnalysisRun:
        del output_dir
        self.last_run = self.engine.analyze(
            data,
            specification,
            dataset_manifest,
            output_dir=self.output_dir,
        )
        return self.last_run

    def follow_up(self, specification: AnalysisSpecification, query_id: str):
        return self.engine.follow_up(specification, query_id)


def scenario_question(scenario: str) -> str:
    """Return the visible example question for a frozen portfolio scenario."""
    try:
        return SCENARIOS[scenario].question
    except KeyError as exc:
        raise ValueError(f"Unknown demo scenario: {scenario}") from exc


def managed_token_file_from_environment() -> Path:
    """Resolve the repository-external managed-client credential file."""
    return Path(os.environ.get("DCFA_TABPFN_TOKEN_FILE", str(DEFAULT_MANAGED_TOKEN_FILE)))


def gemini_api_key_file_from_environment() -> Path:
    """Resolve the repository-external Gemini credential file."""
    return Path(os.environ.get("DCFA_GEMINI_API_KEY_FILE", str(DEFAULT_GEMINI_API_KEY_FILE)))


def _reserve_output_directory(root: Path, scenario: str, seed: int) -> Path:
    """Atomically reserve a fresh immutable run directory for a UI request."""
    run_root = root / scenario / f"seed-{seed}"
    with _OUTPUT_RESERVATION_LOCK:
        run_root.mkdir(parents=True, exist_ok=True)
        run_index = 1
        while True:
            output_dir = run_root / f"run-{run_index:04d}"
            try:
                output_dir.mkdir()
            except FileExistsError:
                run_index += 1
                continue
            return output_dir


def _remove_empty_reservation(output_dir: Path) -> None:
    """Remove only the empty leaf reserved by this request after a blocked run."""
    try:
        output_dir.rmdir()
    except OSError:
        return


def execute_portfolio_scenario(
    scenario: str,
    rows: int,
    seed: int,
    *,
    question: str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    token_file: Path | None = None,
    client_module: Any | None = None,
    client_version: str | None = None,
    gemini_api_key_file: Path | None = None,
    gemini_client: Any | None = None,
    gemini_sdk_version: str | None = None,
    analysis_mode: str | None = None,
) -> PortfolioDemoResult:
    """Execute one frozen guided scenario through managed TabPFN and the typed runtime."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown demo scenario: {scenario}")
    rows = int(rows)
    seed = int(seed)
    if not MIN_DEMO_ROWS <= rows <= MAX_DEMO_ROWS:
        raise ValueError(f"Demo rows must be between {MIN_DEMO_ROWS} and {MAX_DEMO_ROWS}.")
    if not MIN_DEMO_SEED <= seed <= MAX_DEMO_SEED:
        raise ValueError(f"Demo seed must be between {MIN_DEMO_SEED} and {MAX_DEMO_SEED}.")

    selected = SCENARIOS[scenario]
    dataset = generate_development_iv(
        n=rows,
        seed=seed,
        instrument_strength=selected.instrument_strength,
    )
    manifest = replace(dataset.manifest, estimator_backend=EstimatorBackend.TABPFN)
    interventions = tuple(
        float(value) for value in np.quantile(dataset.columns["X"], selected.intervention_quantiles)
    )
    if selected.violate_support:
        interventions = (
            *interventions[:-1],
            float(np.max(dataset.columns["X"]) + 5.0),
        )
    return _execute_managed_dataset(
        result_scenario=scenario,
        output_scenario=scenario,
        columns=dataset.columns,
        manifest=manifest,
        outcome="Y",
        treatment="X",
        instrument="Z",
        question=question or selected.question,
        interventions=interventions,
        seed=seed,
        output_root=output_root,
        analysis_mode=analysis_mode,
        token_file=token_file,
        client_module=client_module,
        client_version=client_version,
        gemini_api_key_file=gemini_api_key_file,
        gemini_client=gemini_client,
        gemini_sdk_version=gemini_sdk_version,
    )


def execute_csv_upload(
    csv_file: str | Path,
    outcome: str | None,
    treatment: str | None,
    instrument: str | None,
    confirmed: bool,
    seed: int,
    *,
    question: str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    token_file: Path | None = None,
    client_module: Any | None = None,
    client_version: str | None = None,
    gemini_api_key_file: Path | None = None,
    gemini_client: Any | None = None,
    gemini_sdk_version: str | None = None,
    analysis_mode: str | None = None,
) -> PortfolioDemoResult:
    """Execute a confirmed, strictly bounded local Y/X/Z CSV through managed TabPFN."""
    seed = int(seed)
    if not MIN_DEMO_SEED <= seed <= MAX_DEMO_SEED:
        raise ValueError(f"Demo seed must be between {MIN_DEMO_SEED} and {MAX_DEMO_SEED}.")
    boundary = (
        CSVDataBoundary.DAILY_SELECTED_POLICY
        if analysis_mode is not None
        else CSVDataBoundary.MANAGED_PRIOR_LABS
    )
    validated = read_authorized_csv_columns(
        csv_file,
        confirmed=bool(confirmed),
        data_boundary=boundary,
    )
    selected_question = question or DEFAULT_CSV_QUESTION
    compilation = compile_website_question(
        selected_question,
        api_key_file=gemini_api_key_file or gemini_api_key_file_from_environment(),
        client=gemini_client,
        sdk_version=gemini_sdk_version,
        available_columns=validated.header,
        role_overrides={
            "outcome": outcome,
            "treatment": treatment,
            "instrument": instrument,
        },
    )
    dataset = assign_csv_roles(
        validated,
        outcome=compilation.outcome,
        treatment=compilation.treatment,
        instrument=compilation.instrument,
    )
    interventions = tuple(
        float(value)
        for value in np.quantile(dataset.columns[dataset.treatment], (0.1, 0.3, 0.5, 0.7, 0.9))
    )
    digest_suffix = dataset.manifest.dataset_hash.split(":", maxsplit=1)[1][:12]
    return _execute_managed_dataset(
        result_scenario="csv_upload",
        output_scenario=f"csv-upload-{digest_suffix}",
        columns=dataset.columns,
        manifest=dataset.manifest,
        outcome=dataset.outcome,
        treatment=dataset.treatment,
        instrument=dataset.instrument,
        question=selected_question,
        interventions=interventions,
        seed=seed,
        output_root=output_root,
        analysis_mode=analysis_mode,
        token_file=token_file,
        client_module=client_module,
        client_version=client_version,
        gemini_api_key_file=gemini_api_key_file,
        gemini_client=gemini_client,
        gemini_sdk_version=gemini_sdk_version,
        compilation=compilation,
    )


def _frozen_preset_compilation(question: str) -> GeminiWebsiteCompilation:
    trace_body = {
        "protocol_version": "website_demo_frozen_preset_v1",
        "provider": "none",
        "model": "none",
        "model_request_count": 0,
        "interaction_id": None,
        "interaction_status": "not_requested",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "thought_tokens": 0,
            "total_tokens": 0,
        },
        "request_hash": sha256_digest(question.strip()),
        "data_sent_to_gemini": [],
        "data_rows_sent_to_gemini": 0,
        "actual_intervention_values_sent_to_gemini": 0,
        "proposal": dict(_FROZEN_PRESET_PROPOSAL),
    }
    return GeminiWebsiteCompilation(
        outcome="Y",
        treatment="X",
        instrument="Z",
        objective="quantile_contrast",
        x_label="high",
        comparison_x_label="low",
        level=0.5,
        trace={"trace_id": content_id("website_frozen_trace", trace_body), **trace_body},
    )


def execute_local_portfolio_scenario(
    scenario: str,
    rows: int,
    seed: int,
    *,
    model_path: Path,
    prediction_runner: Any = None,
    question: str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    gemini_api_key_file: Path | None = None,
    gemini_client: Any | None = None,
    gemini_sdk_version: str | None = None,
    dataset_executor: Any = None,
) -> PortfolioDemoResult:
    """Execute a synthetic scenario with the frozen local TabPFN v2 profile."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown demo scenario: {scenario}")
    rows = int(rows)
    seed = int(seed)
    if not MIN_DEMO_ROWS <= rows <= MAX_DEMO_ROWS:
        raise ValueError(f"Demo rows must be between {MIN_DEMO_ROWS} and {MAX_DEMO_ROWS}.")
    if not MIN_DEMO_SEED <= seed <= MAX_DEMO_SEED:
        raise ValueError(f"Demo seed must be between {MIN_DEMO_SEED} and {MAX_DEMO_SEED}.")
    selected = SCENARIOS[scenario]
    dataset = generate_development_iv(
        n=rows,
        seed=seed,
        instrument_strength=selected.instrument_strength,
    )
    manifest = replace(dataset.manifest, estimator_backend=EstimatorBackend.TABPFN)
    interventions = tuple(
        float(value) for value in np.quantile(dataset.columns["X"], selected.intervention_quantiles)
    )
    if selected.violate_support:
        interventions = (*interventions[:-1], float(np.max(dataset.columns["X"]) + 5.0))
    selected_question = question or selected.question
    compilation = (
        _frozen_preset_compilation(selected_question)
        if gemini_api_key_file is None and gemini_client is None
        else compile_website_question(
            selected_question,
            api_key_file=gemini_api_key_file or gemini_api_key_file_from_environment(),
            client=gemini_client,
            sdk_version=gemini_sdk_version,
        )
    )
    kwargs = dict(
        result_scenario=scenario,
        output_scenario=scenario,
        columns=dataset.columns,
        manifest=manifest,
        outcome="Y",
        treatment="X",
        instrument="Z",
        interventions=interventions,
        seed=seed,
        output_root=output_root,
        compilation=compilation,
    )
    if dataset_executor is not None:
        return dataset_executor(kwargs)
    return _execute_compiled_dataset(
        **kwargs,
        prediction_runner=prediction_runner,
        backend_parameters=LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
        backend_factory=lambda specification: make_local_tabpfn_v2_backend(
            specification, model_path=model_path
        ),
    )


def execute_local_csv_upload(
    csv_file: str | Path,
    outcome: str | None,
    treatment: str | None,
    instrument: str | None,
    confirmed: bool,
    seed: int,
    *,
    model_path: Path,
    question: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    gemini_api_key_file: Path,
    gemini_client: Any | None = None,
    gemini_sdk_version: str | None = None,
) -> PortfolioDemoResult:
    """Execute an authorized HF-uploaded CSV with local TabPFN v2."""
    seed = int(seed)
    if not MIN_DEMO_SEED <= seed <= MAX_DEMO_SEED:
        raise ValueError(f"Demo seed must be between {MIN_DEMO_SEED} and {MAX_DEMO_SEED}.")
    boundary = CSVDataBoundary.HF_ZEROGPU_LOCAL
    validated = read_authorized_csv_columns(
        csv_file,
        confirmed=bool(confirmed),
        data_boundary=boundary,
    )
    compilation = compile_website_question(
        question,
        api_key_file=gemini_api_key_file,
        client=gemini_client,
        sdk_version=gemini_sdk_version,
        available_columns=validated.header,
        role_overrides={
            "outcome": outcome,
            "treatment": treatment,
            "instrument": instrument,
        },
    )
    return execute_prepared_local_csv(
        validated,
        compilation,
        seed,
        model_path=model_path,
        output_root=output_root,
    )


def execute_prepared_local_csv(
    validated: ValidatedCSVColumns,
    compilation: GeminiWebsiteCompilation,
    seed: int,
    *,
    model_path: Path,
    prediction_runner: Any = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    dataset_executor: Any = None,
) -> PortfolioDemoResult:
    """Execute an already reviewed CSV proposal without another provider request."""
    seed = int(seed)
    if not MIN_DEMO_SEED <= seed <= MAX_DEMO_SEED:
        raise ValueError(f"Demo seed must be between {MIN_DEMO_SEED} and {MAX_DEMO_SEED}.")
    dataset = assign_csv_roles(
        validated,
        outcome=compilation.outcome,
        treatment=compilation.treatment,
        instrument=compilation.instrument,
    )
    interventions = tuple(
        float(value)
        for value in np.quantile(dataset.columns[dataset.treatment], (0.1, 0.3, 0.5, 0.7, 0.9))
    )
    digest_suffix = dataset.manifest.dataset_hash.split(":", maxsplit=1)[1][:12]
    kwargs = dict(
        result_scenario="csv_upload",
        output_scenario=f"csv-upload-{digest_suffix}",
        columns=dataset.columns,
        manifest=dataset.manifest,
        outcome=dataset.outcome,
        treatment=dataset.treatment,
        instrument=dataset.instrument,
        interventions=interventions,
        seed=seed,
        output_root=output_root,
        compilation=compilation,
    )
    if dataset_executor is not None:
        return dataset_executor(kwargs)
    return _execute_compiled_dataset(
        **kwargs,
        prediction_runner=prediction_runner,
        backend_parameters=LOCAL_TABPFN_V2_BACKEND_PARAMETERS,
        backend_factory=lambda specification: make_local_tabpfn_v2_backend(
            specification, model_path=model_path
        ),
    )


def _execute_managed_dataset(
    *,
    result_scenario: str,
    output_scenario: str,
    columns: dict[str, np.ndarray],
    manifest: DatasetManifest,
    outcome: str,
    treatment: str,
    instrument: str,
    question: str,
    interventions: tuple[float, ...],
    seed: int,
    output_root: Path,
    token_file: Path | None,
    client_module: Any | None,
    client_version: str | None,
    gemini_api_key_file: Path | None,
    gemini_client: Any | None,
    gemini_sdk_version: str | None,
    compilation: GeminiWebsiteCompilation | None = None,
    analysis_mode: str | None = None,
) -> PortfolioDemoResult:
    """Run one already-validated no-W dataset through the shared managed profile."""
    if analysis_mode is not None:
        from dcfa_website_demo.daily import execute_daily_dataset

        llm_compilation = compilation or compile_website_question(
            question,
            api_key_file=gemini_api_key_file or gemini_api_key_file_from_environment(),
            client=gemini_client,
            sdk_version=gemini_sdk_version,
        )
        return execute_daily_dataset(
            mode=analysis_mode,
            compiled_kwargs=dict(
                result_scenario=result_scenario,
                output_scenario=output_scenario,
                columns=columns,
                manifest=manifest,
                outcome=outcome,
                treatment=treatment,
                instrument=instrument,
                interventions=interventions,
                seed=seed,
                output_root=output_root,
                compilation=llm_compilation,
            ),
            managed_settings=dict(
                token_file=token_file, client_module=client_module, client_version=client_version
            ),
        )
    credential = read_managed_token_file(token_file or managed_token_file_from_environment())
    client = client_module or load_managed_client_module()
    observed_client_version = client_version or importlib.metadata.version("tabpfn-client")
    if observed_client_version != MANAGED_CLIENT_VERSION:
        raise DCFAError(
            ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
            "The installed tabpfn-client version does not match the frozen website profile.",
            stage="managed_client.version",
            context={
                "expected": MANAGED_CLIENT_VERSION,
                "observed": observed_client_version,
            },
        )

    from dcfa.tabcf_iv.managed_session import MANAGED_SESSION_LOCK

    MANAGED_SESSION_LOCK.acquire()
    try:
        llm_compilation = compilation or compile_website_question(
            question,
            api_key_file=gemini_api_key_file or gemini_api_key_file_from_environment(),
            client=gemini_client,
            sdk_version=gemini_sdk_version,
        )
        client.set_access_token(credential)
        del credential

        def backend_factory(specification: AnalysisSpecification) -> TabPFNClientBackend:
            return TabPFNClientBackend.from_specification(
                specification,
                regressor_class=client.TabPFNRegressor,
                client_version=observed_client_version,
            )

        return _execute_compiled_dataset(
            result_scenario=result_scenario,
            output_scenario=output_scenario,
            columns=columns,
            manifest=manifest,
            outcome=outcome,
            treatment=treatment,
            instrument=instrument,
            interventions=interventions,
            seed=seed,
            output_root=output_root,
            compilation=llm_compilation,
            backend_parameters=MANAGED_BACKEND_PARAMETERS,
            backend_factory=backend_factory,
        )
    finally:
        try:
            client.reset()
        finally:
            MANAGED_SESSION_LOCK.release()


def compiled_request(
    *,
    outcome,
    treatment,
    instrument,
    compilation,
    interventions,
    manifest,
    backend_parameters,
    seed,
):
    """Resolve the already confirmed symbolic plan identically for both executors."""
    if (outcome, treatment, instrument) != (
        compilation.outcome,
        compilation.treatment,
        compilation.instrument,
    ):
        raise DCFAError(
            ErrorCode.LLM_OUTPUT_INVALID,
            "The compiled role mapping does not match the validated dataset mapping.",
            stage="website_demo.gemini_output",
        )
    if compilation.distribution is not None:
        import math

        interventions = tuple(math.log(p) for p in compilation.distribution.prices)
        x_value, comparison_value = interventions[1], interventions[0]
    else:
        label_values = {
            "low": interventions[0],
            "center": interventions[len(interventions) // 2],
            "high": interventions[-1],
        }
        x_value = label_values[compilation.x_label]
        comparison_value = (
            None
            if compilation.comparison_x_label is None
            else label_values[compilation.comparison_x_label]
        )
    return CompilationRequest(
        dataset_hash=manifest.dataset_hash,
        outcome=outcome,
        treatment=treatment,
        instrument=instrument,
        objective=compilation.objective,
        intervention_grid=interventions,
        x=x_value,
        comparison_x=comparison_value,
        distribution=compilation.distribution,
        level=compilation.level,
        units=f"{outcome}_units",
        confirmed_by_user=True,
        execution_profile=ExecutionProfile.LOCAL_DEVELOPMENT,
        estimator_backend=EstimatorBackend.TABPFN,
        evidence_status=EvidenceStatus.DEVELOPMENT_ONLY,
        backend_parameters=backend_parameters,
        seed=seed,
    )


def _execute_compiled_dataset(
    *,
    result_scenario: str,
    output_scenario: str,
    columns: dict[str, np.ndarray],
    manifest: DatasetManifest,
    outcome: str,
    treatment: str,
    instrument: str,
    interventions: tuple[float, ...],
    seed: int,
    output_root: Path,
    compilation: GeminiWebsiteCompilation,
    backend_parameters: tuple[tuple[str, str], ...],
    backend_factory: Any,
    prediction_runner: Any = None,
    reserved_output_dir: Path | None = None,
    preserve_failure: bool = False,
) -> PortfolioDemoResult:
    """Execute one compiled request through an injected deterministic backend."""
    compilation.trace["backend_access_mode"] = dict(backend_parameters).get(
        "access_mode", "unknown"
    )
    request = compiled_request(
        outcome=outcome,
        treatment=treatment,
        instrument=instrument,
        compilation=compilation,
        interventions=interventions,
        manifest=manifest,
        backend_parameters=backend_parameters,
        seed=seed,
    )
    started = time.perf_counter()
    measurements = {"provider_server_seconds": None, "stages": []}
    predictions_completed = False
    if prediction_runner is None:
        from dcfa.tabcf_iv.pipeline import predict_backend

        prediction_runner = predict_backend
    original_runner = prediction_runner

    def tracked_predictions(*args, **kwargs):
        nonlocal predictions_completed
        stage_started = time.perf_counter()
        try:
            result = original_runner(*args, **kwargs)
        except DCFAError as exc:
            exc.context["analysis_stage"] = args[1]
            raise
        finally:
            measurements["stages"].append(
                {
                    "stage": args[1],
                    "client_wall_seconds": time.perf_counter() - stage_started,
                    "backend_observations": dict(getattr(args[0], "audit_details", ())),
                }
            )
        if args[1] == "stage2":
            predictions_completed = True
        return result

    if prediction_runner is not None:
        prediction_runner = tracked_predictions
    try:
        output_dir = reserved_output_dir or _reserve_output_directory(
            Path(output_root), output_scenario, seed
        )
        engine = TabCFAnalysisEngine(
            backend_factory=backend_factory,
            **({"prediction_runner": prediction_runner} if prediction_runner else {}),
        )
        tool = _WebsiteAnalysisTool(output_dir, engine)
        response = CausalAgentRuntime(analysis_tool=tool).execute(request, columns, manifest)
        visitor_plot_path = output_dir / "website_interventional_summary.png"
        if response.status == "completed":
            if tool.last_run is None:
                raise DCFAError(
                    ErrorCode.EVIDENCE_MISMATCH,
                    "The completed website run has no validated result bundle.",
                    stage="website.presentation",
                )
            if response.queries and present_query(response.queries[0]).allow_numeric:
                if tool.last_run.bundle.distribution is not None:
                    from dcfa.distribution_reporting import (
                        distribution_markdown,
                        distribution_warning_html,
                        render_distribution_plot,
                    )

                    render_distribution_plot(
                        tool.last_run.bundle, tool.last_run.ledger, visitor_plot_path
                    )
                    compilation.trace["distribution_report"] = distribution_markdown(
                        tool.last_run.bundle.distribution, tool.last_run.bundle.queries
                    )
                    compilation.trace["distribution_warnings"] = distribution_warning_html(
                        tool.last_run.bundle
                    )
                else:
                    render_visitor_plot(
                        tool.last_run.bundle, tool.last_run.ledger, visitor_plot_path
                    )
    except Exception as exc:
        if "output_dir" in locals() and not preserve_failure:
            shutil.rmtree(output_dir, ignore_errors=True)
        if predictions_completed:
            raise WebsiteFinalizationError(str(exc)) from exc
        raise
    if not any(output_dir.iterdir()) and not preserve_failure:
        _remove_empty_reservation(output_dir)
    elif response.status == "completed":
        try:
            write_compilation_trace(output_dir, compilation.trace)
        except Exception as exc:
            if not preserve_failure:
                shutil.rmtree(output_dir, ignore_errors=True)
            raise WebsiteFinalizationError(str(exc)) from exc
    from dcfa_website_demo.daily import write_record

    measurements["analysis_and_report_seconds"] = time.perf_counter() - started
    if output_dir.is_dir():
        try:
            write_record(output_dir / "execution_measurement.json", measurements)
        except OSError as exc:
            raise WebsiteFinalizationError(
                "Execution measurement could not be saved; no refit was attempted."
            ) from exc
    return PortfolioDemoResult(
        scenario=result_scenario,
        response=response,
        plot_path=visitor_plot_path if visitor_plot_path.is_file() else None,
        output_dir=output_dir if output_dir.is_dir() else None,
        llm_trace=compilation.trace,
    )


def _status_html(result: PortfolioDemoResult) -> str:
    response = result.response
    if response.status == "blocked":
        presentation = present_error((response.error or {}).get("code"))
        return (
            '<div class="demo-status demo-status--blocked" role="status" aria-live="polite">'
            f"<strong>{html.escape(presentation.title)}</strong>"
            "No numerical result was returned.</div>"
        )
    if not response.queries or not present_query(response.queries[0]).allow_numeric:
        presentation = present_error(ErrorCode.EVIDENCE_MISMATCH)
        return (
            '<div class="demo-status demo-status--blocked" role="status" aria-live="polite">'
            f"<strong>{html.escape(presentation.title)}</strong>"
            "No numerical result is displayed.</div>"
        )
    if result.llm_trace.get("distribution_report"):
        return (
            '<div class="demo-status" role="status" aria-live="polite">'
            "<strong>Analysis completed</strong></div>"
        )
    presented = present_query(response.queries[0])
    if any(
        item.severity in {"caution", "warning"} and item.title != "Development result"
        for item in presented.warnings
    ):
        return (
            '<div class="demo-status demo-status--warning" role="status" aria-live="polite">'
            "<strong>Completed with important limitations</strong>"
            "The result passed evidence validation; review the interpretation limits.</div>"
        )
    return (
        '<div class="demo-status" role="status" aria-live="polite">'
        "<strong>Result verified</strong>"
        "The displayed value comes from the validated result bundle.</div>"
    )


_VISITOR_STAGES = (
    "Understand the question",
    "Check the data",
    "Run the analysis",
    "Verify the result",
)


def _progress_html(
    states: tuple[str, str, str, str],
    *,
    blocked_stage: int | None = None,
    blocked_title: str = "",
    blocked_action: str = "",
) -> str:
    rendered: list[str] = []
    for index, (label, state) in enumerate(zip(_VISITOR_STAGES, states, strict=True)):
        detail = ""
        if index == blocked_stage:
            detail = (
                f'<span class="state-reason">{html.escape(blocked_title)}. '
                f"{html.escape(blocked_action)}</span>"
            )
        rendered.append(f'<li class="{state}"><span>{html.escape(label)}</span>{detail}</li>')
    return '<ol class="state-graph" aria-label="Analysis progress">' + "".join(rendered) + "</ol>"


def _error_stage_index(code: str | ErrorCode | None) -> int:
    try:
        error_code = code if isinstance(code, ErrorCode) else ErrorCode(str(code))
    except ValueError:
        return 3
    if error_code in {
        ErrorCode.LLM_IMPORT_FAILED,
        ErrorCode.LLM_API_FAILED,
        ErrorCode.LLM_OUTPUT_INVALID,
    }:
        return 0
    if error_code in {
        ErrorCode.INVALID_SPECIFICATION,
        ErrorCode.MISSING_CAUSAL_ROLE,
        ErrorCode.ROLE_CONFLICT,
        ErrorCode.UNSUPPORTED_BASELINE_COVARIATES,
        ErrorCode.UNSUPPORTED_TREATMENT,
        ErrorCode.INVALID_DATA,
        ErrorCode.OUTSIDE_SUPPORT,
        ErrorCode.DATA_ACCESS_BLOCKED,
        ErrorCode.CONSTRAINT_VIOLATION,
        ErrorCode.OUTPUT_PATH_EXISTS,
    }:
        return 1
    if error_code in {
        ErrorCode.UNSUPPORTED_BACKEND_PROFILE,
        ErrorCode.BACKEND_IMPORT_FAILED,
        ErrorCode.BACKEND_LOAD_FAILED,
        ErrorCode.BACKEND_FIT_FAILED,
        ErrorCode.BACKEND_PREDICT_FAILED,
        ErrorCode.MANAGED_QUOTA_EXHAUSTED,
        ErrorCode.MANAGED_RATE_LIMITED,
        ErrorCode.MANAGED_SERVICE_FAILED,
        ErrorCode.V2_UNAVAILABLE,
        ErrorCode.V2_EXECUTION_FAILED,
    }:
        return 2
    return 3


def _blocked_progress_html(code: str | ErrorCode | None) -> str:
    stage_index = _error_stage_index(code)
    presentation = present_error(code)
    states = tuple(
        "completed" if index < stage_index else "blocked" if index == stage_index else "pending"
        for index in range(len(_VISITOR_STAGES))
    )
    return _progress_html(
        states,
        blocked_stage=stage_index,
        blocked_title=presentation.title,
        blocked_action=presentation.action,
    )


def _running_outputs() -> tuple[str, str, str, str, None]:
    """Return one stable waiting state without implying completed work or a percentage."""
    return (
        '<div class="demo-status" role="status" aria-live="polite">'
        "<strong>Analysis in progress</strong>Understanding the question before any result "
        "is shown."
        "</div>",
        _progress_html(("current", "pending", "pending", "pending")),
        "",
        "",
        None,
    )


def _state_graph_html(response: AgentResponse, llm_trace: dict[str, Any]) -> str:
    del llm_trace
    visitor_result_allowed = (
        response.status == "completed"
        and bool(response.queries)
        and present_query(response.queries[0]).allow_numeric
    )
    if visitor_result_allowed:
        return _progress_html(("completed", "completed", "completed", "completed"))
    return _blocked_progress_html((response.error or {}).get("code"))


def _answer_markdown(response: AgentResponse, llm_trace: dict[str, Any]) -> str:
    if not response.queries:
        presentation = present_error((response.error or {}).get("code"))
        return (
            "### No numerical answer\n\n"
            f"**{presentation.title}.** {presentation.explanation} {presentation.action}"
        )
    presented = present_query(response.queries[0])
    if not presented.allow_numeric:
        return (
            "### No numerical answer\n\n"
            "**Result verification failed.** Do not use a numerical result; inspect the run "
            "with the local verifier."
        )
    if llm_trace.get("distribution_report"):
        return llm_trace["distribution_report"]
    return f"### Answer\n\n**{answer_sentence(response.queries[0], llm_trace.get('proposal'))}**"


def _evidence_card_html(
    response: AgentResponse,
    *,
    show_warnings: bool = True,
    backend_access_mode: str = "unknown",
) -> str:
    if not response.queries:
        return (
            '<div class="demo-evidence-card demo-evidence-placeholder">'
            "<h3>What to do next</h3>"
            "Use the action in the answer above; no evidence record or chart was created."
            "</div>"
        )
    presented = present_query(response.queries[0])
    if not presented.allow_numeric:
        return (
            '<div class="demo-evidence-card demo-evidence-placeholder">'
            "<h3>Result details</h3>"
            "This result requires local artifact review and is not available for visitor display."
            "</div>"
        )
    support_html = (
        '<section class="demo-result-detail"><h3>Data support</h3>'
        f"<strong>{html.escape(presented.support.title)}</strong>"
        f"<p>{html.escape(presented.support.explanation)} "
        f"{html.escape(presented.support.action)}</p></section>"
    )
    visible_warnings = tuple(
        warning for warning in presented.warnings if warning.title != "Development result"
    )
    if visible_warnings:
        warning_items = "".join(
            "<li>"
            f"<strong>{html.escape(warning.title)}</strong><br>"
            f"{html.escape(warning.explanation)} {html.escape(warning.action)}"
            "</li>"
            for warning in visible_warnings
        )
        warning_html = (
            '<section class="demo-result-detail demo-evidence-warnings">'
            "<h3>Important warnings</h3>"
            f'<ul class="demo-warning-list">{warning_items}</ul></section>'
        )
    else:
        warning_html = (
            '<section class="demo-result-detail"><h3>Important warnings</h3>'
            "<p>No additional empirical warning was triggered.</p></section>"
        )
    if not show_warnings:
        warning_html = ""
    development_description = (
        "This local TabPFN v2 result is tied to the recorded checkpoint artifact, but the "
        "ZeroGPU runtime remains development-only and is not release-ready causal evidence."
        if backend_access_mode == "local_model"
        else "This managed TabPFN result is service-version-traceable, development-only, and "
        "not release-ready causal evidence."
        if backend_access_mode == "managed_client"
        else "This TabPFN result uses a recorded development-only backend profile and is not "
        "release-ready causal evidence."
    )
    development_html = (
        '<section class="demo-result-detail demo-result-detail--development">'
        "<h3>Development-only</h3>"
        f"<p>{html.escape(development_description)}</p></section>"
    )
    return (
        '<div class="demo-evidence-card demo-result-details">'
        f"{support_html}{warning_html}{development_html}</div>"
    )


def _input_error_outputs(message: str) -> tuple[str, str, str, str, None]:
    del message
    presentation = present_error(ErrorCode.INVALID_DATA)
    return (
        '<div class="demo-status demo-status--blocked" role="status" aria-live="polite">'
        f"<strong>{html.escape(presentation.title)}</strong>No workflow was run.</div>",
        _blocked_progress_html(ErrorCode.INVALID_DATA),
        f"### No numerical answer\n\n**{presentation.title}.** {presentation.explanation}",
        '<div class="demo-evidence-card demo-evidence-placeholder">'
        f"<h3>What to do next</h3>{html.escape(presentation.action)}</div>",
        None,
    )


def _execution_error_outputs(error: DCFAError) -> tuple[str, str, str, str, None]:
    presentation = present_error(error.code)
    return (
        '<div class="demo-status demo-status--blocked" role="status" aria-live="polite">'
        f"<strong>{html.escape(presentation.title)}</strong>"
        "No numerical result was returned.</div>",
        _blocked_progress_html(error.code),
        f"### No numerical answer\n\n**{presentation.title}.** {presentation.explanation}",
        '<div class="demo-evidence-card demo-evidence-placeholder">'
        f"<h3>What to do next</h3>{html.escape(presentation.action)} "
        "The workflow did not use a fallback model.</div>",
        None,
    )


def _log_operator_error(error: DCFAError) -> None:
    """Keep the typed failure diagnosable without sending its context to the browser."""
    _LOGGER.warning(
        "Website demo run stopped with code=%s at stage=%s",
        error.code.value,
        error.stage,
    )


def format_portfolio_result(
    result: PortfolioDemoResult,
) -> tuple[str, str, str, str, str | None]:
    """Project a runtime response into display-only values without recomputing numbers."""
    if result.response.error:
        _LOGGER.warning(
            "Website demo workflow blocked with code=%s at stage=%s",
            result.response.error.get("code", "unknown"),
            result.response.error.get("stage", "unknown"),
        )
    presented = present_query(result.response.queries[0]) if result.response.queries else None
    return (
        _status_html(result),
        _state_graph_html(result.response, result.llm_trace),
        (
            result.llm_trace.get("daily_summary", "")
            + "\n\n"
            + _answer_markdown(result.response, result.llm_trace)
        ),
        (
            result.llm_trace["distribution_warnings"]
            if result.llm_trace.get("distribution_report")
            else _evidence_card_html(
                result.response,
                show_warnings=True,
                backend_access_mode=str(result.llm_trace.get("backend_access_mode", "unknown")),
            )
        ),
        (
            str(result.plot_path)
            if result.plot_path is not None and presented is not None and presented.allow_numeric
            else None
        ),
    )


def resolve_build_revision() -> str:
    """Return a short local build identity without exposing a health payload."""
    configured = os.environ.get("DCFA_BUILD_REVISION", "").strip().lower()
    if _BUILD_REVISION_PATTERN.fullmatch(configured):
        return configured
    if configured == "unknown":
        return configured
    repository_root = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    revision = completed.stdout.strip().lower()
    return (
        revision
        if completed.returncode == 0 and _BUILD_REVISION_PATTERN.fullmatch(revision)
        else "unknown"
    )


def portfolio_ui_updates(
    formatted: tuple[str, str, str, str, str | None],
    *,
    buttons_enabled: bool,
    archive_path: str | None = None,
    clear_api_key: bool = True,
) -> tuple[Any, ...]:
    """Map one visitor projection to Gradio component updates."""
    import gradio as gr

    status_value, state_value, answer_value, evidence_value, plot_value = formatted
    return (
        gr.update(value=answer_value, visible=bool(answer_value)),
        gr.update(value=status_value, visible=bool(status_value)),
        gr.update(value=state_value, visible=bool(state_value)),
        gr.update(value=evidence_value, visible=bool(evidence_value)),
        gr.update(value=plot_value, visible=plot_value is not None),
        gr.update(value=archive_path, visible=archive_path is not None),
        gr.update(value="") if clear_api_key else gr.update(),
        gr.update(interactive=buttons_enabled),
        gr.update(interactive=buttons_enabled),
    )


def build_app(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    build_revision: str | None = None,
    deployment_mode: str = "managed_local",
    space_authorize_handler: Any | None = None,
    space_csv_authorize_handler: Any | None = None,
    space_scenario_handler: Any | None = None,
    space_csv_handler: Any | None = None,
    space_csv_chat_handler: Any | None = None,
    fixed_analysis_mode: str | None = None,
    presentation_title: str = "Agentic TabCF",
    local_csv_dialogue: bool = False,
) -> Any:
    """Build the optional website demo while keeping Gradio a lazy dependency."""
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError(
            "Install the website demo with: python -m pip install -r requirements-website-demo.lock"
        ) from exc

    if deployment_mode not in {"managed_local", "zerogpu_canonical", "zerogpu_duplicate"}:
        raise ValueError(f"Unsupported website deployment mode: {deployment_mode}")
    is_space = deployment_mode.startswith("zerogpu_")
    gemini_enabled = deployment_mode != "zerogpu_canonical"
    csv_enabled = True
    temporary_key_enabled = deployment_mode == "zerogpu_canonical"
    if is_space and (
        space_authorize_handler is None
        or space_csv_authorize_handler is None
        or space_scenario_handler is None
        or space_csv_handler is None
    ):
        raise ValueError("ZeroGPU deployment requires explicit authenticated event handlers.")
    from dcfa_website_demo.daily import AnalysisMode

    if fixed_analysis_mode is not None:
        fixed_analysis_mode = AnalysisMode(fixed_analysis_mode).value
    initial_mode = fixed_analysis_mode or "api_preferred"
    dialogue_enabled = is_space or local_csv_dialogue
    if local_csv_dialogue and not is_space:
        from dcfa_website_demo.local_dialogue import local_handlers

        space_authorize_handler, space_csv_chat_handler, space_csv_handler = local_handlers(
            output_root=output_root, fixed_analysis_mode=fixed_analysis_mode
        )
    scenario_choices = [(item.label, key) for key, item in SCENARIOS.items()]
    visible_revision = html.escape(build_revision or resolve_build_revision())
    with gr.Blocks(
        title=presentation_title,
        analytics_enabled=False,
        fill_width=True,
        delete_cache=(300, 900) if is_space else None,
    ) as app:
        environment_label = "ZeroGPU demo" if is_space else "Local demo"
        attribution = (
            '<p class="demo-attribution"><strong>Built with PriorLabs-TabPFN</strong> · '
            "TabPFN 3.5 API · v2 backup</p>"
            if is_space
            else ""
        )
        hero_copy = (
            "Explore a complete example report, or upload your data to start an analysis."
            if is_space
            else "Upload your data. Describe your question. Explore treatment effects."
        )
        gr.HTML(
            f"""
            <header class="demo-hero">
              <h1>{html.escape(presentation_title)}</h1>
              <p class="demo-hero-copy">
                {hero_copy}
              </p>
            </header>
            """
        )
        from dcfa_website_demo.daily import MODE_CHOICES, transfer_notice

        analysis_mode = gr.Radio(
            choices=[c for c in MODE_CHOICES if c[1] == fixed_analysis_mode]
            if fixed_analysis_mode
            else MODE_CHOICES,
            value=initial_mode,
            visible=fixed_analysis_mode is None,
            label="Analysis mode",
            elem_id="analysis-mode",
        )
        policy_notice = gr.Markdown(
            transfer_notice(
                initial_mode, v2_location="this Hugging Face Space" if is_space else None
            )
        )
        v2_status = gr.Markdown(
            "Checking v2 endpoint availability…",
            visible=not is_space and fixed_analysis_mode != "api_only",
        )
        with gr.Column(
            elem_classes=["demo-workspace", "demo-space"] if is_space else ["demo-workspace"],
            elem_id="analysis-input",
        ):
            with gr.Column(
                elem_classes="demo-input",
            ):
                with gr.Tabs(selected="saved_example" if is_space else "csv", elem_id="input-tabs"):
                    if is_space:
                        with gr.Tab("Example report", id="saved_example"):
                            from dcfa_website_demo.prepared_report import render_prepared_report

                            render_prepared_report()
                    with gr.Tab("Upload CSV", id="csv"):
                        if is_space:
                            gr.LoginButton(value="Sign in with Hugging Face", size="sm")
                        gr.Markdown(
                            "Three numeric columns: outcome, continuous treatment, "
                            "and instrument. "
                            f"{MIN_UPLOAD_ROWS}–{MAX_UPLOAD_ROWS} rows; no extra columns.",
                            elem_classes="demo-section-copy",
                        )
                        csv_file = gr.File(
                            label="Upload your CSV",
                            elem_id="csv-upload",
                            height=150,
                            file_types=[".csv"],
                            type="filepath",
                            interactive=csv_enabled,
                        )
                        csv_question = gr.Textbox(
                            value="" if dialogue_enabled else DEFAULT_CSV_QUESTION,
                            placeholder="Describe your variables and the analysis you want.",
                            label="Describe your question",
                            elem_id="csv-question",
                            info="Name the outcome, treatment, and instrument columns, "
                            "then describe the comparison you want to explore.",
                            lines=3,
                            interactive=csv_enabled,
                        )
                        with gr.Accordion("Advanced settings", open=False):
                            gr.Markdown(
                                "Leave these blank to let Gemini map the three CSV headers from "
                                "your question. An override must exactly match a header name.",
                                elem_classes="demo-section-copy",
                            )
                            with gr.Row():
                                csv_outcome = gr.Textbox(
                                    value="",
                                    label="Outcome override",
                                    placeholder="Optional exact column name",
                                    interactive=csv_enabled,
                                )
                                csv_treatment = gr.Textbox(
                                    value="",
                                    label="Treatment override",
                                    placeholder="Optional exact column name",
                                    interactive=csv_enabled,
                                )
                                csv_instrument = gr.Textbox(
                                    value="",
                                    label="Instrument override",
                                    placeholder="Optional exact column name",
                                    interactive=csv_enabled,
                                )
                            csv_seed = gr.Number(
                                value=20260813,
                                precision=0,
                                minimum=MIN_DEMO_SEED,
                                maximum=MAX_DEMO_SEED,
                                label="Analysis seed",
                                interactive=csv_enabled,
                            )
                        csv_api_key = gr.Textbox(
                            value="",
                            type="password",
                            label="Temporary Gemini API key",
                            info=(
                                "Retained in this password field during the conversation. "
                                "Cleared on report generation, reset, or after 15 idle minutes. "
                                "Never included in chat history, logs, or reports."
                            ),
                            lines=1,
                            max_lines=1,
                            visible=temporary_key_enabled,
                            interactive=temporary_key_enabled,
                        )
                        if is_space and not temporary_key_enabled:
                            gr.Markdown(
                                "This duplicate uses its owner-provided `DCFA_GEMINI_API_KEY` "
                                "Space Secret; no browser key is required.",
                                elem_classes="demo-section-copy",
                            )
                        csv_confirmed = gr.Checkbox(
                            value=False,
                            label=(
                                "I am authorized to upload this data to Hugging Face and send only "
                                "conversation text, three column names, optional role overrides, "
                                "and temporary API credential to Google Gemini; I authorize "
                                "the statistical data transfers in the selected model policy."
                                if is_space
                                else (
                                    "I authorize data use and the transfers "
                                    "in the selected model policy."
                                )
                            ),
                            interactive=csv_enabled,
                        )
                        gr.HTML(
                            '<div class="demo-transfer-note" role="note">'
                            + (
                                "<strong>Data boundary:</strong> conversation, three header names, "
                                "and optional role overrides go to Google Gemini; the temporary "
                                "key passes through Hugging Face. It is not intentionally "
                                "persisted by DCFA. Review the selected model policy above "
                                "for statistical data recipients. Temporary rows are deleted "
                                "after processing. Never upload sensitive data.</div>"
                                if is_space
                                else "<strong>Data boundary:</strong> Review the policy above. "
                                "Never upload sensitive data.</div>"
                            )
                        )
                        csv_run_button = gr.Button(
                            "Send message" if dialogue_enabled else "Run uploaded CSV",
                            variant="primary",
                            elem_id="run-csv-button",
                            interactive=csv_enabled,
                        )
                        if dialogue_enabled:
                            csv_chat = gr.Chatbot(
                                label="Prepare your analysis",
                                render_markdown=False,
                                buttons=[],
                                height=260,
                                visible=False,
                            )
                            csv_plan = gr.HTML("")
                            csv_notice = gr.Markdown("")
                            csv_generate = gr.Button(
                                "Confirm and generate report",
                                interactive=False,
                                visible=False,
                                variant="primary",
                            )
                            csv_reset = gr.Button(
                                "Reset conversation", variant="secondary", size="sm"
                            )
                    with gr.Tab(
                        "Run synthetic example" if is_space else "Try an example", id="example"
                    ):
                        if is_space:
                            gr.Markdown(
                                "Sign in on the **Upload CSV** tab before running a live example."
                            )
                        gr.Markdown(
                            "Explore a synthetic example with strong instruments, "
                            "weak instruments, "
                            "or limited support.",
                            elem_classes="demo-section-copy",
                        )
                        scenario = gr.Radio(
                            choices=scenario_choices,
                            value="strong_iv",
                            label="Guided path",
                        )
                        question = gr.Textbox(
                            value=scenario_question("strong_iv"),
                            label="Example question",
                            info=(
                                "Ask for a mean or median summary/contrast at low, center, or "
                                "high treatment. Gemini receives the question, not data rows."
                            ),
                            lines=3,
                            interactive=gemini_enabled,
                        )
                        gr.HTML(
                            '<div class="demo-transfer-note" role="note">'
                            + (
                                "<strong>Before you run:</strong> Your question text will be sent "
                                "to Google Gemini. Do not enter private or sensitive information. "
                                "Gemini receives no data rows or actual treatment values.</div>"
                                if gemini_enabled
                                else "<strong>Canonical Space:</strong> this preset uses a frozen "
                                "typed median contrast and makes no Gemini request.</div>"
                            )
                        )
                        with gr.Accordion("Reproducibility controls", open=False):
                            rows = gr.Slider(
                                MIN_DEMO_ROWS,
                                MAX_DEMO_ROWS,
                                value=128,
                                step=8,
                                label="Synthetic rows",
                            )
                            seed = gr.Number(
                                value=20260810,
                                precision=0,
                                minimum=MIN_DEMO_SEED,
                                maximum=MAX_DEMO_SEED,
                                label="Seed",
                            )
                        run_button = gr.Button(
                            "Run example",
                            variant="primary",
                            elem_id="run-demo-button",
                        )

            with gr.Column(elem_classes="demo-results", elem_id="analysis-results"):
                state_graph = gr.HTML("", visible=False)
                status = gr.HTML("", visible=False)
                plot = gr.Image(
                    type="filepath",
                    label="Estimated outcome distributions and summaries",
                    show_label=False,
                    visible=False,
                )
                answer = gr.Markdown("", visible=False, elem_classes="demo-answer")
                artifact_download = gr.File(label="Download analysis artifacts", visible=False)
                evidence = gr.HTML("", visible=False)
        gr.HTML(
            f'<footer class="demo-footer">'
            f"<span>{environment_label} · Build {visible_revision}</span>"
            f"{attribution}</footer>"
        )

        if not is_space and fixed_analysis_mode != "api_only":
            from dcfa_website_demo.v2_remote import availability_notice

            app.load(availability_notice, outputs=v2_status, api_name=False)

            def change_analysis_mode(selected_mode):
                return transfer_notice(selected_mode), gr.update(value=False)

            analysis_mode.input(
                change_analysis_mode,
                inputs=analysis_mode,
                outputs=(policy_notice, csv_confirmed),
                queue=False,
                api_name=False,
            )

        scenario.change(
            fn=scenario_question,
            inputs=scenario,
            outputs=question,
            queue=False,
            api_name=False,
        )

        def handle_run(
            selected_scenario: str,
            selected_question: str,
            selected_rows: int,
            selected_seed: int,
            selected_mode: str,
        ):
            yield (
                *portfolio_ui_updates(_running_outputs(), buttons_enabled=False),
                gr.update(interactive=False),
            )
            archive_path = None
            try:
                result = execute_portfolio_scenario(
                    selected_scenario,
                    selected_rows,
                    selected_seed,
                    question=selected_question,
                    output_root=output_root,
                    analysis_mode=fixed_analysis_mode or selected_mode,
                )
                from dcfa_website_demo.daily import archive_daily_result

                formatted = format_portfolio_result(result)
                archive_path = archive_daily_result(result)
            except DCFAError as exc:
                _log_operator_error(exc)
                formatted = _execution_error_outputs(exc)
            except (TypeError, ValueError) as exc:
                formatted = _input_error_outputs(str(exc))
            yield (
                *portfolio_ui_updates(formatted, buttons_enabled=True, archive_path=archive_path),
                gr.update(interactive=True),
            )

        result_outputs = (
            answer,
            status,
            state_graph,
            evidence,
            plot,
            artifact_download,
            csv_api_key,
            run_button,
            csv_run_button,
            analysis_mode,
        )
        if is_space:

            def show_running() -> tuple[Any, ...]:
                return (
                    *portfolio_ui_updates(
                        _running_outputs(),
                        buttons_enabled=False,
                        clear_api_key=False,
                    ),
                    gr.update(interactive=False),
                )

            authorized = run_button.click(
                fn=space_authorize_handler,
                inputs=None,
                outputs=None,
                queue=False,
                api_name=False,
            )
            authorized.success(
                fn=show_running,
                inputs=None,
                outputs=result_outputs,
                queue=False,
                api_name=False,
            ).success(
                fn=space_scenario_handler,
                inputs=(scenario, question, rows, seed, analysis_mode),
                outputs=result_outputs,
                scroll_to_output=True,
                show_progress="hidden",
                trigger_mode="once",
                api_name=False,
            )
        else:
            run_button.click(
                fn=handle_run,
                inputs=(scenario, question, rows, seed, analysis_mode),
                outputs=result_outputs,
                scroll_to_output=True,
                show_progress="hidden",
                trigger_mode="once",
                api_name=False,
            )

        def handle_csv_run(
            selected_file: str | None,
            selected_outcome: str | None,
            selected_treatment: str | None,
            selected_instrument: str | None,
            selected_confirmation: bool,
            selected_question: str,
            selected_seed: int,
            selected_mode: str,
        ):
            yield (
                *portfolio_ui_updates(_running_outputs(), buttons_enabled=False),
                gr.update(interactive=False),
            )
            archive_path = None
            try:
                if not selected_file:
                    raise ValueError("Choose a local CSV file before running the workflow.")
                result = execute_csv_upload(
                    selected_file,
                    selected_outcome,
                    selected_treatment,
                    selected_instrument,
                    selected_confirmation,
                    selected_seed,
                    question=selected_question,
                    output_root=output_root,
                    analysis_mode=fixed_analysis_mode or selected_mode,
                )
                from dcfa_website_demo.daily import archive_daily_result

                formatted = format_portfolio_result(result)
                archive_path = archive_daily_result(result)
            except DCFAError as exc:
                _log_operator_error(exc)
                formatted = _execution_error_outputs(exc)
            except (OSError, TypeError, ValueError) as exc:
                formatted = _input_error_outputs(str(exc))
            yield (
                *portfolio_ui_updates(formatted, buttons_enabled=True, archive_path=archive_path),
                gr.update(interactive=True),
            )

        csv_inputs = (
            (
                csv_file,
                csv_api_key,
                csv_outcome,
                csv_treatment,
                csv_instrument,
                csv_confirmed,
                csv_question,
                csv_seed,
                analysis_mode,
            )
            if is_space
            else (
                csv_file,
                csv_outcome,
                csv_treatment,
                csv_instrument,
                csv_confirmed,
                csv_question,
                csv_seed,
                analysis_mode,
            )
        )
        if dialogue_enabled and csv_enabled:
            from dcfa_website_demo.dialogue_ui import bind_csv_dialogue

            bind_csv_dialogue(
                app=app,
                authorize=space_authorize_handler,
                chat_handler=space_csv_chat_handler,
                execute_handler=space_csv_handler,
                components=(
                    csv_file,
                    csv_api_key,
                    csv_outcome,
                    csv_treatment,
                    csv_instrument,
                    csv_confirmed,
                    csv_question,
                    csv_seed,
                    csv_run_button,
                    csv_chat,
                    csv_plan,
                    csv_notice,
                    csv_generate,
                    csv_reset,
                ),
                result_outputs=result_outputs,
                temporary_key_enabled=temporary_key_enabled,
                analysis_mode=analysis_mode,
                policy_notice=policy_notice,
                local_session=not is_space,
                fixed_analysis_mode=fixed_analysis_mode,
            )
        elif not is_space:
            csv_run_button.click(
                fn=handle_csv_run,
                inputs=csv_inputs,
                outputs=result_outputs,
                scroll_to_output=True,
                show_progress="hidden",
                trigger_mode="once",
                api_name=False,
            )
    return app.queue(max_size=8, default_concurrency_limit=1)


def main() -> None:
    """Launch the bounded development service as a single-worker ASGI app."""
    from dcfa_website_demo.service import run_service

    run_service()


if __name__ == "__main__":
    main()
