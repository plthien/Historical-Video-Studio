# 02 — SYSTEM ARCHITECTURE · V1.0
**Mode:** Fresh Windows-local implementation; design artifact only. See 01_PRODUCT_SPEC and 04_DATA_CONTRACTS_AND_GATES for behavior contracts.

## 1. Context and bounded responsibilities
~~~
External ChatGPT → single StoryPackage JSON → FastAPI import validator → G1
                                                   ├─ Voice: TTS adapters → G2 → assembly → ElevenLabs alignment
                                                   └─ Assets: archive adapters + G-Labs → G3
                       G2-aligned + G3-approved → deterministic compiler → Remotion Player → G4
                       G4-approved → Remotion renderer → technical QC → G5 → MP4/credits
~~~
**Backend:** Python 3.12/FastAPI, SQLite, local immutable content-addressed store, durable worker queue (local process, not Redis required). **Frontend:** React+TypeScript; design system, forms, scene editor, Remotion Player. **Renderer:** pinned Remotion and Node packages; one shared HistoryComposition used by Player and final render. **Auxiliary:** FFmpeg/FFprobe; optional rembg and source-specific image processors. Windows process lifecycle is a design requirement, not implementation evidence.

## 2. Ownership of contracts
| Module | Owns / validates | Does NOT own |
|---|---|---|
| Authoring Import | StoryPackage schema, IDs, source leads | historical factual certainty |
| Project & Approvals | revision lineage, 5 gate decisions, optimistic concurrency | media bytes |
| Durable Orchestrator | jobs, dependencies, retry/cancel/resume, idempotency | editorial choice |
| TTS Registry | Kokoro/ElevenLabs synthesis, capabilities, provider errors | alignment timing |
| Alignment Registry | ElevenLabs final-WAV word timing and anomaly flags | TTS synthesis |
| Archive Registry | Wikimedia / LOC / Europeana candidate metadata + download | truth/rights final approval |
| G-Labs Adapter | async image creation, poll, download, stop(task_id) | archival authority |
| Asset Store / Treatment | immutable originals, derivatives, transformations | changing a source's factual class |
| Storyboard Compiler | intent resolution, templates, cues, exact integer frames, diagnostics | runtime code generation |
| Remotion Runtime | visual composition from approved timeline, frame deterministic effects | semantic history research |
| Renderer & QC | pinned outputs, playback parity evidence, technical diagnostics | deciding editorial quality |

No API key in browser JSON, project export or logs. UI sends bounded actions and approved IDs only. User-supplied JSON/URL/paths must never become executable code or unrestricted file read.

## 3. Provider Adapter Pattern
Defined ports:
~~~
interface TTSAdapter:
  capabilities() -> {language_ids,voice_ids,speed_range,formats,version}
  list_voices(language) -> VoiceInfo[]
  synthesize(SynthesisRequest) -> AudioAttempt  # typed failure taxonomy
interface AlignmentAdapter:
  capabilities() -> {languages,formats,limits,version}
  align(approved_final_wav,exact_transcript) -> WordTimingMap
interface ArchiveAdapter:
  search(AssetRequirement) -> Candidate[]
  hydrate(candidate) -> EvidenceAndRights
  download(candidate) -> Bytes+MIME
interface ImageProviderAdapter:
  capabilities(); submit(prompt,refs,options)->ProviderTask
  poll(task)->ProviderStatus; download(task)->Bytes; cancel(task)->Status
~~~
V1 registry IDs: kokoro_local, elevenlabs_tts, elevenlabs_forced_alignment, wikimedia_commons, loc, europeana, glabs_webhook. No need to hot-load plugins or arbitrary Python modules from ChatGPT data. Each adapter has offline mock/contract fixtures. Avoid inventing identical license fields between archives; normalize and preserve original responses.

