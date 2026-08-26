"""P3-06 recommended-action framework.

Actions are looked up from a fixed, versioned, machine-readable catalogue --
never generated dynamically by a model or an LLM. Every returned action
preserves why it was triggered (risk type, risk level, reason codes) so it
remains traceable and auditable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_CATALOG = json.loads((ROOT / "operational" / "config" / "action_catalog.json").read_text(encoding="utf-8"))
CATALOG_VERSION = _CATALOG["version"]

_BY_KEY: dict[tuple[str, str], list[dict[str, Any]]] = {}
for _action in _CATALOG["actions"]:
    _BY_KEY.setdefault((_action["risk_type"], _action["risk_level"]), []).append(_action)


def recommended_actions(risk_type: str, risk_level: str, reason_codes: list[str]) -> list[dict[str, Any]]:
    """Deterministic lookup: no action text is generated on the fly."""
    if risk_level == "NORMAL":
        return []
    matched = _BY_KEY.get((risk_type, risk_level), [])
    return [
        {
            **action,
            "why_triggered": {
                "risk_type": risk_type,
                "risk_level": risk_level,
                "reason_codes": reason_codes,
            },
            "catalogue_version": CATALOG_VERSION,
        }
        for action in matched
    ]
