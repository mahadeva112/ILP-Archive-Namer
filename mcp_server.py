"""ILP Archive Namer - MCP server.

Exposes the naming engine to MCP clients (Claude Code, Claude Desktop, ...)
over stdio, so an assistant can build and check archive names with exactly
the same rules as the app. Nothing here decides anything about naming: every
tool is a thin wrapper over namer.engine.

Standard library only, like the rest of the app. Every tool is read-only:
none of them creates, moves or renames anything on disk.

    python mcp_server.py        speak MCP (JSON-RPC 2.0, one message per line)
                                on stdin/stdout

Register it with Claude Code:

    claude mcp add ilp-archive-namer -- python "<path>\\mcp_server.py"
"""
import io
import json
import os
import socket
import sys
import traceback
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from namer import SPEC_REVISION, __version__, engine
from namer.registry import REGISTRY
from namer.slug import clean_title, slugify
from server import extract_video_id, fetch_youtube_title

SERVER_NAME = "ilp-archive-namer"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = (
    "Builds and checks folder/file names for archiving ILP (Isha) content, "
    "following 'How to archive ILP content' (%s). Call list_categories first "
    "to see the eight categories and the field keys each needs, and "
    "list_codes for valid channel, department and language codes. Dates are "
    "yyyy-mm-dd, months are yyyy-mm, languages are 3-letter ISO 639-2/B "
    "codes (hin, tel, tam...). Use check_name on a name that already exists. "
    "Report names exactly as returned - never retype or 'tidy' them."
    % SPEC_REVISION)


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------

def _category_ids():
    return [c.id for c in engine.CATEGORIES]


def tool_list_categories(args):
    return {"spec_revision": SPEC_REVISION,
            "categories": [c.meta() for c in engine.CATEGORIES]}


def tool_list_codes(args):
    kind = (args.get("kind") or "all").lower()
    out = {}
    if kind in ("all", "channels"):
        out["channels"] = REGISTRY.channels
    if kind in ("all", "departments"):
        out["departments"] = REGISTRY.departments
    if kind in ("all", "languages"):
        out["languages"] = REGISTRY.languages
    if not out:
        raise ToolError("kind must be one of: all, channels, departments, "
                        "languages")
    return out


def tool_build_name(args):
    category = args.get("category")
    fields = dict(args.get("fields") or {})
    # The app's UI accepts a pasted URL in the video field; so does this.
    vid = fields.get("video_id")
    if isinstance(vid, str) and "/" in vid:
        fields["video_id"] = extract_video_id(vid)[0]
    try:
        return engine.build(category, fields)
    except engine.SpecError as exc:
        raise ToolError(str(exc))


def tool_check_name(args):
    name = args.get("name")
    if not name:
        raise ToolError("name is required")
    return engine.parse_name(name)


def tool_slugify_title(args):
    title = args.get("title") or ""
    cleaned = clean_title(title)
    return {"cleaned": cleaned,
            "slug": slugify(cleaned, bool(args.get("force_title_case")))}


def tool_lookup_video(args):
    raw = args.get("url") or ""
    vid, platform, channel = extract_video_id(raw)
    out = {"video_id": vid, "platform": platform, "suggested_channel": channel,
           "title": "", "slug": "", "note": ""}
    if not vid:
        out["note"] = "Nothing recognised in that input."
    elif platform == "YT":
        try:
            meta = fetch_youtube_title(vid)
            out["title_raw"] = meta.get("title") or ""
            out["title"] = clean_title(out["title_raw"])
            out["slug"] = slugify(out["title"])
            out["author"] = meta.get("author") or ""
        except (urllib.error.URLError, urllib.error.HTTPError,
                socket.timeout, TimeoutError, ValueError) as exc:
            out["note"] = ("Could not reach YouTube to fetch the title (%s)."
                           % type(exc).__name__)
    elif platform == "IG":
        out["note"] = ("Instagram does not expose captions without login - "
                       "the description must come from the caption by hand.")
    else:
        out["note"] = "Treated as a bare video code."
    return out


_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False,
              "idempotentHint": True, "openWorldHint": False}

