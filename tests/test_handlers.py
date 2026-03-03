"""
Unit tests for the tools and generation Lambda handlers.

Covers:
- is_internal check (internal users see all public tools)
- Tool toggle / selected_tools filtering
- Generation API with selected tools
- Access denied for non-internal users
"""

import json
import sys
import os
import unittest
import unittest.mock as mock

# Ensure shared utilities and handlers are importable
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SHARED = os.path.join(_ROOT, "functions", "shared")
_TOOLS_DIR = os.path.join(_ROOT, "functions", "tools")
_GEN_DIR = os.path.join(_ROOT, "functions", "generation")
for _p in (_SHARED, _TOOLS_DIR, _GEN_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _make_event(is_internal=True, body=None, query_params=None):
    """Helper: build a minimal API Gateway proxy event."""
    return {
        "requestContext": {
            "authorizer": {
                "is_internal": "true" if is_internal else "false",
                "sub": "user-123",
                "email": "test@example.com",
            }
        },
        "body": json.dumps(body) if body else None,
        "queryStringParameters": query_params or {},
    }


_SAMPLE_TOOLS = [
    {"id": "tool_001", "name": "Data Analyzer", "public": True},
    {"id": "tool_002", "name": "Text Summarizer", "public": True},
    {"id": "tool_003", "name": "Code Assistant", "public": True},
]


class TestAuthUtils(unittest.TestCase):
    def setUp(self):
        from auth_utils import get_user_context
        self.get_user_context = get_user_context

    def test_internal_user_detected(self):
        event = _make_event(is_internal=True)
        ctx = self.get_user_context(event)
        self.assertTrue(ctx["is_internal"])

    def test_external_user_detected(self):
        event = _make_event(is_internal=False)
        ctx = self.get_user_context(event)
        self.assertFalse(ctx["is_internal"])

    def test_missing_authorizer_defaults_to_external(self):
        event = {"requestContext": {}}
        ctx = self.get_user_context(event)
        self.assertFalse(ctx["is_internal"])

    def test_user_fields_extracted(self):
        event = _make_event(is_internal=True)
        ctx = self.get_user_context(event)
        self.assertEqual(ctx["user_id"], "user-123")
        self.assertEqual(ctx["email"], "test@example.com")


class TestToolsHandler(unittest.TestCase):
    def _call(self, event):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tools_handler",
            os.path.join(_TOOLS_DIR, "handler.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with mock.patch.object(mod, "_load_tools", return_value=_SAMPLE_TOOLS):
            return mod.handler(event, None)

    def test_internal_user_sees_all_public_tools(self):
        event = _make_event(is_internal=True)
        resp = self._call(event)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertEqual(len(body["tools"]), 3)

    def test_external_user_gets_403(self):
        event = _make_event(is_internal=False)
        resp = self._call(event)
        self.assertEqual(resp["statusCode"], 403)

    def test_selected_tools_filter(self):
        event = _make_event(
            is_internal=True,
            query_params={"selected_tools": "tool_001,tool_003"},
        )
        resp = self._call(event)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        ids = [t["id"] for t in body["tools"]]
        self.assertIn("tool_001", ids)
        self.assertIn("tool_003", ids)
        self.assertNotIn("tool_002", ids)

    def test_empty_selected_tools_returns_all(self):
        event = _make_event(is_internal=True, query_params={})
        resp = self._call(event)
        body = json.loads(resp["body"])
        self.assertEqual(len(body["tools"]), 3)


class TestGenerationHandler(unittest.TestCase):
    def _call(self, event):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "gen_handler",
            os.path.join(_GEN_DIR, "handler.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with mock.patch.object(mod, "_load_tools", return_value=_SAMPLE_TOOLS):
            return mod.handler(event, None)

    def test_generation_with_all_tools(self):
        event = _make_event(
            is_internal=True,
            body={"prompt": "Hello world"},
        )
        resp = self._call(event)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertEqual(len(body["active_tools"]), 3)

    def test_generation_with_selected_tools(self):
        event = _make_event(
            is_internal=True,
            body={"prompt": "Hello", "selected_tools": ["tool_001"]},
        )
        resp = self._call(event)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertEqual(body["active_tools"], ["tool_001"])

    def test_generation_missing_prompt_returns_400(self):
        event = _make_event(is_internal=True, body={})
        resp = self._call(event)
        self.assertEqual(resp["statusCode"], 400)

    def test_generation_external_user_gets_403(self):
        event = _make_event(
            is_internal=False,
            body={"prompt": "Hello"},
        )
        resp = self._call(event)
        self.assertEqual(resp["statusCode"], 403)

    def test_generation_invalid_json_returns_400(self):
        event = _make_event(is_internal=True)
        event["body"] = "not-json"
        resp = self._call(event)
        self.assertEqual(resp["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
