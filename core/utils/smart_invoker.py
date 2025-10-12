import asyncio
import inspect
import logging

logger = logging.getLogger(__name__)


async def _smart_tool_invoke(
    self, tool_name: str, tool_function, params: dict, timeout: float | None
):
    """
    Call tools robustly:
      1) Try kwargs
      2) If TypeError (unexpected keyword), try single positional dict
      3) Prune to accepted names and retry kwargs
      4) If tool accepts a 'params'/'payload' style arg, wrap into it
    """
    tn = tool_name.lower()
    params = {k: v for k, v in (params or {}).items() if v is not None}

    async def _await(call):
        return await asyncio.wait_for(call, timeout=timeout or settings.timeouts.tool_default)

    # Prefer using cached dossier automatically for refactors
    if tn == "apply_refactor_smart" and not params.get("dossier"):
        cached = self.ctx.state.get("last_dossier") if self.ctx and self.ctx.state else None
        if cached:
            params["dossier"] = cached

    # -- Attempt 1: kwargs (works when function expects **kwargs / named args)
    try:
        return await _await(tool_function(**params))
    except TypeError as e:
        logger.debug("kwargs call failed for %s: %s", tool_name, e)

    # -- Attempt 2: single positional (common for tool(params_dict) or tool(dossier))
    try:
        sig = inspect.signature(tool_function)
        if len(sig.parameters) == 1:
            # for refactor tools, first try passing just dossier if we have it
            if tn == "apply_refactor_smart" and params.get("dossier") is not None:
                try:
                    return await _await(tool_function(params["dossier"]))
                except TypeError as e2:
                    logger.debug("positional dossier failed for %s: %s", tool_name, e2)
            # otherwise pass the whole params as the single payload
            return await _await(tool_function(params))
    except Exception as e:
        logger.debug("single-positional fallback failed for %s: %r", tool_name, e)

    # -- Attempt 3: prune to accepted names and retry kwargs
    try:
        accepted = set(inspect.signature(tool_function).parameters.keys())
        pruned = {k: v for k, v in params.items() if k in accepted}

        # If dossier isn't accepted by name, try common container aliases
        if tn == "apply_refactor_smart" and "dossier" in params and "dossier" not in accepted:
            for alias in ("payload", "params", "request", "input", "data"):
                if alias in accepted and alias not in pruned:
                    pruned[alias] = params["dossier"]
                    break

        if pruned:
            return await _await(tool_function(**pruned))
    except Exception as e:
        logger.debug("pruned-kwargs fallback failed for %s: %r", tool_name, e)

    # -- Attempt 4: Wrap into a single 'params' or 'payload' kw if present
    try:
        sig = inspect.signature(tool_function)
        if "params" in sig.parameters:
            return await _await(tool_function(params=params))
        if "payload" in sig.parameters:
            return await _await(tool_function(payload=params))
    except Exception as e:
        logger.debug("container-wrapper fallback failed for %s: %r", tool_name, e)

    # If we’re still here, surface a crisp error so we don’t loop
    raise TypeError(
        f"Invocation failed for tool '{tool_name}'. Sent keys: {sorted(params.keys())}. "
        f"Signature: {tool_function} -> {inspect.signature(tool_function)}",
    )
