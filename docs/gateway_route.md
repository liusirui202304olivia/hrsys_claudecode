# HR MCP Centerized HTTP Route

## Current Decision

The previous API Gateway plan is no longer the P0 deployment path. The company
does not have a dedicated API Gateway for this project, so HR MCP now runs as a
centerized FastAPI HTTP-MCP service.

Request path:

`Claude Code CLI -> HR MCP FastAPI service -> controlled data service -> MySQL`

The backend remains a secure data service, not an HR business agent. Candidate
screening, recommendation, Q&A, analysis, and report writing stay in Claude Code
CLI Skills.

## Routes

- `GET /healthz`: liveness.
- `GET /readyz`: repository and local store readiness.
- `POST /mcp`: MCP over HTTP JSON-RPC entry.
- `GET /mcp/tools`: debug tool list, only `HR_ADMIN` or `MCP_DEBUG`.
- `POST /internal/audit/query`: audit readback, only `HR_ADMIN` or `MCP_DEBUG`.

## Identity Contract

Claude Code CLI sends:

- `Authorization: Bearer <token>`
- Optional `X-Request-Id`
- Optional `X-Trace-Id`
- Optional `X-Client-Id`
- Optional `X-Access-Reason` for privileged field access

The service maps the token to `user_id`, `user_name`, `role`, and
`department_id` by reading server-side token configuration. Client-supplied
`X-User-Id`, `X-User-Role`, and `X-Department-Id` are ignored and must not be
used as trusted identity.

## Built-In Security

Because there is no gateway, these controls are implemented in the FastAPI
service:

- Bearer token authentication.
- Server-side role and department mapping.
- IP allowlist.
- Per-user rate limit.
- Request body size limit.
- Success and failure audit logging.
- Field policy enforcement through the safe view service.

## Privileged Fields

Privileged fields are available only when all of these are true:

1. The Bearer token maps to a privileged role, currently `HR_ADMIN`.
2. `X-Access-Reason` or tool argument `access_reason` is non-empty.
3. The request passes `candidate_safe_view_service.py` and `field_policy.py`.

Privileged field access must be audited. Database credentials and connection
strings must stay in the server-side `.env` file and must never be configured in
Claude Code CLI.
