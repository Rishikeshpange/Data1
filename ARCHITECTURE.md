# Architecture: Angular Studio → Python Backend → MCP Server → IMO Tools

> **POC timeline:** 3–4 days  
> **Author / implementer:** Rishikesh Pange  
> **Status:** Draft

---

## Table of Contents

1. [Overview](#overview)
2. [Components and Responsibilities](#components-and-responsibilities)
3. [Sequence Flow – Chat Request](#sequence-flow--chat-request)
4. [Session Handling: Agent Core vs Custom Memory](#session-handling-agent-core-vs-custom-memory)
5. [Assumptions](#assumptions)
6. [Backend API Endpoints](#backend-api-endpoints)
7. [Data Structures](#data-structures)
8. [Deployment Notes](#deployment-notes)
9. [Rishikesh's Task List](#rishikeshs-task-list)
10. [Open Questions / Next Decisions](#open-questions--next-decisions)

---

## Overview

```
┌─────────────────────┐       HTTP/REST        ┌──────────────────────────┐
│   Angular Studio UI │ ─────────────────────► │  Python Backend Service  │
│  (chat interface)   │ ◄─────────────────────  │  (FastAPI / Flask)       │
└─────────────────────┘                         └──────────┬───────────────┘
                                                           │  MCP protocol
                                                           ▼
                                                ┌──────────────────────────┐
                                                │  Internal MCP Server     │
                                                │  (tool registry / proxy) │
                                                └──────────┬───────────────┘
                                                           │  tool calls
                                                           ▼
                                                ┌──────────────────────────┐
                                                │       IMO Tools          │
                                                │  (search, compute, etc.) │
                                                └──────────────────────────┘
```

The Angular Studio frontend is **mocked** for the POC — a simple chat panel that
sends `POST /chat` requests and renders the response. The Python backend owns all
agent orchestration logic and is the only component Rishikesh must implement end-to-end
for this proof of concept.

---

## Components and Responsibilities

| Component | Technology | Responsibility |
|---|---|---|
| **Angular Studio (Frontend)** | Angular 17+ | Chat UI; renders messages, tool-call traces, and session state. *Mocked for POC.* |
| **Python Backend Service** | FastAPI (recommended) or Flask | Exposes REST API; runs the agent loop; manages session memory; calls the MCP server. |
| **Agent Core** | LangChain / LangGraph (or custom) | Decides which tools to call, assembles the final answer, maintains conversation state. |
| **Internal MCP Server** | Internal deployment (assumed pre-existing) | Hosts and routes calls to individual IMO tools via the Model Context Protocol. |
| **IMO Tools** | Internal services | Domain-specific capabilities (e.g., vessel search, voyage compute, fleet analytics). |

---

## Sequence Flow – Chat Request

```
Angular Studio          Python Backend           Agent Core        MCP Server       IMO Tool(s)
     │                        │                       │                 │                 │
     │  POST /chat            │                       │                 │                 │
     │  {session_id, message} │                       │                 │                 │
     │───────────────────────►│                       │                 │                 │
     │                        │  1. Load/create       │                 │                 │
     │                        │     session memory    │                 │                 │
     │                        │──────────────────────►│                 │                 │
     │                        │                       │                 │                 │
     │                        │  2. Append user msg   │                 │                 │
     │                        │     to history        │                 │                 │
     │                        │──────────────────────►│                 │                 │
     │                        │                       │                 │                 │
     │                        │  3. Run agent step    │                 │                 │
     │                        │──────────────────────►│                 │                 │
     │                        │                       │ 4. Decide tool  │                 │
     │                        │                       │──────────────►  │                 │
     │                        │                       │                 │ 5. Route tool   │
     │                        │                       │                 │────────────────►│
     │                        │                       │                 │                 │
     │                        │                       │                 │ 6. Tool result  │
     │                        │                       │                 │◄────────────────│
     │                        │                       │ 7. Tool result  │                 │
     │                        │                       │◄──────────────  │                 │
     │                        │                       │                 │                 │
     │                        │                       │  (repeat 4-7    │                 │
     │                        │                       │   as needed)    │                 │
     │                        │                       │                 │                 │
     │                        │  8. Final answer      │                 │                 │
     │                        │◄──────────────────────│                 │                 │
     │                        │                       │                 │                 │
     │                        │  9. Persist updated   │                 │                 │
     │                        │     session memory    │                 │                 │
     │                        │                       │                 │                 │
     │  200 OK ChatResponse   │                       │                 │                 │
     │◄───────────────────────│                       │                 │                 │
     │                        │                       │                 │                 │
```

### Key Steps

1. **Session lookup** – Backend retrieves existing conversation history by `session_id`
   (in-memory dict or Redis for POC). New `session_id` is created if absent.
2. **History append** – User message is appended to the session's message list.
3. **Agent invocation** – Agent Core receives the full history plus available tools.
4. **Tool selection** – Agent decides (via LLM reasoning) which IMO tool to call and
   with what arguments.
5. **MCP routing** – Backend calls the internal MCP server with the tool name + args.
6. **Tool execution** – MCP server delegates to the actual IMO tool and returns the result.
7. **Result injection** – Tool output is fed back to the Agent Core as a tool message.
8. **Final answer** – Agent produces the final text response (steps 4–7 may repeat).
9. **Persistence** – Updated history (including tool traces) is saved back to session store.

---

## Session Handling: Agent Core vs Custom Memory

| Concern | Agent Core (built-in) | Custom Memory (backend-owned) |
|---|---|---|
| **What it manages** | Per-invocation message list passed to the LLM | Cross-request session store keyed on `session_id` |
| **Scope** | Single agent run | Entire conversation thread |
| **Storage** | In-process (ephemeral) | In-memory dict (POC) → Redis / DB (production) |
| **Responsibility** | LangChain / LangGraph internals | Rishikesh's backend code |
| **Tool-call trace** | Stored as `ToolMessage` entries in the run | Serialised and persisted alongside `HumanMessage` / `AIMessage` |

**POC approach:** Use a simple `dict[session_id → list[Message]]` in the backend
process. The full message list (including tool calls and results) is rehydrated and
passed to the agent on every request.

---

## Assumptions

| # | Assumption |
|---|---|
| 1 | The **internal MCP server** is already deployed and reachable from the Python backend over the internal network. The backend needs only a base URL and a shared secret. |
| 2 | **Authentication** between Angular Studio and the Python backend uses a bearer token (e.g., Azure AD / OAuth2 JWT). For the POC, a static API key in an env var is acceptable **for local/dev use only** — this must be replaced with proper auth (Azure AD / Managed Identity) before any non-development deployment. Secrets should be sourced from a vault (e.g., Azure Key Vault) rather than plain env vars in production. |
| 3 | **Tool discovery** is done once at startup: the backend calls `GET /tools` on the MCP server, caches the tool manifest, and registers tools with the agent. Hot-reload of tools is out of scope. |
| 4 | **Toggling individual tools on/off** per user or session is **out of scope** for this POC. All available tools are active for all sessions. |
| 5 | The LLM provider (e.g., Azure OpenAI) is accessible from the backend and credentials are injected via environment variables. |
| 6 | The Angular Studio frontend team will consume the REST contract defined below; no frontend implementation is required from Rishikesh for the POC. |
| 7 | A single region / single container deployment is sufficient for the POC. Multi-region and HA are deferred. |

---

## Backend API Endpoints

All endpoints are prefixed `/api/v1`.

### `POST /api/v1/chat`

Send a user message and receive the agent's response.

**Request** – `ChatRequest`  
**Response** – `ChatResponse`  
See [Data Structures](#data-structures) below.

---

### `GET /api/v1/tools`

Return the list of tools currently registered with the agent.

**Response**

```json
{
  "tools": [
    {
      "name": "vessel_search",
      "description": "Search for vessels by name, IMO number, or flag state.",
      "input_schema": {
        "type": "object",
        "properties": {
          "query": { "type": "string" }
        },
        "required": ["query"]
      }
    }
  ]
}
```

---

### `GET /api/v1/healthz`

Liveness / readiness probe.

**Response**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "mcp_reachable": true
}
```

Returns `HTTP 200` when healthy, `HTTP 503` when the MCP server is unreachable.

---

## Data Structures

### `ChatRequest`

```json
{
  "session_id": "string | null",
  "message": "string",
  "metadata": {
    "user_id": "string | null",
    "locale": "string | null"
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `session_id` | `string` | No | Omit or `null` to start a new session. |
| `message` | `string` | Yes | The user's chat message. |
| `metadata.user_id` | `string` | No | Passed through for audit logging. |
| `metadata.locale` | `string` | No | BCP-47 locale hint (e.g., `"en-US"`). |

---

### `ChatResponse`

```json
{
  "session_id": "string",
  "reply": "string",
  "tool_call_trace": [
    {
      "tool_name": "vessel_search",
      "input": { "query": "Ever Given" },
      "output": { "vessels": [{ "imo": "9811000", "name": "Ever Given" }] },
      "duration_ms": 142
    }
  ],
  "usage": {
    "prompt_tokens": 512,
    "completion_tokens": 128,
    "total_tokens": 640
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `session_id` | `string` | Echo or newly created session identifier. |
| `reply` | `string` | Final text answer from the agent. |
| `tool_call_trace` | `array` | Ordered list of every tool call made during this turn. Empty if no tools were used. |
| `tool_call_trace[].tool_name` | `string` | Name of the MCP tool invoked. |
| `tool_call_trace[].input` | `object` | Arguments passed to the tool. |
| `tool_call_trace[].output` | `object` | Raw result returned by the tool. |
| `tool_call_trace[].duration_ms` | `integer` | Wall-clock time for the tool call. |
| `usage` | `object` | LLM token consumption for this turn (omitted if unavailable). |

---

### Error Response

All errors follow a consistent envelope:

```json
{
  "error": {
    "code": "TOOL_TIMEOUT",
    "message": "The vessel_search tool did not respond within 10s.",
    "request_id": "req_abc123"
  }
}
```

Common error codes: `INVALID_REQUEST`, `SESSION_NOT_FOUND`, `TOOL_TIMEOUT`,
`AGENT_ERROR`, `MCP_UNREACHABLE`.

---

## Deployment Notes

> These are **placeholder** notes for a future Terraform / IaC pass.

```
infrastructure/
├── terraform/
│   ├── main.tf          # Resource group, networking (placeholder)
│   ├── variables.tf     # Env-specific overrides
│   └── outputs.tf       # Service URLs, connection strings
├── Dockerfile           # Python backend container image
└── docker-compose.yml   # Local development stack
```

### POC Deployment (manual / CLI)

1. Build and push the Docker image to the container registry.
2. Deploy as a single Azure Container Instance (or App Service) with env vars:
   - `MCP_BASE_URL` – internal MCP server base URL
   - `MCP_API_KEY` – shared secret for MCP server
   - `OPENAI_API_BASE` / `OPENAI_API_KEY` – LLM credentials
   - `BACKEND_API_KEY` – static key accepted by `/chat` (**POC only** — replace with proper auth before production)
3. Point Angular Studio's environment config at the deployed backend URL.

### Production considerations (deferred)

- Replace in-process session dict with **Redis** (TTL-based expiry).
- Add **Azure API Management** in front of the backend for rate limiting and auth.
- Use **Managed Identity** instead of static API keys.
- Enable **distributed tracing** (OpenTelemetry → Azure Monitor).
- CI/CD pipeline via GitHub Actions → Terraform Cloud.

---

## Rishikesh's Task List

The following items are in scope for the 3–4 day POC sprint:

- [ ] **R-1** Set up Python project (FastAPI, pyproject.toml / requirements.txt, Dockerfile).
- [ ] **R-2** Implement `GET /api/v1/healthz` endpoint; verify MCP reachability on startup.
- [ ] **R-3** Implement `GET /api/v1/tools` endpoint; fetch and cache tool manifest from MCP server.
- [ ] **R-4** Implement in-process session store (`dict[session_id → list[Message]]`).
- [ ] **R-5** Integrate Agent Core (LangChain / LangGraph) with the MCP tool wrappers.
- [ ] **R-6** Implement `POST /api/v1/chat` endpoint with full agent loop and tool-call trace collection.
- [ ] **R-7** Write unit tests for request/response serialisation and session creation logic.
- [ ] **R-8** Write an integration smoke-test that stubs the MCP server and asserts the tool-call trace in the response.
- [ ] **R-9** Produce a `docker-compose.yml` that wires the backend + a mock MCP stub for local dev.
- [ ] **R-10** Update this document with any deviations discovered during implementation.

**Not in scope for Rishikesh:**

- Angular Studio frontend implementation.
- Toggling individual tools per user/session.
- Production auth (Azure AD, APIM).
- Terraform / IaC authoring.

---

## Open Questions / Next Decisions

| # | Question | Owner | Target date |
|---|---|---|---|
| Q-1 | Which LLM provider and model version should the agent use? | Rishikesh + Tech Lead | Day 1 |
| Q-2 | What is the internal MCP server base URL and auth mechanism? | MCP team | Day 1 |
| Q-3 | Should `session_id` be a JWT sub-claim, or a separate UUID generated by the backend? | Arch review | Day 2 |
| Q-4 | Is there a maximum message-history length before truncation / summarisation is needed? | Rishikesh | Day 2 |
| Q-5 | Which IMO tools are available and stable enough to use in the POC? | IMO tools team | Day 1 |
| Q-6 | Do we need structured logging shipped to a central store for the POC, or is stdout sufficient? | DevOps | Day 2 |
| Q-7 | Confirm Redis is available in the POC environment, or confirm in-memory is acceptable. | Infra | Day 2 |
