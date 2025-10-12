# core/prompting/devtools.py
import asyncio
import json

from core.prompting.orchestrator import preview_lenses


async def main():
    scope = "unity.judge.decision"  # change as needed
    base = {
        "retrieval_query": "Example user question",
        "event": {"id": "dev-test"},
        "salience": {"test": 0.7},
        "affect": {"curiosity": 0.5},
    }
    report = await preview_lenses(scope, base, include_render=True, truncate_chars=500)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
