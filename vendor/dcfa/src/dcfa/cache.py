"""Validated in-process result cache for no-refit follow-up queries."""

from __future__ import annotations

from dataclasses import replace

from dcfa.errors import DCFAError, ErrorCode
from dcfa.evidence import EvidenceLedger, validate_bundle_evidence
from dcfa.schemas import ResultBundle


class ResultCache:
    def __init__(self) -> None:
        self._bundles: dict[str, tuple[ResultBundle, EvidenceLedger]] = {}

    def put(self, cache_key: str, bundle: ResultBundle, ledger: EvidenceLedger) -> None:
        validate_bundle_evidence(bundle, ledger)
        current = self._bundles.get(cache_key)
        if current is not None and current[0].result_bundle_id != bundle.result_bundle_id:
            raise DCFAError(
                ErrorCode.CACHE_MISMATCH,
                "A cache key cannot be rebound to a different result bundle.",
                stage="cache.put",
                context={"cache_key": cache_key},
            )
        self._bundles[cache_key] = (bundle, ledger)

    def get(self, cache_key: str) -> tuple[ResultBundle, EvidenceLedger] | None:
        cached = self._bundles.get(cache_key)
        if cached is None:
            return None
        bundle, ledger = cached
        validate_bundle_evidence(bundle, ledger)
        return replace(bundle, cached=True), ledger
