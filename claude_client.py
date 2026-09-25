"""Shared helpers for calling Claude across this project (digest analysis,
fund explanations, ...) — extracted so the ThinkingBlock/JSON-fence gotchas
are handled in exactly one place."""

import json


def extract_text(response) -> str:
    # claude-sonnet-5 may emit a ThinkingBlock before the text block —
    # never assume content[0] is the text (same gotcha as the video pipeline).
    for block in response.content:
        if block.type == "text":
            return block.text
    raise RuntimeError("No text block in Claude response")


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json").strip()
    # strict=False: Claude sometimes emits a literal newline/tab inside a
    # JSON string value (e.g. a multi-sentence thesis) instead of an
    # escaped \n — strict JSON parsing rejects that with "Invalid control
    # character" (two real production failures, 2026-09-21, both digests).
    # Python's json module supports exactly this relaxation deliberately.
    return json.loads(text, strict=False)


def require_complete(response):
    """Raise if the response was truncated — callers should always check
    this before trusting extract_text/parse_json (see the max_tokens
    gotcha in CLAUDE.md: thinking tokens eat into the budget too)."""
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude response truncated (max_tokens) — raise the budget")
