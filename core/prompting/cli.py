# core/prompting/cli.py
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from core.prompting.orchestrator import PolicyHint, build_prompt


def _load_json_maybe(path_or_json: str | None) -> Any:
    if not path_or_json:
        return None
    p = Path(path_or_json)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    # not a file: try parsing as raw JSON string
    return json.loads(path_or_json)


def _ensure_context(ctx: Dict[str, Any] | None) -> Dict[str, Any]:
    ctx = dict(ctx or {})
    ctx.setdefault("vars", {})
    ctx.setdefault("facts", {})
    return ctx


def cmd_render(args: argparse.Namespace) -> int:
    # Load context (file or JSON string)
    raw_ctx = _load_json_maybe(args.context)
    ctx = _ensure_context(raw_ctx)

    # Optional: inject tool specs into context.vars.tool_specs
    tools = _load_json_maybe(args.tools)
    if tools is not None:
        # allow either a list of dicts or a JSON string; templates will |tojson it
        ctx["vars"]["tool_specs"] = tools
        ctx["vars"]["tool_specs_json"] = tools  # for templates expecting *_json
        ctx["tool_specs_json"] = tools          # flat fallback

    # Optional: set a human summary (used by some templates)
    summary = args.summary or f"Render prompt for scope={args.scope}"

    hint = PolicyHint(scope=args.scope, context=ctx, summary=summary)
    prompt_data = _safe_await(build_prompt(hint))

    if args.out:
        Path(args.out).write_text(json.dumps({
            "messages": prompt_data.messages,
            "provider_overrides": prompt_data.provider_overrides,
            "provenance": prompt_data.provenance,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps({
            "messages": prompt_data.messages,
            "provider_overrides": prompt_data.provider_overrides,
            "provenance": prompt_data.provenance,
        }, ensure_ascii=False, indent=2))

    return 0


def _safe_await(coro):
    # Allow running as a module without bringing in trio/anyio;
    # reuse an event loop if one exists (e.g., in embedded contexts).
    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # In a running loop we need to schedule and wait
            from asyncio import ensure_future
            fut = ensure_future(coro)
            # crude: spin until done (CLI usage only)
            while not fut.done():
                loop.run_until_complete(asyncio.sleep(0.01))
            return fut.result()
        return asyncio.run(coro)
    except Exception as e:
        print(f"CLI render failed: {e!r}", file=sys.stderr)
        raise


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m core.prompting.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Render a prompt for a given scope.")
    r.add_argument("--scope", required=True, help="Template scope (e.g., simula.react.step)")
    r.add_argument("--context", help="Path to JSON file or raw JSON string for the context dict")
    r.add_argument("--tools", help="Path to JSON file or raw JSON (list/dict) for tool specs")
    r.add_argument("--summary", help="Optional human summary for provenance")
    r.add_argument("--out", help="Write rendered prompt JSON to this path")

    args = ap.parse_args(argv)

    if args.cmd == "render":
        return cmd_render(args)

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
