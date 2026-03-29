# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Token usage tracking and cost estimation for ReplicantX LLM calls.

Loads pricing from model_pricing.json (bundled with the package) and
supports per-scenario overrides declared in YAML under
``model_pricing_overrides``.  The tracker accumulates usage from every
PydanticAI call in a scenario run and emits a :class:`TokenUsageSummary`.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import ModelPricingOverride, ModelTokenUsage, TokenUsageSummary

# Resolve the bundled pricing file relative to this module.
_PRICING_JSON_PATH = Path(__file__).parent.parent.parent / "model_pricing.json"


def _load_pricing_table() -> Dict[str, Dict[str, float]]:
    """Load active model pricing from model_pricing.json.

    Returns a dict keyed by model identifier (no provider prefix) with
    ``{"input": <float>, "output": <float>}`` values (cost per million tokens).
    """
    try:
        data = json.loads(_PRICING_JSON_PATH.read_text(encoding="utf-8"))
        return {
            entry["model_identifier"]: {
                "input": float(entry["input_cost_per_million"]),
                "output": float(entry["output_cost_per_million"]),
            }
            for entry in data.get("model_pricing", [])
            if entry.get("is_active", True)
        }
    except Exception:
        return {}


def normalize_model_name(model: str) -> str:
    """Strip provider prefix so ``openai:gpt-4o`` becomes ``gpt-4o``."""
    return model.split(":", 1)[1] if ":" in model else model


class TokenUsageTracker:
    """Accumulates LLM token usage across a scenario run and estimates cost.

    Usage
    -----
    Create one tracker per scenario run, then call :meth:`record_pydantic_usage`
    after each PydanticAI ``agent.run(...)`` call.  At the end of the run,
    call :meth:`get_summary` to obtain a :class:`TokenUsageSummary` suitable
    for attaching to a :class:`ScenarioReport`.

    Parameters
    ----------
    pricing_overrides:
        Optional per-model overrides loaded from ``model_pricing_overrides``
        in the scenario YAML.  Keys can include or omit the provider prefix.
    """

    def __init__(
        self,
        pricing_overrides: Optional[Dict[str, "ModelPricingOverride"]] = None,
    ) -> None:
        self._pricing_table = _load_pricing_table()
        self._overrides: Dict[str, ModelPricingOverride] = pricing_overrides or {}
        # Each record: (model_name, input_tokens, output_tokens, purpose)
        self._records: List[tuple] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        purpose: str = "",
    ) -> None:
        """Record raw token counts for one LLM call."""
        self._records.append((model, max(0, input_tokens), max(0, output_tokens), purpose))

    def record_pydantic_usage(
        self,
        model: str,
        usage: Any,
        purpose: str = "",
    ) -> None:
        """Record token usage from a PydanticAI ``RunResult.usage()`` object.

        Handles ``None`` gracefully (e.g. when using the ``test`` model).
        """
        if usage is None:
            return
        input_tokens = int(getattr(usage, "request_tokens", None) or 0)
        output_tokens = int(getattr(usage, "response_tokens", None) or 0)
        if input_tokens == 0 and output_tokens == 0:
            return
        self.record(model, input_tokens, output_tokens, purpose)

    def get_summary(self) -> TokenUsageSummary:
        """Compute and return the aggregated token usage summary."""
        # Aggregate by (model, purpose) pair
        agg: Dict[str, Dict[str, Any]] = {}
        has_unknown = False

        for model, input_tok, output_tok, purpose in self._records:
            key = f"{model}::{purpose}"
            if key not in agg:
                agg[key] = {
                    "model": model,
                    "purpose": purpose,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "call_count": 0,
                }
            pricing = self._get_pricing(model)
            if pricing is None:
                has_unknown = True
                cost = 0.0
            else:
                cost = (
                    input_tok * pricing["input"] + output_tok * pricing["output"]
                ) / 1_000_000

            agg[key]["input_tokens"] += input_tok
            agg[key]["output_tokens"] += output_tok
            agg[key]["cost_usd"] += cost
            agg[key]["call_count"] += 1

        by_model = [
            ModelTokenUsage(
                model=v["model"],
                purpose=v["purpose"],
                input_tokens=v["input_tokens"],
                output_tokens=v["output_tokens"],
                total_tokens=v["input_tokens"] + v["output_tokens"],
                cost_usd=round(v["cost_usd"], 8),
                call_count=v["call_count"],
            )
            for v in agg.values()
        ]

        total_input = sum(r.input_tokens for r in by_model)
        total_output = sum(r.output_tokens for r in by_model)
        total_cost = sum(r.cost_usd for r in by_model)

        source = "model_pricing.json"
        if self._overrides:
            source += " (with YAML overrides)"

        return TokenUsageSummary(
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_tokens=total_input + total_output,
            total_cost_usd=round(total_cost, 8),
            by_model=by_model,
            pricing_source=source,
            has_unknown_models=has_unknown,
        )

    def merge(self, other: "TokenUsageTracker") -> None:
        """Merge records from another tracker into this one."""
        self._records.extend(other._records)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_pricing(self, model: str) -> Optional[Dict[str, float]]:
        """Return pricing dict for *model*, checking YAML overrides first."""
        normalized = normalize_model_name(model)
        for key in (model, normalized):
            if key in self._overrides:
                override = self._overrides[key]
                return {
                    "input": override.input_cost_per_million,
                    "output": override.output_cost_per_million,
                }
        return self._pricing_table.get(normalized)
