# systems/atune/salience/conformal_alpha_adapter.py
from __future__ import annotations

from systems.synapse.sdk.hints_extras import HintsExtras


async def apply_alpha_hints(
    per_head_conformal,
    default_alpha: float = 0.05,
    context: dict[str, object] | None = None,
) -> None:
    """
    Attempts to pull per-head α from Synapse and apply them.
    Degrades gracefully to a single global alpha if the gate lacks per-head support.
    Expected compat:
      - per_head_conformal.set_alpha_per_head(dict[str,float])  # preferred
      - per_head_conformal.set_alpha(float) or attribute '.alpha'
    """
    hints = await HintsExtras().alpha_per_head(default=default_alpha, context=context or {})
    try:
        if hasattr(per_head_conformal, "set_alpha_per_head") and isinstance(hints, dict) and hints:
            # If only "__default__" present, fall back to global
            if list(hints.keys()) == ["__default__"]:
                alpha = float(hints["__default__"])
                if hasattr(per_head_conformal, "set_alpha"):
                    per_head_conformal.set_alpha(alpha)  # type: ignore[attr-defined]
                else:
                    per_head_conformal.alpha = alpha  # type: ignore[attr-defined]
            else:
                per_head_conformal.set_alpha_per_head(hints)  # type: ignore[attr-defined]
            return
    except Exception:
        pass

    # Global fallback
    alpha = (
        float(hints.get("__default__"))
        if isinstance(hints, dict) and "__default__" in hints
        else float(default_alpha)
    )
    try:
        if hasattr(per_head_conformal, "set_alpha"):
            per_head_conformal.set_alpha(alpha)  # type: ignore[attr-defined]
        else:
            per_head_conformal.alpha = alpha  # type: ignore[attr-defined]
    except Exception:
        pass