## 4. Voice and alignment lifecycle
1. Canonical section IDs/text and voice configs from G1 approved StoryPackage.
2. Synthesis per section; store provider/voice/model/settings, text hash, raw audio SHA, durations, attempt ID, error details.
3. Playback + correction/regeneration, naturalness and clipping QC; G2 exact attempt approvals.
4. Single G2 Approve action freezes sections, assembles final WAV with reproducible sample offsets and confirms sample count + hash.
5. ElevenLabs Forced Alignment receives exact final WAV and exact spoken transcript; normalize seconds to sample indices then frame cues, preserving loss/anomaly signals and word IDs unique within transcript revision.
6. Alignment invalid/stale: block G4 compilation and expose retry/voice correction; never manufacture word timestamps.
7. Replacing one section attempt rebuilds final audio and invalidates full-word map plus dependent cues, not archive download.

English is the initial lane. Kokoro and ElevenLabs synthesize through distinct TTS adapters, with **ElevenLabs alignment regardless of chosen TTS**. Keep G2 audio decision separate from post-approval automated alignment result. Provider API constraints are checked at runtime/preflight, not guessed from one document.

## 5. G-Labs adapter — contract-first
Implementation authority: user's WEBHOOK_INTEGRATION.vi(1).md. Initial base http://127.0.0.1:8765 (configurable), X-API-Key on protected endpoints.
- GET /api/health checks responsiveness (no API key).
- POST /api/image/generate: prompt required, model, aspect_ratio, reference_images, optional upscale. Returns HTTP 202 task_id.
- GET /api/status/{task_id} every 3–5 s; pending/running/completed/failed; completed.results downloaded through /api/files/{filename}; keep original bytes locally and SHA.
- POST /api/stop/{task_id} on **one named task** only; never use global stop for per-image cancellation.
- Treat 400 invalid input as terminal, 429 quota as actionable backoff, 401/403 configuration issue, transient 5xx/timeouts retriable within limits; worker needs task-id ledger and restart reconciliation.
- If G-Labs and Studio share a host, use documented reference_images object path forms; otherwise base64 under 50 MB body. Model-specific limits/config matter; do not assume all image providers support @tags.
- Running app, MAX license and account availability are prerequisites to live jobs. Mock tests required during implementation. **Live calls are deferred until user-led integrated testing, not a design or coding prerequisite.**
- No G-Labs call allowed for historical-photo replacement until user opts in to managed fallback; all results remain review candidates at G3.

## 6. Archive and provenance lifecycle
AssetRequirement → adapter-specific candidate queries → normalized source leads → item page & full rights metadata → candidate scoring (subject/date/place, evidence quality, usable resolution, legal status) → download immutable original → variant processing → G3 user approval.

Evidence role and rights role are separate: rights metadata cannot prove the photo depicts the actual event. Preserve source page URL, archive item id, creator/title, date, collection, rights statement/license link and retrieval timestamp; do not overwrite unknown with inferred public-domain. User upload requires same provenance/rights form and never auto-approves. Historical maps require period-specific approved geometry with valid dates. A modern border dataset cannot prove 1914 boundaries.

Fallback state machine:
~~~
REQUIRED_SEARCHING → EXACT_CANDIDATE_REVIEW
                   └→ ARCHIVE_ASSET_UNRESOLVED
                          ├→ MANUAL_UPLOAD → candidate review
                          └→ USER_AUTHORIZES_MANAGED_FALLBACK → generated/search candidates → candidate review
candidate review → APPROVED | REJECTED | UNRESOLVED
~~~
Selecting managed fallback is **authorization to propose candidates**, never an asset approval.

## 7. Local storage and revisions
SQLite stores Projects, ProjectRevisions, StoryRevisions, Jobs, ProviderTasks, GateDecisions, AssetRequirements, SourceCandidates, AssetVersions, AssetBindings, AudioAttempts, ApprovedAudio, WordMaps, SceneDrafts, CompiledTimelines, RenderJobs, QcResults, AttributionEntries. Foreign keys and unique project/revision scoped stable IDs.
Immutable media store:
~~~
data/projects/{safe-project-id}/objects/sha256/{hash-prefix}/{sha256}
data/projects/{safe-project-id}/snapshots/{revision-id}.json
data/projects/{safe-project-id}/exports/{render-id}/video.mp4
~~~
Original never edited; every derivative has parent hash, deterministic transform settings/code version and output hash. Approved snapshots pin content hashes and registry versions. Atomic transaction checks expected revision before approving. Do not overwrite approved history.

