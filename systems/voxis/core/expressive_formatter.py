import re
from typing import Dict, List, Tuple

TAG_PATTERN = re.compile(r"\[(.*?)\]")


def format_llm_response(text: str) -> tuple[str, dict]:
    """Strips expressive tags from text and returns them as structured metadata."""
    metadata = {"emotion": "neutral", "pacing": "default"}
    tags = TAG_PATTERN.findall(text)

    for tag in tags:
        parts = tag.split(":")
        key = parts[0]
        value = parts[1] if len(parts) > 1 else None

        if key == "emotion":
            metadata["emotion"] = value
        # Add more mappings here for pacing, etc.

    clean_text = TAG_PATTERN.sub("", text).strip()
    return clean_text, metadata
