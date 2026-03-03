# Architecture Overview

## Summary

This repository contains the serverless infrastructure for the AI tools platform.
The architecture consists of an API Gateway fronting two Lambda functions and a
demo database.  It implements **row-based access control (RBAC)** so that each
user only interacts with the tools they are permitted to use.

---

## Key Design Decisions

### 1. All tools are public

Every tool in `data/tools.json` carries `"public": true`.  This removes the
need for per-tool ACL rules while the JWT claims (organisation ID, team
membership) are still pending review.

### 2. Internal-user detection via `is_internal`

The authorizer Lambda populates `requestContext.authorizer.is_internal` from
the login logic.  Both the Tools and Generation Lambda handlers check this
flag before returning any data:

- `is_internal == true`  → full access to all public tools
- `is_internal == false` → `403 Access Denied`

```python
# functions/shared/auth_utils.py
is_internal_raw = authorizer.get("is_internal", "false")
is_internal = str(is_internal_raw).lower() == "true"
```

### 3. Tool toggle handled in the SDK

When a user toggles a tool **off** in the UI, the SDK passes only the
remaining **enabled** tool IDs to the API.  Both Lambda handlers honour this
list:

**Tools API** (query-string):
```
GET /tools?selected_tools=tool_001,tool_003
```

**Generation API** (request body):
```json
POST /generate
{
  "prompt": "Summarise this document",
  "selected_tools": ["tool_002"]
}
```

If `selected_tools` is omitted or empty, all public tools are used.

---

## Project Structure

```
data/
  tools.json              # Tool registry – all tools marked public: true

functions/
  shared/
    auth_utils.py         # is_internal check + response helpers
  tools/
    handler.py            # GET /tools  – list available tools
  generation/
    handler.py            # POST /generate – run generation with selected tools

tests/
  test_handlers.py        # Unit tests for both handlers and auth utils
```

---

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```