## 8. Durable jobs, dependency invalidation and concurrency
Jobs: QUEUED/RUNNING/SUCCEEDED/FAILED_RETRYABLE/FAILED_TERMINAL/CANCELLED/BLOCKED_REVIEW with job key (project, artifact_kind, source fingerprint, operation). Lease and attempt token prevent duplicate finalization. Persist external task_id before polling; after restart reconcile task if provider still remembers it, otherwise require safe resubmission decision. Idempotency key per UI action; scoped cancellation.

Dependency edges:
- Story text/claims change → G1 reapproval, affected voice attempts/audio, word map, affected asset requirements and all visual/render dependents. Reuse unrelated assets safely.
- Voice/audio bytes change → G2, assembled WAV, entire alignment map, affected cues/timeline and render stale; no new archival search.
- Asset binding/derivative change → G3 affected rows, scenes using it and G4/G5 stale; no TTS/alignment change.
- Visual layout or preset change → G4 scenes/timeline and G5 stale; G1 unchanged unless factual text altered.
- QC-only re-render with identical frozen input leaves G1–G4 approvals intact; G5 refers to new render hash.
- A stale artifact remains inspectable but cannot authorize downstream work.

## 9. Rendering and parity
Compiler emits validated CompiledTimeline with canonical order, fps 30, 1920x1080, positive integer durations and path-safe asset IDs. Remotion Player takes HistoryComposition as component; Node renderer uses same component registered by Composition for MP4. Both consume same approved timeline, asset/font snapshots and deterministic motion math. Motion Prompt is *reference material*, not a native Remotion dependency. Check selected diagnostic frames plus audio timestamp matching, text collisions, missing assets, black frames and output probe metadata. Do not call a UI CSS approximation “preview parity”.

## 10. Service API outline and error taxonomy
All paths are **proposed V1 local API**, not already implemented. Root /api/v1, defined in 04_DATA_CONTRACTS_AND_GATES and contracts/openapi.yaml.
- POST /projects; POST /projects/{id}/story/import; GET /projects/{id}/gates; POST /projects/{id}/gates/{gate}/decision.
- POST /projects/{id}/voice/generate; GET /projects/{id}/voice/attempts; G2 approval uses only POST /projects/{id}/gates/G2/decision (auto assembly+alignment).
- POST /projects/{id}/assets/discover; POST /projects/{id}/assets/{req}/resolve; POST /projects/{id}/assets/{req}/upload; POST /projects/{id}/assets/{req}/approve.
- POST /projects/{id}/storyboard/compile; POST /projects/{id}/storyboard/revisions; POST /projects/{id}/render-jobs; GET /jobs/{job}; POST /jobs/{job}/cancel.
Use a shared problem response: error_code, message, entity_id, blocking_gate, remediation, retryable. Distinguish HTTP 409 revision conflict / gate illegal transition, 422 schema+cross-ref invalid, 424 upstream dependency stale, 429 provider quota, 503 provider unavailable; never return success when result is not persisted.

## 11. Minimal local safety, no unnecessary enterprise features
Localhost backend binds 127.0.0.1, secrets in local private config; no exposed remote control by default. Path boundary checks and download domain allowlist per provider, limit file size/MIME and reject executable user content. Do not build multi-tenant cloud auth/permissions, Kubernetes, remote SaaS, organization RBAC or fleet orchestration.

## 12. Architecture acceptance
Step 01 passes design review when all adapter boundaries, ownership, approval lifecycle, job states, schema/API links, error paths, review signals, and revision invalidation rules are explicit. Actual provider execution, performance or Remotion parity requires Step 03 evidence and cannot be claimed in this document.
