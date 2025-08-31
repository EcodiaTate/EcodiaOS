# core/prompting/validators.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import jsonschema  # type: ignore
except Exception:
    jsonschema = None


class SchemaValidationError(Exception):
    pass


def load_schema(path: str) -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SchemaValidationError("Schema must be a JSON object.")
    return data


def validate_json(instance: Any, schema: dict[str, Any]) -> tuple[bool, str]:
    if jsonschema is None:
        # Soft validation when lib missing
        return True, "jsonschema library not installed; skipped strict validation"
    try:
        jsonschema.validate(instance=instance, schema=schema)
        return True, "ok"
    except Exception as e:
        return False, str(e)
