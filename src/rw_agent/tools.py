from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Static, speed-focused system prompt — never mutated mid-session to maximize KV/prefix cache hits.
SYSTEM_PROMPT = (
    "You are rw, an ultra-fast file agent with only two tools: read and write.\n"
    "Rules:\n"
    "- Act immediately. Call read/write directly without preamble.\n"
    "- Keep replies minimal: 1-3 short lines stating what you found or changed.\n"
    "- Read before editing if you don't know the file's contents. Never invent contents.\n"
    "- No filler, no restating the request."
)

# Static, compact tool schemas (2 tools only) — constant prefix for prompt caching.
TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a text file with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "offset": {"type": "integer", "description": "1-based start line (default 1)"},
                    "limit": {"type": "integer", "description": "Max lines (default 200)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write or overwrite a file with content (creates parent dirs).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Full file content"},
                },
                "required": ["path", "content"],
            },
        },
    },
]

MAX_OUTPUT_CHARS = 24_000


def exec_read(path: str, offset: int = 1, limit: int = 200) -> tuple[str, str]:
    """Return (tool_result_text, short_ui_summary)."""
    p = Path(path).expanduser()
    if not p.exists():
        return f"Error: file not found: {path}", "not found"
    if p.is_dir():
        return f"Error: {path} is a directory", "is a directory"

    try:
        raw = p.read_bytes()
    except OSError as e:
        return f"Error reading {path}: {e}", f"error: {e}"

    if b"\x00" in raw[:4096]:
        return f"Error: binary file ({len(raw)} bytes): {path}", f"binary ({len(raw)}B)"

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    total = len(lines)
    start = max(1, int(offset or 1))
    count = max(1, min(int(limit or 200), 1000))
    chunk = lines[start - 1 : start - 1 + count]

    formatted = "\n".join(f"{start + i}|{line}" for i, line in enumerate(chunk))
    if len(formatted) > MAX_OUTPUT_CHARS:
        formatted = formatted[:MAX_OUTPUT_CHARS] + "\n...[truncated]"

    end_line = start + len(chunk) - 1 if chunk else start - 1
    header = f"[{path} lines {start}-{end_line}/{total}]\n"
    return header + formatted, f"{len(chunk)}/{total} lines"


def exec_write(path: str, content: str) -> tuple[str, str]:
    """Return (tool_result_text, short_ui_summary)."""
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"Error writing {path}: {e}", f"error: {e}"

    n_lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    n_bytes = len(content.encode("utf-8"))
    return f"Wrote {path} ({n_lines} lines, {n_bytes} bytes)", f"{n_lines} lines, {n_bytes}B"


def run_tool(name: str, raw_args: str) -> tuple[str, str, str]:
    """Execute read or write. Returns (result_text, target_path, short_ui_summary)."""
    try:
        args = json.loads(raw_args) if raw_args.strip() else {}
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON arguments: {e}", "?", "invalid args"

    path = str(args.get("path", ""))
    if name == "read":
        res, summary = exec_read(
            path=path,
            offset=args.get("offset", 1),
            limit=args.get("limit", 200),
        )
        return res, path, summary
    if name == "write":
        res, summary = exec_write(
            path=path,
            content=str(args.get("content", "")),
        )
        return res, path, summary
    return f"Error: unknown tool '{name}'", path, "unknown tool"
