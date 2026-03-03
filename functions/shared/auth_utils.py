"""
Shared authentication utilities for Lambda functions.

Provides helpers to extract and validate user identity from the
API Gateway request context, including the `is_internal` flag
that identifies internal users who have access to all public tools.
"""

import json


def get_user_context(event):
    """
    Extract user context from the API Gateway request event.

    The authorizer Lambda populates `requestContext.authorizer` with
    claims from the JWT.  One of those claims is `is_internal`, which
    is set to the string ``"true"`` for internal users.

    Args:
        event (dict): The raw Lambda event from API Gateway.

    Returns:
        dict: A user context dict with at least the key ``is_internal``
              (bool) and optionally ``user_id`` and ``email``.
    """
    authorizer = (
        event.get("requestContext", {})
        .get("authorizer", {})
    )

    is_internal_raw = authorizer.get("is_internal", "false")
    is_internal = str(is_internal_raw).lower() == "true"

    return {
        "user_id": authorizer.get("sub") or authorizer.get("user_id", ""),
        "email": authorizer.get("email", ""),
        "is_internal": is_internal,
    }


def build_response(status_code, body, headers=None):
    """
    Build a standard API Gateway proxy response dict.

    Args:
        status_code (int): HTTP status code.
        body (dict | list): Response payload (will be JSON-serialised).
        headers (dict | None): Optional additional response headers.

    Returns:
        dict: API Gateway proxy response.
    """
    response_headers = {"Content-Type": "application/json"}
    if headers:
        response_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": response_headers,
        "body": json.dumps(body),
    }
