# systems/axon/io/quarantine.py

from html.parser import HTMLParser
from typing import Any, Literal

from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Data Contracts for Quarantine Output
# -----------------------------------------------------------------------------


class Taint(BaseModel):
    """A structured label indicating the source and nature of untrusted data."""

    origin_type: str = Field(
        ...,
        description="The source of the taint, e.g., 'html_script_tag', 'unverified_api'.",
    )
    level: Literal["low", "medium", "high"] = Field(
        "medium",
        description="The severity of the taint.",
    )


class CanonicalizedPayload(BaseModel):
    """The structured, sanitized output of the quarantine process."""

    content_type: Literal["text", "structured_data"]
    text_blocks: list[str] = Field(
        default_factory=list,
        description="Ordered, clean text extracted from the payload.",
    )
    structured_data: dict[str, Any] | None = Field(
        None,
        description="Clean, structured data if the source was a format like JSON.",
    )
    taints: list[Taint] = Field(
        ...,
        description="A list of all taints applied during canonicalization.",
    )


# -----------------------------------------------------------------------------
# Whitelist-based HTML Sanitizer
# -----------------------------------------------------------------------------


class HTMLSanitizer(HTMLParser):
    """
    A strict, whitelist-based HTML parser that extracts clean text
    and flags potentially malicious content by applying taints.
    """

    def __init__(self, allowed_tags: set[str]):
        super().__init__()
        self.allowed_tags = allowed_tags
        self.text_blocks: list[str] = []
        self.taints: list[Taint] = []
        self._tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any):
        if tag in self.allowed_tags:
            self._tag_stack.append(tag)
        else:
            self._tag_stack.append("BLOCKED")
            self.taints.append(Taint(origin_type=f"html_disallowed_tag_{tag}", level="medium"))

    def handle_endtag(self, tag: str):
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str):
        # Only accept data if we are inside an allowed tag
        if data.strip() and self._tag_stack and self._tag_stack[-1] != "BLOCKED":
            self.text_blocks.append(data.strip())

    @classmethod
    def sanitize(cls, html_content: str, allowed_tags: set[str]) -> tuple[list[str], list[Taint]]:
        parser = cls(allowed_tags=allowed_tags)
        parser.feed(html_content)
        return parser.text_blocks, parser.taints


# -----------------------------------------------------------------------------
# Main Quarantine Class
# -----------------------------------------------------------------------------


class Quarantine:
    """
    Handles the initial processing of raw, untrusted data from drivers.
    Its purpose is to sanitize, canonicalize, and apply taint before
    the data is allowed to become a formal AxonEvent.
    """

    def __init__(
        self,
        html_allowed_tags: set[str] = {
            "p",
            "b",
            "i",
            "strong",
            "em",
            "h1",
            "h2",
            "h3",
            "li",
            "ul",
            "ol",
            "a",
        },
    ):
        self.html_allowed_tags = html_allowed_tags

    def process_and_canonicalize(self, raw_payload: Any, mime_type: str) -> CanonicalizedPayload:
        """
        Processes a raw payload according to its MIME type, returning a
        structured, sanitized, and tainted representation.
        """
        if "html" in mime_type:
            return self._canonicalize_html(raw_payload)
        elif "json" in mime_type:
            return self._canonicalize_json(raw_payload)
        else:  # Default to plain text handling
            return self._canonicalize_text(raw_payload)

    def _canonicalize_html(self, payload: Any) -> CanonicalizedPayload:
        if not isinstance(payload, str):
            return CanonicalizedPayload(
                content_type="text",
                text_blocks=[f"Error: HTML payload was not a string, but {type(payload)}"],
                taints=[Taint(origin_type="invalid_html_payload_type", level="high")],
            )

        text_blocks, taints = HTMLSanitizer.sanitize(payload, self.html_allowed_tags)
        taints.append(Taint(origin_type="source_html", level="low"))

        return CanonicalizedPayload(content_type="text", text_blocks=text_blocks, taints=taints)

    def _canonicalize_json(self, payload: Any) -> CanonicalizedPayload:
        taints = [Taint(origin_type="source_json", level="low")]
        if not isinstance(payload, dict):
            return CanonicalizedPayload(
                content_type="structured_data",
                structured_data={"error": f"JSON payload was not a dict, but {type(payload)}"},
                taints=[Taint(origin_type="invalid_json_payload_type", level="high")],
            )

        return CanonicalizedPayload(
            content_type="structured_data",
            structured_data=payload,  # Assuming JSON is already clean data
            taints=taints,
        )

    def _canonicalize_text(self, payload: Any) -> CanonicalizedPayload:
        if not isinstance(payload, str):
            return CanonicalizedPayload(
                content_type="text",
                text_blocks=[f"Error: Text payload was not a string, but {type(payload)}"],
                taints=[Taint(origin_type="invalid_text_payload_type", level="high")],
            )

        return CanonicalizedPayload(
            content_type="text",
            text_blocks=[payload.strip()],
            taints=[Taint(origin_type="source_text", level="low")],
        )
