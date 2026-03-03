"""
Generation Lambda handler.

Accepts a user prompt and an optional list of selected tool IDs from
the SDK.  Only the tools the user has enabled (i.e. not toggled off)
are forwarded to the generation back-end, implementing the row-based
access-control requirement at the SDK layer:

    "we can pass the tools they selected using SDK and then only
     that's the generation API to use those tools."
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.join(_HERE, "..", "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from auth_utils import build_response, get_user_context  # noqa: E402

_TOOLS_FILE = os.path.join(
    os.path.dirname(_HERE), "data", "tools.json"
)


def _load_tools():
    """Load tool definitions from the bundled JSON file."""
    with open(_TOOLS_FILE, "r") as fh:
        return json.load(fh)


def _resolve_tools(requested_ids):
    """
    Return the subset of public tools whose IDs are in *requested_ids*.

    If *requested_ids* is empty, all public tools are returned (i.e.
    the user left all toggles enabled).
    """
    all_tools = _load_tools()
    public_tools = [t for t in all_tools if t.get("public", False)]

    if not requested_ids:
        return public_tools

    id_set = set(requested_ids)
    return [t for t in public_tools if t["id"] in id_set]


def handler(event, context):
    """
    Lambda entry-point for the generation API.

    Expected request body (JSON):
        {
            "prompt": "<user prompt>",
            "selected_tools": ["tool_001", "tool_003"]   // optional
        }

    If ``selected_tools`` is omitted or empty, all public tools are
    used.  If the user has toggled some tools off, the SDK passes only
    the remaining enabled tool IDs here.

    Args:
        event (dict): API Gateway proxy event.
        context (LambdaContext): Lambda execution context (unused).

    Returns:
        dict: API Gateway proxy response with the generation result.
    """
    user = get_user_context(event)

    if not user["is_internal"]:
        return build_response(
            403,
            {"message": "Access denied: internal users only"},
        )

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return build_response(400, {"message": "Invalid JSON body"})

    prompt = body.get("prompt", "").strip()
    if not prompt:
        return build_response(400, {"message": "prompt is required"})

    selected_tool_ids = body.get("selected_tools") or []
    active_tools = _resolve_tools(selected_tool_ids)

    # --- placeholder: invoke your actual generation back-end here ---
    result = {
        "prompt": prompt,
        "active_tools": [t["id"] for t in active_tools],
        "message": (
            f"Generation request received with {len(active_tools)} active tool(s)."
        ),
    }

    return build_response(200, result)