TOOLS = [
    {
        "name": "list_categories",
        "title": "List naming categories",
        "description": (
            "The eight archive naming categories with their spec reference, "
            "an example name, the NAS destination, and the fields each one "
            "needs (key, label, type, required, default). Field types: "
            "'date' = yyyy-mm-dd, 'month' = yyyy-mm, 'lang' = 3-letter code, "
            "'channel'/'department' = a code from list_codes, 'select' = one "
            "of the listed option values."),
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": _READ_ONLY,
        "fn": tool_list_categories,
    },
    {
        "name": "list_codes",
        "title": "List registered codes",
        "description": "Registered channel, department and language codes.",
        "inputSchema": {
            "type": "object",
            "properties": {"kind": {
                "type": "string",
                "enum": ["all", "channels", "departments", "languages"],
                "default": "all"}},
        },
        "annotations": _READ_ONLY,
        "fn": tool_list_codes,
    },
    {
        "name": "build_name",
        "title": "Build an archive name",
        "description": (
            "Build the spec-compliant folder name (and inner file names) for "
            "one item. Returns folder, files, segments, NAS route and "
            "issues; ok=false means at least one issue is an error. Field "
            "keys come from list_categories. A video_id may be a full "
            "YouTube/Instagram URL."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": _category_ids()},
                "fields": {
                    "type": "object",
                    "description": (
                        "Field values by key, e.g. {\"channel\": \"SGYT\", "
                        "\"lang\": \"hin\", \"video_id\": \"xVbcVQApKig\", "
                        "\"title\": \"A Lesson From Guru Nanak\", "
                        "\"date\": \"2021-07-09\"}. Optional extras: "
                        "force_title_case (bool), voices (int, default 2)."),
                    "additionalProperties": True,
                },
            },
            "required": ["category", "fields"],
        },
        "annotations": _READ_ONLY,
        "fn": tool_build_name,
    },
    {
        "name": "check_name",
        "title": "Check an existing name",
        "description": (
            "Check a folder name that already exists. 'matched' is the "
            "category it truly is; when it breaks the rules, 'matched' is "
            "null, 'reads_as' is the category it was evidently meant to be, "
            "and 'suggestion' may hold a corrected name. 'issues' lists every "
            "rule broken."),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "annotations": _READ_ONLY,
        "fn": tool_check_name,
    },
    {
        "name": "slugify_title",
        "title": "Turn a title into a name slug",
        "description": (
            "Turn an English title into the hyphenated Title-Case slug used "
            "inside names (transliterated, forbidden characters removed)."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "force_title_case": {"type": "boolean", "default": False},
            },
            "required": ["title"],
        },
        "annotations": _READ_ONLY,
        "fn": tool_slugify_title,
    },
    {
        "name": "lookup_video",
        "title": "Look up a video URL",
        "description": (
            "Extract the video code and platform from a YouTube, Instagram "
            "or Facebook URL, suggest a channel, and for YouTube fetch the "
            "public title (one request to youtube.com oEmbed)."),
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        "annotations": dict(_READ_ONLY, openWorldHint=True),
        "fn": tool_lookup_video,
    },
]

TOOL_BY_NAME = dict((t["name"], t) for t in TOOLS)


class ToolError(Exception):
    """A refusal the caller should read, not a server fault."""


# --------------------------------------------------------------------------
# JSON-RPC plumbing
# --------------------------------------------------------------------------

class RpcError(Exception):
    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


def _tool_result(payload, is_error=False):
    text = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, indent=2)
    out = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if isinstance(payload, dict) and not is_error:
        out["structuredContent"] = payload
    return out


def handle(method, params):
    if method == "initialize":
        asked = (params or {}).get("protocolVersion")
        version = asked if asked in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "ILP Archive Namer",
                           "version": __version__},
            "instructions": INSTRUCTIONS,
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [dict((k, v) for k, v in t.items() if k != "fn")
                          for t in TOOLS]}
    if method == "tools/call":
        name = (params or {}).get("name")
        tool = TOOL_BY_NAME.get(name)
        if not tool:
            raise RpcError(-32602, "Unknown tool: %r" % name)
        args = (params or {}).get("arguments") or {}
        try:
            return _tool_result(tool["fn"](args))
        except ToolError as exc:
            return _tool_result(str(exc), is_error=True)
        except Exception as exc:  # report it to the model, keep serving
            return _tool_result("Unexpected error: %s" % exc, is_error=True)
    raise RpcError(-32601, "Method not found: %s" % method)


def serve(stdin, stdout, log):
    def send(msg):
        stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        stdout.flush()

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            send({"jsonrpc": "2.0", "id": None,
                  "error": {"code": -32700, "message": "Parse error"}})
            continue
        if not isinstance(msg, dict) or "method" not in msg:
            continue                      # a response to us; we send no requests
        is_request = "id" in msg
        try:
            result = handle(msg["method"], msg.get("params"))
            if is_request:
                send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
        except RpcError as exc:
            if is_request:
                send({"jsonrpc": "2.0", "id": msg["id"],
                      "error": {"code": exc.code, "message": exc.message}})
        except Exception as exc:
            traceback.print_exc(file=log)
            if is_request:
                send({"jsonrpc": "2.0", "id": msg["id"],
                      "error": {"code": -32603, "message": str(exc)}})


def main():
    # stdout carries protocol messages only; UTF-8 and \n regardless of the
    # Windows console code page.
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
    serve(stdin, stdout, sys.stderr)


if __name__ == "__main__":
    main()
