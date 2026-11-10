# Deployment limits for the reverse proxy and app server (PHASE_01 / 01.7, REV-0124)

TECHNICAL DEFAULTS for the internal reverse proxy (DEC-042). They are applied when the staging server exists
(DEC-045 A); the values below follow from approved parameters and settings, not from a guess.

## 1. Request body size

| Layer | Limit | Source |
|---|---|---|
| Parameter `document_upload_max_bytes` | 26 214 400 bytes (25 MB) | DEC-053, employer answer Q-0104 (seed 0010) |
| App: `UploadSizeLimitMiddleware` (`backend/platform_core/api/upload_limit.py`) | `document_upload_max_bytes` + 65 536 bytes multipart allowance, checked from `Content-Length` **before** the body is read; larger -> 413 `PAYLOAD_TOO_LARGE` (problem+json) | 01.7 |
| App: upload view | the exact file size again after parsing (defence in depth) | 01.4 |
| App: every other body | `ALEEKHAN_MAX_BODY_BYTES` (default 1 048 576) via Django `DATA_UPLOAD_MAX_MEMORY_SIZE`, checked before reading | 00.4 |
| **Proxy (to configure)** | `client_max_body_size 26m;` on the upload location `~ ^/api/v1/documents/[^/]+/revisions$` (POST); `client_max_body_size 1m;` everywhere else | this document |

Rules:
- If the employer changes `document_upload_max_bytes`, the proxy limit of the upload location must be raised to
  at least the new value + 64 KiB in the same change; otherwise the proxy answers 413 first (nginx: plain HTML,
  not problem+json).
- Keep `client_body_buffer_size` small (e.g. 128k) so large bodies are buffered to the proxy's temp folder on
  the proxy host, never forwarded before the limit check; `proxy_request_buffering on;` (default).
- Requests without `Content-Length` (chunked) are refused by the proxy for the upload location
  (`if ($http_transfer_encoding ~* chunked) { return 411; }`); Django would read them as an empty body anyway.

## 2. Timeouts (TECHNICAL DEFAULT)

| Setting | Value | Why |
|---|---|---|
| `proxy_read_timeout` | 60 s | an upload of 25 MB on the factory LAN takes seconds; the scan runs later as a job |
| `client_body_timeout` | 60 s | slow-body protection |
| gunicorn `--timeout` | 60 s | same |

## 3. Security headers on the proxy (checklist items 2.6, 3.4)

HSTS (prod), CSP for the static UI (`default-src 'self'; frame-ancestors 'none'`), `X-Content-Type-Options:
nosniff` - to be set with the staging server; tracked as OPEN items in docs/security/PHASE_01_SECURITY_CHECKLIST.md.
