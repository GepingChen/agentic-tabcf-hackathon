"""Notebook-native adapter for the bounded user-owned Colab workflow."""

from dcfa_colab.workflow import ColabRunResult, preflight_colab_csv, run_colab_analysis

__all__ = ["ColabRunResult", "preflight_colab_csv", "run_colab_analysis"]
