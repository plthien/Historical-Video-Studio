# G-Labs Image Webhook Adapter · Contract-first implementation reference
**Authority:** user supplied WEBHOOK_INTEGRATION.vi(1).md (G-Labs Automation v5.0.8+). This is a **focused implementation projection**, not a replacement for the complete 1149-line supplied source file. No live request has been executed.

## HTTP and task protocol
- Service default http://127.0.0.1:8765, enabled only when the desktop app Webhook server is running and MAX license is active; bound to loopback by default.
- X-API-Key for POST /api/image/generate, GET /api/status/{task_id}, GET /api/result/{task_id}, POST /api/stop/{task_id}; GET /api/health and /api/files/{filename} do not use that key.
- POST /api/image/generate body: prompt (nonempty), model, aspect_ratio, reference_images (optional), upscale (optional). Model examples: nano_banana_pro, nano_banana_2, nano_banana_2_lite, nano_pics. Default aspect_ratio for image request is 1:1: Studio MUST set 16:9 explicitly for landscape requirements.
- Response 202 {task_id,status:"pending",poll_url}. Poll status every 3–5 seconds to terminal completed/failed; completed results are file URLs, download and persist binary locally immediately; not a permanent provider blob address.
- /api/stop/{task_id}: only target specific task; global /api/stop is forbidden for cancelling one Studio job. Cancellation may still incur upstream generation cost already charged.
- Pending/running/completed/failed explicit state, with error_code/error/error_detail fields on failure; recent task registry is limited, Studio retains its own durable job ledger.

## Request shaping
For Nano Banana 2/Pro/Lite: accepted aspect_ratio 1:1,3:4,4:3,9:16,16:9; reference_images up to 10; upscale can request 2K or 4K with account/model entitlement. For nano_pics strict mode/keep/ref and different ratio rules apply; it is NOT identical to the Flow models.
Images use base64 strings or object {data:...} or {path:...}, with path only on the same machine as G-Labs; remote requires base64 and 50 MB JSON body cap. For Flow model @tag may refer to named image; nano_pics and OpenAI do NOT support that linking. Implement model-specific validation rather than generic acceptance.

## Provider adapter state contract
submit returns normalized ProviderTask(provider="glabs_webhook",task_id,request_hash); poll returns status+diagnostics; download returns bytes+MIME+SHA and immutable local URI; cancel returns scoped stop status. Store model, prompt, reference hashes, aspect_ratio, upscales, task_id and cost/quota information when available.
- 400 input validation ⇒ fix request (terminal).
- 401 missing/bad key ⇒ settings action (terminal).
- 403 MAX/license ⇒ settings action (terminal).
- 413 >50MB ⇒ shrink refs / use same-device path.
- 429 quota ⇒ retry/backoff or user waiting, never silently change product.
- 5xx/timeouts ⇒ bounded retries and operator-visible failure.
- provider_task_id not found after restart ⇒ reconcile as unknown, not blind duplicated generation.

## Critical historical integrity
This provider produces **AI_ILLUSTRATION** only. Missing exact archival item → G3 unresolved → user picks Manual Upload or explicitly authorizes Managed Fallback → generation creates candidates **requiring later G3 human approval**. Provider return completed is not a source-evidence approval.

## Design acceptance
Mock HTTP 202/pending/running/completed/failed, auth errors, quota, cancel(task_id) and restart-safe task ledger. Live G-Labs integration is **not a precondition to writing code** per user; when tested later it must be reported as observed/failed, never inferred PASS from mocks.
