"""
Tools Lambda handler.

Returns the list of available tools to the caller.  All tools are
stored with ``public: true`` so that any authenticated internal user
can discover and use them.  The `is_internal` claim (populated by the
authorizer from the login logic) is used to gate access:

* **Internal users** (``is_internal == true``) – receive every tool
  that has ``public: true``.
* **External / unauthenticated users** – receive an empty list until
  further access-control rules are introduced.

If the caller supplies a ``selected_tools`` query-string parameter
(a comma-separated list of tool IDs), only those tools are returned.
This mirrors the SDK-side toggle: the SDK passes only the tools the
user has left enabled.
"""

import json
import os
import sys

# Allow shared utilities to be imported when the handler is invoked by
# the Lambda runtime (where /var/task is on sys.path) or during tests.
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


def handler(event, context):
    """
    Lambda entry-point for the tools listing API.

    Args:
        event (dict): API Gateway proxy event.
        context (LambdaContext): Lambda execution context (unused).

    Returns:
        dict: API Gateway proxy response containing the list of tools
              the requesting user is allowed to see.
    """
    user = get_user_context(event)

    if not user["is_internal"]:
        return build_response(
            403,
            {"message": "Access denied: internal users only"},
        )

    all_tools = _load_tools()
    public_tools = [t for t in all_tools if t.get("public", False)]

    # Apply SDK-side tool toggle: if the caller specified a subset of
    # tool IDs (e.g. because the user toggled some tools off in the UI),
    # return only those tools.
    params = event.get("queryStringParameters") or {}
    selected_raw = params.get("selected_tools", "")
    if selected_raw:
        selected_ids = {tid.strip() for tid in selected_raw.split(",") if tid.strip()}
        public_tools = [t for t in public_tools if t["id"] in selected_ids]

    return build_response(200, {"tools": public_tools})
