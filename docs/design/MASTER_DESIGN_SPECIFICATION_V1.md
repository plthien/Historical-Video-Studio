# MASTER DESIGN SPECIFICATION V1.0
## History Motion Graphics Studio — New Build / Storyboard-first / Human-approved Automation

**Ngày khóa bản thiết kế:** 19/10/2026  
**Trạng thái:** DESIGN REVIEWED — **CONDITIONAL PASS**; chưa triển khai, chưa chứng minh bằng video pilot.  
**Phạm vi:** Bước 01 Product & Architecture Specification + Bước 02 Visual System & Template Specification.  
**Nguồn đầu vào:** `1015.mp4` (video mẫu người dùng cung cấp), `WEBHOOK_INTEGRATION.vi(1).md` (hợp đồng G-Labs do người dùng cung cấp), repository Remotion, Motion Prompt và tài liệu nhà cung cấp được liệt kê ở §21.  
**Giới hạn:** Xây ứng dụng **mới hoàn toàn**, không tiếp tục kiến trúc, database, lược đồ hoặc runtime của Historical-Motion-Graphics-Studio cũ. Repo cũ không phải nguồn thẩm quyền thiết kế. Không chỉnh sửa repo trong công việc này.

> **North Star:** *Một Story Package JSON do ChatGPT bên ngoài tạo → sản xuất tự động giữa các Human Review Gates → video lịch sử motion-documentary xuất bằng Remotion, có provenance và dễ sửa cảnh.*

### Ký hiệu bắt buộc
- **MUST**: quy tắc bắt buộc để đạt V1; vi phạm = BLOCK.
- **SHOULD**: mặc định khuyến nghị, có thể thay bằng quyết định ghi nhận.
- **MAY**: mở rộng; không là điều kiện nghiệm thu V1.
- **VERIFIED FACT / OBSERVATION / DESIGN DECISION / OPEN RISK**: phân biệt khả năng repo, quan sát từ video, quyết định thiết kế và điều chưa kiểm chứng.
- Các số thời lượng/cỡ chữ ở §12–15 là **design defaults cần thử nghiệm trên video thực**, không phải số đo suy ra chính xác từ video mẫu.

---

# PHẦN A — PRODUCT & SYSTEM ARCHITECTURE (STEP 01)

## 1. Product vision, boundaries và mục tiêu

### 1.1 Người dùng và trường hợp sử dụng
- Operator chính: **một người vận hành trên Windows**, làm video lịch sử nhiều chủ đề, không cần biết React/JSX, lập trình hoặc timeline compositor chi tiết.
- Đầu vào sáng tạo: ChatGPT ngoài ứng dụng; operator tự copy prompt, trao đổi và **download JSON rồi import**. Không có LLM API/SDK, local LLM, AI browser automation, Codex/Claude Code trong production.
- Nội dung: video **motion documentary 2D** 16:9: bản đồ, ảnh tư liệu, portrait cutout, document, label, quote, schematic, typography, animation 2D/2.5D, voice-over; không hứa tái tạo hoạt hình 3D hay tất cả phong cách điện ảnh.
- Kết quả: final MP4 + QC report + source/attribution report + bản JSON project và revision references để dựng lại.
- Chiến lược: template/preset đã lập trình, kiểm thử một lần; mỗi video tiếp theo **chỉ nhập dữ liệu**.

### 1.2 Mục tiêu V1 — riêng biệt
1. **Workflow Automation:** giữa hai gates đã được approve, mọi job có thể tự chạy, dừng/khôi phục và báo lỗi có lý do.
2. **Editorial Reuse:** cùng một template/preset registry dựng được **ít nhất hai câu chuyện khác nhau** mà không thêm code scene-specific.
3. **Evidence Integrity:** không tự gắn sai ảnh lịch sử, không fallback âm thầm, giữ source/rights/transform lineage và nhãn AI reconstruction.
4. **Preview–Export Parity:** Player và MP4 dùng chung composition, assets/font/timeline revision; sai lệch có kiểm tra.
5. **Local-first operability:** hoạt động trên Windows với một launcher, API/provider secrets lưu local server-side, backup/project portability.

### 1.3 Non-goals V1
- Không tự nghiên cứu, kết luận mọi fact lịch sử hoặc tự làm quyền sử dụng ảnh hợp pháp tuyệt đối.
- Không tự sinh JSX, JS, CSS, animation code hoặc ghép plugin mới khi sản xuất một video.
- Không tự gọi AI video model cho mọi cảnh; G-Labs là **image-generation adapter** chính, có thể mở rộng video provider trong tương lai nhưng không là điều kiện V1.
- Không thay thế một desktop NLE chuyên nghiệp; tập trung scene/layer/timing đủ cho motion documentary.
- Không hoàn toàn “hands-free”: **5 Human Approval Gates là bắt buộc**.
- Không auto-approve ảnh không rõ provenance/rights hoặc file người dùng upload; không coi ảnh AI là tư liệu gốc.
- Không cam kết tiếng Việt TTS / Forced Alignment đạt chất lượng production khi chưa kiểm tra tương thích model thật (§9.7).

### 1.4 Nguồn nguồn tham chiếu và điều đã xác minh
- **OBSERVATION — video `1015.mp4`:** độ dài **298.284 giây**, **1920×1080**, **30 fps**, stream HEVC/AAC 44.1 kHz stereo. Các frame ở 0–295s thể hiện phối hợp giấy trắng ngà, chữ đen/vàng/đỏ, archive photo cards, portrait cutouts, maps nền tối, route diagrams, typography trọng âm. Quan sát từ contact sheets có bước lấy mẫu 5s; **không chứng minh từng easing/timing chính xác** và không xác minh sự thật lịch sử trong video.
- **VERIFIED FACT — Remotion:** có `@remotion/player` cho browser preview, `@remotion/renderer` cho Node render video/stills; `@remotion/transitions` và frame-driven React composition [S1–S3].
- **VERIFIED FACT — Motion Prompt:** 120 element ở 5 pack; Canvas 2D reference code/spec là nguồn tham khảo **không phải package Remotion preset đã sản xuất sẵn**; có hướng dẫn port và giấy phép MIT/attribution [S4–S6].
- **VERIFIED FACT — G-Labs:** webhook localhost mặc định :8765, MAX license, POST image async, status/poll/results, reference images, upscale, error/cancel; lấy từ file user [U2]. **Chưa live-test endpoint trên máy user.**
- **OPEN RISK — ElevenLabs forced alignment tiếng Việt:** tài liệu giới thiệu Forced Alignment nêu 29 ngôn ngữ, **chưa liệt kê Vietnamese**; dubbing/Scribe/TTS hỗ trợ tiếng Việt **không** chứng minh forced alignment hỗ trợ [S7–S8]. V1 sẽ chỉ bật ngôn ngữ khi provider capability test đạt.

## 2. Product workflow và 5 Human Review Gates

### 2.1 Main flow — một lần ChatGPT authoring bắt buộc
```
USER: Tạo Project, chọn Style Profile + language + mục tiêu
  ↓
APP: Build External ChatGPT Brief + export authoring prompt
  ↓  [MANUAL EXTERNAL CHATGPT — ONE REQUIRED AUTHORING PASS]
USER: Import StoryPackage.v1 (script, claims, visual intent, asset requirements)
  ↓ strict syntax + semantic validations
[G1 — STORY & RESEARCH APPROVAL]
  ├── VOICE BRANCH: Kokoro/ElevenLabs TTS → review-ready voice sections → [G2 VOICE]
  └── ASSET BRANCH: Archive search → rights/relevance classification → missing queue
            → user selects manual upload OR managed fallback → [G3 ASSETS]
  ↓ G2 APPROVED + G3 APPROVED
APP: Final WAV freeze/assemble → ElevenLabs forced alignment → timing QA
  ↓ if alignment fails: BLOCK, report/resume correction; do not invent word times
APP: Resolve VisualBlueprint → compile storyboard, scene templates/layers/motions
  ↓ deterministic preview with actual asset/voice revision
[G4 — STORYBOARD APPROVAL]
  ↓
APP: Remotion render MP4 + automated technical QC + attribution generation
  ↓
[G5 — FINAL VIDEO APPROVAL] → release/export
```
**Gate sequencing:** G2/G3 độc lập có thể hoàn thành theo thứ tự bất kỳ; assembly/alignment trigger gắn với G2, compilation cần G2 alignment PASS + G3 PASS. G4 không được APPROVE nếu có unresolved upstream; G5 chỉ approve exact render revision.

### 2.2 Gate state machine
`DRAFT → PREPARING → READY_FOR_REVIEW → APPROVED | CHANGES_REQUESTED | REJECTED | BLOCKED`.  
Sau `CHANGES_REQUESTED`, chỉ workflow/revision được chọn chạy lại; `BLOCKED` cho technical/provider/evidence failure và có retry/resolution path; APPROVED gắn user action, immutable inputs fingerprints. Không có `auto_approve` trên 5 gates.

### 2.3 Acceptance của từng gate

| Gate | Màn hình/đầu vào | MUST PASS | Các hành động user | Artifact freeze |
|---|---|---|---|---|
| G1 Story/Research | Script, assertions, claim/source links, visual intents | Toàn script có ID; mỗi factual claim có source state (`verified/reviewed/uncertain`); unresolved critical claim được sửa, rút lại hoặc user approve điều chỉnh minh bạch | Approve, targeted edit, reject, export repair prompt | `ApprovedStoryRevision` |
| G2 Voice | Full audio + section waveform, TTS settings, section QC | Script/audio được match; không bị cắt đầu/đuôi; lỗi phát âm đã xử lý hoặc user ghi nhận rõ; assembled final audio có hash | Approve Voice (auto assemble + ElevenLabs align), regenerate section, adjust pacing/correction, reject | `ApprovedFinalAudio` + **later** `VerifiedWordTimingMap` |
| G3 Assets | Asset board, provenance, license, thumbnails, missing list, fallback previews | Tất cả **required** visual asset bindings có explicit approved source/version hoặc approved alternate; không có missing/unlicensed blocker | Approve batch, replace, upload, ask managed fallback, reject | `ApprovedAssetSnapshot` |
| G4 Storyboard | Player, scene list, timeline, unresolved diagnostics | Correct scene semantics; no missing required asset; text layout/word cues valid; template quality reviewed; no unsupported preset | Approve, edit scene/layer, replace asset/preset, request selective rebuild | `ApprovedCompiledTimeline` |
| G5 Final | MP4 preview, QC report, attribution/rights sheet | Render technical PASS, correct revision hashes, no blank/black unintended frames, audio included, reviewer listened/watched | Approve publish, return scene/editor, rerender, reject | `ApprovedDeliveryRevision` |

**G1/3 user human judgment ≠ automated certificate.** Metadata/rights heuristics produce candidate assessments; operator owns explicit approval. Gate badges must never imply actual claim truth or legal clearance beyond recorded evidence.

### 2.4 Missing archival asset — mandatory two-option rule
Whenever an archival requirement cannot be fulfilled by a suitable candidate, set `ARCHIVE_ASSET_UNRESOLVED`, stop **that asset requirement** (other unrelated research/jobs may proceed), and show exactly the two primary options:
- **Option M — Manual Upload:** user tự tra mạng, upload owned/allowed file, bổ sung original source URL, photographer/creator, title, dated context, license/permission evidence; engine checks format/hash/provenance completeness; **requires G3 approval**.
- **Option F — Managed Fallback:** only after user opts in **per requirement or explicit selected batch**; engine proposes candidates in tiers: related archive context → documentary evidence → schematic/map reconstruction → AI illustration via G-Labs. Must label how each differs from exact photo. Render candidate preview and user selects/approves; **no auto acceptance**.
`user_selected_fallback = true` authorizes *candidate generation only*, not use in approved timeline. Cannot silently move to a different tier or modify the factual statement. A candidate with a mismatching factual claim is rejected/marked needs re-authoring.

### 2.5 Gate routing and selective invalidation
| Changed object | Invalidate / recompute | Must remain unchanged |
|---|---|---|
| Narration or factual wording | G1 + affected TTS/voice; alignment; dependent asset needs/scene; G4/G5 | Other projects |
| TTS section audio/pacing | G2; assembled WAV; alignment; voice-cued timeline; G4/G5 | Archival originals/license metadata |
| Final WAV | Word timing map; downstream cues/timeline/MP4; G4/G5 | Script approval record (unless words changed) |
| Asset binding / crop | Affected G3 binding; affected scenes + G4/G5 | Final audio, unaffected asset versions |
| Asset license/provenance | G3 of affected bindings, downstream publication eligibility + G4/G5 | Original file hashes |
| One motion timing/preset | Affected compiled timeline and G4/G5 | Script, audio, asset approval |
| Source style tokens/fonts | All affected template renders G4/G5 only | Script/audio/source originals |
| Only export codec/bitrate | Render/QC/G5 | Approved storyboard revision |

Approved records **never overwritten**; a new candidate/revision references previous record. User-visible UI shows why a downstream gate became STALE and what did not change. An approval is valid only for exact dependency fingerprint.

## 3. App information architecture and UX

### 3.1 Six workspaces, not engineering phases
1. **Project & Style:** create/select project; language, aspect ratio, length, reference profile, output quality; settings/connection health.
2. **Story Review:** export ChatGPT prompt, import schema JSON, inspect sections/claims/source trail; G1.
3. **Voice Studio:** choose Kokoro/ElevenLabs, voice, speed, preview per section, correction/regeneration, full approve; G2 and alignment status.
4. **Historical Assets:** search batches, license/source inspector, archive thumbnails, missing list, two-option resolution modal, G-Labs candidate queue; G3.
5. **Storyboard & Motion:** Remotion Player + scene navigator + tracks/layers + preset inspector + auto QA, regenerate/edit selective; G4.
6. **Render & Delivery:** immutable render job, logs/progress/cancel/retry, video QC, attribution, export; G5.

### 3.2 UX guidelines
- Global header: `project`, `current_revision`, `production_status`, `5 gates`, `blocked_count`, `cost/quota signals`, `last saved`, and *next valid action*. `Start/Continue Production` advances jobs **only to next gate**; never skips gate.
- Batch review by default; show exception queue and filter `requires-review | missing | rights-unknown | invalid-timing`.
- Every field editable through bounded UI controls; raw JSON advanced viewer is read-only by default (edited JSON must revalidate).
- Manual fallback flow: search link instructions then drag/drop uploader with mandatory source/rights fields. App cannot fetch user's unspecified private website automatically.
- No inert buttons; clicking an async operation immediately indicates state and shows its queue, retry/cancel target, and visible outcome.
- Stable IDs, undo/redo within draft, no edits in approved immutable snapshot; promotion is explicit.
- Keyboard navigation for common review actions; long lists virtualized.

## 4. Service architecture and module ownership

```
React + TypeScript Studio UI
  ├── Project/Style, Story Review, Voice Studio, Assets, Storyboard, Delivery
  └── @remotion/player → same HistoryComposition & CompiledTimeline DTO
FastAPI (local 127.0.0.1, new SQLite + immutable artifact store)
  ├── Project/Approval/Revision/Dependency service
  ├── External Authoring Import + strict schemas + Claims service
  ├── Production Orchestrator (durable jobs / bounded queue / resume)
  ├── Voice subsystem
  │    ├── TTSAdapter Registry → KokoroAdapter / ElevenLabsTTSAdapter
  │    ├── Audio Assembly/QC
  │    └── AlignmentAdapter Registry → ElevenLabsForcedAlignmentAdapter
  ├── Assets subsystem
  │    ├── ArchiveAdapter Registry → Wikimedia / LOC / Europeana
  │    ├── Rights/Evidence Inspector + Missing-Resolution Queue
  │    ├── ImageGenerationAdapter Registry → GLabsWebhookAdapter
  │    └── immutable originals + deterministic derivatives + variant QC
  ├── Storyboard/Director Compiler → template resolver, timed layer graphs
  └── Render Bridge/Quality/Attribution service
Node/Remotion local runtime
  ├── Shared HistoryComposition + Template Registry + Motion Presets
  └── @remotion/renderer, FFprobe, QC thumbnails
```

### 4.1 Design decisions
- Python/FastAPI owns file/network/provider coordination, canonical JSON schema validation, SQLite transactions and job states.
- React owns UX; **never calls G-Labs or ElevenLabs with API keys directly**.
- Remotion engine owns **all final image composition**. Browser Player and Node renderer share component entrypoint, style tokens/font and compiled plan to prevent dual implementations.
- `motion-prompt` **not runtime dependency**. Port selected mechanisms into audited local preset implementations; retain source license lines/attribution when code/numbers reused [S4–S6].
- `maplibre` MAY be an optional *editor* library for geospatial exploration, but historical map layers rendered as verified period-specific SVG/GeoJSON/raster; contemporary polygons never treated as historical truth without evidence.
- Image and video AI are different: V1 requires images through G-Labs, **no AI-video provider** necessary.
- Local-only single operator: minimal but adequate safeguards (loopback service, process-owned child jobs, bounded file paths, secret protection, outbound domain rules); no enterprise RBAC/SaaS architecture.

### 4.2 Directory/package boundaries (proposal)
```
app/
  api/  project/  auth_package/  approvals/  jobs/
  voice/{tts_registry,adapters,audio,alignment,qc}/
  assets/{archive_adapters,search,rights,download,variants,glabs,review}/
  director/{resolver,compiler,layout,timing,validation}/
  render/{bridge,jobs,qc,attribution}/
contracts/{story,voice,assets,visual,timeline,approval,render}/
runtime/remotion/
  src/{composition,templates,presets,maps,typography,assets,style}/
src/{features,components,layouts,player}/
tests/{contracts,providers,voice,assets,director,remotion,ui,e2e}/
```
Do not persist API credentials in exported project package. Any storage/binary paths derive only from validated project/asset IDs, not model-supplied arbitrary paths.

## 5. Durable production orchestration

### 5.1 Job lifecycle
`QUEUED → RUNNING → SUCCEEDED | FAILED_RETRYABLE | FAILED_TERMINAL | CANCELLED | BLOCKED_REVIEW`. Store `job_id, owner, type, dependency_snapshot, attempt, lease/execution_nonce, provider_task_id, input_hashes, outcome, error_code` transactionally.

- Retry policy explicit per provider; G-Labs 429 waits/backoff rather than regenerating blindly; max attempts configurable; no spin loop.
- Retry/idempotency: repeated UI click cannot submit duplicate running job for same revision/job key; archive same file SHA reused, G-Labs calls only after user action or permitted job retry.
- Crash/resume: on startup reconcile orphan jobs and known provider IDs, verify output hash, do not publish stale attempts.
- Cancellation scoped to job; **G-Labs `POST /api/stop/{task_id}`** for exactly one task. Do not call bare global `/api/stop` for a single asset.
- Operator panel provides `queued/running/error/blocked`, elapsed time, last failure, provider, next retry, estimated spend when possible.
- Running independent branches after G1: voice and archive discovery; G3 individual unresolved items can pause without stopping G2.
- Network failures must never retroactively undo approved work; immutable artifacts allow offline re-preview if assets/fonts present.

### 5.2 Approval transaction
Approve validates the **exact revision hash** just reviewed, all upstream required gates passed, and no missing required artifact; records operator decision timestamp/version and atomically publishes new approved head; refuses optimistic lock conflict. Snapshot hash includes source authoring, provider identity, final WAV, word map, every approved asset version, style/font and compiler/template versions.

## 6. Data contracts and external ChatGPT authoring

### 6.1 External authoring rules
- Studio exports a **versioned Prompt Package** with audience, target language, style vocabulary, narrator constraints, allowed visual intent/template keys, source requirements, `StoryPackage.v1` JSON schema and negative examples.
- ChatGPT returns **one importable JSON file** containing script sections, claim IDs, source leads, provisional visual beats / candidate template intentions and asset requirements. It does **not** output executable JSX, scripts, SVG markup, CSS, arbitrary URLs to download, or immutable timestamps invented before voice exists.
- User brings file into Studio; strict parsing checks schemas and related IDs; claims and source leads considered **candidates**, not verified just because ChatGPT supplied them.
- In V1 **one ChatGPT authoring round is intended**; optional targeted repair round when author/script changes or research truly requires it is not counted as normal operator loop. Daily UI edits need no ChatGPT.
- Treat all model text as **untrusted data**; external JSON specifies safe IDs/values only. Provenance checking/research operates separately.

### 6.2 Canonical object inventory
| Object | Required information |
|---|---|
| `Project.v1` | id, language BCP-47, output profile, style_id, project revision |
| `StoryPackage.v1` | schema, project, sections, ordered spoken text, claims/source leads, visual_intents, asset_requirements |
| `Claim.v1` | claim_id, text, attribution/source lead, confidence state, depiction sensitivity, operator decision |
| `AssetRequirement.v1` | requirement_id, visual_role, exactness, historical period/place, target type, scene use, `required` boolean |
| `SpeechSection.v1` | section_id, canonical spoken text, voice ID/config, text SHA, language |
| `TTSAudioArtifact.v1` | audio SHA, provider/model/voice, pronunciation overrides, sample rate, native duration, correction lineage |
| `FinalAudio.v1` | assembled WAV SHA, section offsets/samples, peak/QC, spoken transcript SHA |
| `WordTimingMap.v1` | alignment provider/version, final WAV SHA + transcript SHA, words and stable word IDs, start/end samples, anomaly flags |
| `ArchivalAsset.v1` | origin URL/item ID, author/date/place/rights evidence, SHA, content class, approved status |
| `AssetVariant.v1` | original SHA, transforms list/version, derivative SHA, transform policy, display disclaimers |
| `ManagedFallbackDecision.v1` | req ID, chosen option, tier, candidate IDs, human candidate approval, reason |
| `VisualBlueprint.v1` | semantic setup/scene intents, optional template ID, cues referencing word/section IDs, layer roles, asset req refs |
| `CompiledTimeline.v1` | fps, dimensions, integer frames, approved source refs, validated template/layers, all resolved cues, deterministic hash |
| `ApprovalRecord.v1` | gate, candidate SHA, dependency fingerprint, user decision, timestamp, reason |
| `RenderJob.v1` | pinned timeline, renderer version/font/media SHA, output path, render result hash, QC/attribution refs |

### 6.3 Illustrative Story Package payload (not full JSON Schema)
```json
{
  "schema_version": "StoryPackage.v1",
  "project": {"title": "How Germany Became One Country", "language": "en"},
  "sections": [{
    "section_id": "sec_001",
    "narration": "In 1871, the German Empire was proclaimed.",
    "visual_intents": [
      {"intent_id": "vi_001", "kind": "ARCHIVE_PHOTO_EVENT", "cue_text": "1871", "asset_requirement_ids": ["req_001"]}
    ],
    "claim_ids": ["claim_001"]
  }],
  "claims": [{"claim_id": "claim_001", "text": "The empire was proclaimed in 1871.", "source_leads": ["SOURCE_LEAD_URL"], "status": "UNVERIFIED"}],
  "asset_requirements": [{"id": "req_001", "subject": "1871 proclamation", "preferred_class": "HISTORICAL_ARTWORK", "required": true, "historical_date": "1871"}]
}
```
**Important:** `SOURCE_LEAD_URL` is intentionally a placeholder, not a claimed source. Production schema rejects unresolved required historical sources when G1 rules require them. The illustrative JSON is for communication, not a runnable validator fixture.

### 6.4 Semantic compiler and ownership boundaries
- `StoryPackage` establishes **what must be told** and a soft visual plan; per-word frame timing not in ChatGPT JSON.
- `G2 ApprovedFinalAudio + Alignment` establishes **when** words are actually spoken; per-word IDs stable only within transcript revision.
- `G3 ApprovedAssetSnapshot` establishes **which** legally/evidentially reviewed files may be drawn.
- `Director Compiler` resolves **how** approved assets + template/preset graph appear; rejects unapproved asset refs and unknown template/preset IDs.
- `G4` freezes edit decisions; renderer must be a **pure consumer** of CompiledTimeline and immutable files.

## 7. Provider adapters (principles)
- Adapter = outbound integration boundary; must report `capabilities, health, validation, execute, normalized_result/error`.
- Register provider by stable `provider_id` and version; no provider-specific code in Storyboard/Render UI.
- Changing TTS provider never changes semantics of `FinalAudio` or `WordTimingMap`. Changing archive source never changes `ArchivalAsset` canonical schema.
- Future adapters feature-flagged and independently contract-tested; no dynamic code plugin loading in imported JSON.

## 8. Voice engine and ElevenLabs alignment

### 8.1 Adapter interfaces (illustrative)
```python
class TTSAdapter(Protocol):
    def capabilities(self) -> TTSCapabilities: ...
    def list_voices(self, language: str) -> list[VoiceInfo]: ...
    def synthesize(self, request: SynthesisRequest) -> AudioArtifact: ...

class AlignmentAdapter(Protocol):
    def capabilities(self) -> AlignmentCapabilities: ...
    def align(self, final_wav: FinalAudio, exact_text: str) -> AlignmentResult: ...
```
V1: `KokoroTTSAdapter` (local wrapper) + `ElevenLabsTTSAdapter` (cloud), `ElevenLabsForcedAlignmentAdapter` (separate). **Do not** embed alignment in ElevenLabs TTS adapter; Kokoro audio goes to same alignment pipeline.

### 8.2 Detailed voice flow
1. Per-section canonical spoken text & pronunciation map (proper names); reject unsupported language/voice combination in UI.
2. TTS provider emits raw audio + provider synthesis identity; keep attempt lineage.
3. Quality check duration, corrupt file, silence, sample rate, volume, cut-off, expected transcript; allow user play/compare attempts and targeted regeneration/correction.
4. G2 approval freezes selected attempts, then assembler builds **exact final WAV** with explicit pauses/crossfades and stable sample offsets (user's single `Approve Voice` workflow).
5. ElevenLabs Forced Alignment receives **final WAV** + exact transcript (plain text) via `POST /v1/forced-alignment`; normalized response maps word/character to unique word IDs with time/sample indices [S7].
6. QC word range monotonic/non-negative, within WAV, tolerable unmatched transcript, anomalies around names/punctuation/silence; **do not fake timestamps**. Mark BLOCKED when provider rejects or insufficient quality; show repair/retry path.
7. Revision invariant: any edit to audio bytes or exact text invalidates old word timing map. Every render references exact audio SHA and map SHA.

### 8.3 Pacing and section handling
- Use natural speaking pace and deliberate pauses appropriate to voice; output duration is **measured** after generation/correction, never imposed as a fixed word-rate assumption.
- `section target WPM` may guide generation based on style/language; actual realized WPM recorded; preserve word sequence and section continuity.
- FFmpeg speed correction SHOULD be limited and human-reviewable; no silent time-stretch that makes narration unnatural.
- Script and voice approval can iterate independently of asset search, but G4 waits for stable approved final audio + successful alignment.

### 8.4 Language compatibility gate — **P0 BLOCKER IF NOT VERIFIED**
- Sample video visibly uses Vietnamese captions; this does not prove intended future narration language. Product setting must be explicit per project.
- Official ElevenLabs Forced Alignment overview currently lists 29 languages **without Vietnamese** [S8]; documentation for separate Scribe/Dubbing services lists Vietnamese but cannot be assumed relevant.
- **Initial certified V1 lane: English**, contingent on real Kokoro/ElevenLabs/align tests.
- **Vietnamese lane:** `UNVERIFIED_PROVIDER_SUPPORT` until realistic Vietnamese test audio on chosen ElevenLabs Forced Alignment is accepted and passes word-cue accuracy review. If not, status `BLOCKED_LANGUAGE_SUPPORT`; user must decide whether to change project language/requirements. **No silent swap of alignment provider**, as user explicitly chose ElevenLabs alignment.
- Verify provider file size/limits from the live endpoint at implementation: official API reference lists `<1GB` while overview mentions a larger bound; use conservative `<1GB` preflight unless resolved [S7–S8].

## 9. Historical asset engine and integrity

### 9.1 Archive source adapters
V1 target adapters: `WikimediaCommonsAdapter`, `LibraryOfCongressAdapter`, `EuropeanaAdapter`, with local upload. Each can `search(query)`, `get_item(item_id)`, `get_rights_evidence`, `download_candidate` and emit normalized metadata; source limitations become per-adapter capabilities rather than fake common APIs. Date/place/entity match, license, source quality are separate dimensions.

### 9.2 Search, ranking and rights
- Build terms from asset requirement: canonical subject, alternate names, date range, event, location, document type and `exactness` (`event_exact | subject_exact | context_related`).
- Candidate scores: subject/period consistency, source provenance, usable resolution, rights clarity, visual suitability, uniqueness. **Never let attractive aesthetics override known factual mismatch.**
- Keep 4 distinct statuses: `CANDIDATE`, `RIGHTS_ELIGIBLE`, `EVIDENCE_REVIEWED`, `USER_APPROVED`; **rights metadata is not proof of historic depiction**.
- Never auto-crop source text to misleading claim, remove copyright mark in violation of license, or edit/archive source to imply an event not depicted.
- Rights unknown / no explicit reuse grant is not automatically public domain; archive hosting ≠ permission. License terms (attribution and ShareAlike on derivatives) need individual records [S9].

### 9.3 Asset classification
`ARCHIVAL_PHOTO | HISTORICAL_DOCUMENT | HISTORICAL_ARTWORK | HISTORICAL_MAP | MODERN_RECONSTRUCTION | AI_ILLUSTRATION | USER_SUPPLIED`. Class is immutable per source asset version; derivative does not silently change an `AI_ILLUSTRATION` into an archival photo. Onscreen labels and attribution derived from class/metadata; source attribution sheet accompanies export.

### 9.4 Rights/provenance record
Minimum `original_item_url, archive_id/item_id, title, creator, source_claim, capture_or_creation_date (or unknown), source_collection, current_license_url+verbatim license, restrictions, retrieval_date, source_sha256, user_rights_note, review_decision`. Unknowns explicit `null/unknown` with warning. Preserve original image bytes and transformations separately.

### 9.5 Source preservation and visual processing
- Immutable origin file → non-destructive derivatives `crop`, `grayscale/contrast`, `paper border`, `drop shadow`, `cutout mask`, `editorial vignette`, `upscale` (if permitted), `background overlay`.
- Every derivative stores parent SHA + deterministic params/code version; do not replace origin.
- Cutout fidelity checker: if hair/edges/subject fractured, downgrade to photo card **as a visual treatment**, not a historical evidence fallback; user may review. Never fake missing pixels without explicit reconstruction classification.
- AI creation through G-Labs only for `AI_ILLUSTRATION` or user-approved fallback. No automatically generated "archival" photos, no invisible visual forgery.

### 9.6 Historical maps
- Separate 1) sourced period maps (raster/doc scan), 2) geometry-derived schematics built from **period-specific verified data**, 3) modern reference map (only as geography context, explicitly not historical boundaries).
- `MapAsset`: period_start/end, source/geometry version, date validity, projection, coordinates, labels, boundaries confidence, cited map source, `schematic=true/false`.
- Route diagrams require reviewed path/event chronology; animation must not infer unapproved roads/territory/vehicle movement.
- If exact borders/path data absent: asset unresolved -> G3 options; no silent interpolation from modern border dataset.

### 9.7 G-Labs image adapter — exact user document contract [U2]
- Local default base `http://127.0.0.1:8765`, configured via operator settings; webhook app running + MAX license; authentication header `X-API-Key` on private endpoints, secrets server-side only.
- `GET /api/health` preflight; `POST /api/image/generate` with `{prompt,model,aspect_ratio,reference_images,upscale?}`, supported model names per live options (e.g. `nano_banana_2`, `nano_banana_pro`, `nano_banana_2_lite`, `nano_pics`).
- Returns HTTP `202` with task_id → poll `GET /api/status/{task_id}` every ~3–5s → on `completed`, download each URL in `results` to immutable local file; on `failed`, surface `error_code/error/error_detail`.
- `GET /api/files/{filename}` URLs may be time-limited/evicted; never treat them as permanent project assets. Store locally + hash+MIME validation and prompt/provider/task lineage. `GET /api/tasks` only recent tasks; app stores its own durable ledger.
- For same Windows machine, `reference_images` supports `{path:"X:/..."}` (only if path lives on G-Labs host) or base64; avoid 50MB payload ceiling; `nano_pics` has distinct keep/reference semantics, so adapter validates model-specific payload.
- User-facing targeted Cancel -> `POST /api/stop/{task_id}`; never the global stop endpoint on an individual task. 429 quota does not trigger unlimited cross-account retries; controlled retries and clear pause.
- Generated image gets role `AI_ILLUSTRATION`; prompts should exclude embedded text/numbers when Remotion can render typography accurately.
- **Integration confidence:** spec based on supplied docs, not live authenticated test; G-Labs MAX/health/request/poll/download/cancel is a pilot gate.

## 10. Asset review UX and two-option failure policy

### 10.1 Asset Review Board (G3)
Per requirement row: exactness, intent, source type, thumbnail, candidate count, period match, factual relevance, rights, derivative preview, usage scene IDs, status and final decision. Summary filters `APPROVED | NEEDS_EVIDENCE | RIGHTS_UNCLEAR | MISSING | FALLBACK_CANDIDATES`.

### 10.2 Manual path
`ARCHIVE_ASSET_UNRESOLVED → USER_SELECTS_MANUAL → UPLOAD_PENDING → METADATA_REQUIRED → VALIDATION → G3_REVIEW → APPROVED/REJECTED`. User-provided URL/license assertion logged, not blindly accepted as fact. Manual file can be ordinary artwork/document/map; wrong type must not be coerced into archival photo.

### 10.3 Managed fallback path
`ARCHIVE_ASSET_UNRESOLVED → USER_SELECTS_MANAGED_FALLBACK → GENERATE/SEARCH_CANDIDATES → CANDIDATE_PREVIEW → HUMAN_SELECT + APPROVE → BIND`. Candidate cards include label *"context photo, not exact event"*, *"schematic reconstruction"*, or *"AI-generated illustration"*. User can return to Manual at any time. Managed fallback candidate **may consume G-Labs quota**; show estimated cost/quota and require option selection before dispatch.

### 10.4 Gate semantics
`G3 APPROVED` needs no missing required bindings; may permit optional decorative layers absent with explicit downgrade. `G3 APPROVED` is impossible if any used fallback candidate lacks a human approval record, regardless of user choosing managed path earlier.

---

# PHẦN B — VISUAL PRODUCTION & TEMPLATE DESIGN (STEP 02)

## 11. Video reference breakdown and editorial grammar

### 11.1 Evidence observed from `1015.mp4`
Contact-sheet sample frames every 5s, three bands: 
- ~0–10s: monochrome textured Europe/Balkans map with deep red territory, city text and date.
- ~10–90s: warm paper background, person cutouts with thin bright edge/drop shadow, black uppercase text, yellow emphasis blocks, red callouts; family/group archive photo cards.
- ~95–150s: incident sequence, photo cards + labels/dates/counts, newspaper/document/map inserts.
- ~150–170s: directional route diagram with street/vehicle blocks and turn annotations.
- ~175–210s: character cutouts, multiple caption reveals, stamp-like indicators.
- ~215–295s: global/Europe maps, numeric date/title cards, archive military images, region color highlights and consequence framing.

**Observed grammar:** different visual mode for different semantic purpose; mostly restrained collage rather than constant motion; layer additions often preserve context before a change. **Not observed/claimed:** specific easing curve, exact per-frame motion order, audio transcript factual accuracy or proof a historical image is authentic.

### 11.2 Core editing principles
1. **Narrative causality:** each setup must answer *what changed, why, and with what consequence?*; motion highlights causality rather than being decorative.
2. **Persistent Visual Setup:** retain the main visual across several spoken thoughts, selectively add/remove labels/callouts; no forced image-per-word/image-per-beat.
3. **Semantic matching:** persons→portrait; place/geography→verified map; movement→route; chronology→timeline; evidence→document/photo; scale→numbers/comparison.
4. **Readability before density:** every label has an estimated read window, text-safe area, contrast and hierarchy; if unreadable, suppress lower-priority decoration or split scene.
5. **Purposeful novelty:** avoid repeating same template > several consecutive scenes if another semantic presentation is valid; never swap to a semantically incorrect template solely for variety.
6. **Motion as emphasis:** allow quiet hold, especially on complex map or primary evidence. No mandatory animation running at all times.
7. **Conservative history visuals:** marks, lines and border overlays must agree with approved map geometry and claim.
8. **Truthful illustration:** AI/reconstruction labels are persistent when relevant, not concealed during emphasis.
9. **Visual continuity:** visual subject/camera origin and persistent layer IDs survive overlay/caption changes.
10. **Repeatable render:** all animations pure functions of frame, approved plan, fonts and immutable files; no `Date.now()`/runtime randomness.

## 12. Visual Style Profile `HistoryEditorialPaper.v1`

| Token family | Initial value/design hypothesis | Notes |
|---|---|---|
| Canvas | 1920×1080, 30fps, 16:9 | Render profiles later can expand; pilot uses this |
| Background | warm off-white paper with bounded subtle texture | fixed repeatable texture, don't create flicker |
| Ink | near-black `#1F1F1D` | body/headline; not pure #000 if aesthetic weak |
| Accent yellow | `#F1CB34` | impact figures/key terms, contrast test required |
| Accent red | `#C84B3F` | danger/event/date or territory highlight |
| Map dark | `#202629` | geography setup, overlay must remain readable |
| Map muted blue | `#8AAFC6` | secondary region emphasis |
| Photo treatment | grayscale/aged monochrome, optional white border/shadow/tape | no silent fake restoration |
| Type hierarchy | bold condensed-ish sans for headline; compact neutral sans for labels; optional monospaced document text | actual license/available Windows fonts must be frozen |
| Safe areas | base 6% horizontal, 7% vertical | responsive within output profiles; QA examines |
| Headline size | provisional 72–118 px at 1080p | long Vietnamese words may need alternate layouts |
| Labels/captions | provisional 30–46 px at 1080p | do not render tiny labels solely because sample has them |
| Motion style | restrained hard cuts, mask/text pop, slow pan, purposeful route draw | no generic random shakes/transitions |
| Caption mode | selective editorial text, **not** compulsory all-word subtitles | optional accessible full captions mode later |

Style Profile must version all tokens, typography assets, grid, background/texture seeds, color semantics, motion speed bands, shot-edit rules and feature availability. Theme selection must not mutate historical source images.

### 12.1 Camera and chronology grammar
- `GLOBAL → REGIONAL → LOCAL` for zoom geography; keep geographic anchor and labels near active target.
- `PORTRAIT → DOCUMENT → EVENT/ROUTE → CONSEQUENCE` when causal chain warrants; not mandatory 4-step rigid formula.
- Important year/number/title **land** on aligned word or held phrase; leave enough reading time after land.
- Multiple visual changes may happen in one setup without full cuts; use stable `setup_id` and `layer_id` lifecycle.
- Nonverbal pauses in final WAV can provide hold, but **do not add fabricated narration timestamps**.

## 13. Scene Template Registry `v1`

**Contract:** every scene template declares `template_id, version, semantic_intents, required_slots, optional_slots, compatible_asset_types, layout_variants, permitted_motion_presets, min/max visible content, behavior_on_missing, QC_constraints`. Template is prebuilt local code, not generated from ChatGPT code.

| ID | Template | Required slots | Variants / semantics | QC/invalid state |
|---|---|---|---|---|
| T01 | `MAP_TERRITORY_FOCUS` | period-valid map, focus region, validated labels | map wide / inset / compare; historical geography | wrong era or unapproved polygon = BLOCK |
| T02 | `PORTRAIT_EXPLAINER` | subject photo/art + name | solo left, solo right, duo; identity/biography | cannot assert exact historical person from uncertain image |
| T03 | `ARCHIVAL_PHOTO_COLLAGE` | 1–3 approved archive images, caption context | single polaroid, stacked, side-by-side | image/claim mismatch, unreadable caption |
| T04 | `ROUTE_RECONSTRUCTION` | reviewed path geometry + ordered events | city diagram, top-down timeline route | inferred road/turn without evidence = BLOCK |
| T05 | `CHRONOLOGY_TIMELINE` | valid events/years/source anchors | horizontal ladder, vertical editorial | incorrect order/time scale, overflow |
| T06 | `DOCUMENT_EVIDENCE` | approved page/image + citation/label | page zoom, taped document, multi-callout | exact quotation missing/false; document crop misleads |
| T07 | `TERRITORY_COMPARISON` | two **period-valid** map states | before/after wipe, side-by-side | incomparable projections/dates, wrong geometry |
| T08 | `FACT_NUMBER_IMPACT` | verified fact/number + unit/source | title-only, number with archive inset | number altered/generated or missing unit |
| T09 | `QUOTE_HEADLINE` | exact approved quote/title + citation when factual | typewriter, mask, headline stack | quote changes, omitted quote source |
| T10 | `GLOBAL_CONSEQUENCE` | world/regional map or sourced composition + labels | pullback + multi-region cues | implies unverified world impact, title overflow |
| T11 | `EVENT_CAUSAL_CHAIN` | two+ source-linked events/icons | card chain, arrows, false lead then correction | chronology/causality confused |
| T12 | `SOURCE_COMPARISON` | two evidenced source items or claims | split evidence, contradiction panel | treating conflicting accounts as identical |

**V1 target = T01–T10 production-ready; T11–T12 SHOULD if pilot reveals demand**, not needed to call initial V1 gate PASS. This avoids scope creep and still specifies extension points.

### 13.1 Template-level design sheets (implementer requirements)
For *each* template, final implementation package MUST contain: 1) visual examples with approved sample assets; 2) 2–3 layout variants; 3) slot specs + legal classes; 4) at least 2 motion plans; 5) small/large text examples including Vietnamese diacritics; 6) duration/word cue handling; 7) collision/readability test; 8) preview/output frame parity evidence; 9) negative fixture; 10) operator editor controls.

### 13.2 Top five pilot scene templates (minimal vertical slice)
- T01 Map Territory Focus: source/period map, region highlight, city dot, title/date, camera preset with bounded focus.
- T02 Portrait Explainer: portrait cutout or photo-card treatment, name/year, fact strip, optional secondary archive card.
- T03 Archival Photo Collage: 1–3 verified archives, taped frame and narrative callout, stagger only if readable.
- T04 Route Reconstruction: background sketch with evidenced road/path, animated vehicle/marker, step cue labels.
- T08 Fact Number Impact: date or number card, evidence label, entrance + hold + exit under spoken word cue.

**Pilot templates are deliberately limited to five**, but enough to reproduce core visual language and test a different history topic. Adding T05–T10 happens after both pilots prove reusable.

## 14. Motion Preset Registry `v1`

Motion Prompt source refs below reflect verified catalog names/IDs [S4–S5]. They are **inspiration/port provenance**, not claim the repo provides native Remotion presets. For each adopted component preserve MIT notices when source code/numbers are reused.

| Runtime preset ID | Motion Prompt reference | Typical use | Boundaries |
|---|---|---|---|
| `pop-in` | #001 Pop-in | stamp/date badge | subtle overshoot; avoid “cartoon bounce” for solemn events |
| `stagger-reveal` | #002 Stagger | grouped labels/archival cards | max related elements/readability |
| `route-line-draw` | #004 Line draw | reviewed path | path shape must come from approved map/route |
| `title-mask-reveal` | #005 Mask reveal | headline/date | enter then hold, no unplanned loop |
| `typewriter` | #006 Typewriter | source extract | verified text only; not for long paragraphs |
| `number-count` | #007 Count-up | figures | displayed intermediate values are decorative, final verified number exact |
| `kinetic-type` | #008 Kinetic typography | emphasis words | requires word timing QC, non-jitter text |
| `parallax-layers` | #016 Parallax | separated photo background/foreground | only if asset separation acceptable |
| `mask-transition` | #017 Mask transition | setup switch | no hidden crop that removes evidence context |
| `camera-pan` | #025 Pan | archive/map drift | keep subject in view |
| `camera-push` | #027 Dolly in as conceptual reference | focus on document/portrait | with flat photo this is **simulated 2D transform**, not literal physical dolly |
| `freeze-hold` | #040 Freeze frame | hold evidence/diagram | no unintentional static dead zone |
| `whip-pan` | #043 Whip pan | rare energetic transition | restrict intense/rapid flashing |
| `hard-cut` | #046 Smash cut concept | dramatic reveal | cut as punctuation not default for every sentence |
| `cross-dissolve` | #044 Cross dissolve | sober archive switching | bounded blending |
| `text-highlight` | in-house (no asserted Motion Prompt ID) | word emphasis | anchored to final word map |
| `map-region-wipe` | in-house SVG/Remotion | two valid historical regions | compare dates/projection match |
| `photo-card-enter` | in-house composition | archive framed card | frame/texture/shadow rules |

### 14.1 Preset contract
`MotionPresetDef`: stable ID/version, allowed target layer, frame-local pure transform function, `params_schema` (bounded durations/easing/distance/scale), reduced-motion alternative, visual-QC fixtures, source attribution. Never allow LLM-provided formulas/functions/executable JSX. A composition may combine independent presets with collision/priority rules (e.g. camera move behind title mask), not arbitrarily stack same transform.

### 14.2 Motion timing recommendations (provisional, must test)
- Entry ~0.25–0.85s; hold determined by speech and legibility; exit/cut ~0.15–0.65s where appropriate. **Do not stretch entry/exit solely to fill a scene**; extend hold instead (Motion Prompt porting guidance [S5]).
- Map camera pans SHOULD avoid excessive travel and keep annotation anchored in map world coordinates.
- Word highlight should appear on aligned cue or an explicit small offset, not based on character-count estimate.
- Use consistent motion hierarchy: primary subject first or simultaneous, title emphasis on relevant spoken word, supporting annotation later, sufficient final hold.
- If text too long, choose smaller validated layout variant or split/hold—not automatic microscopic font.

## 15. Automatic storyboard and motion compiler

### 15.1 Inputs and output
Inputs: `ApprovedStoryRevision`, `VerifiedWordTimingMap`, `ApprovedAssetSnapshot`, `VisualBlueprint`, `VisualStyleProfile`, `TemplateRegistryVersion`, `MotionPresetRegistryVersion`. Output: immutable `CompiledTimeline.v1` in frames + deterministic dependency fingerprint + diagnostics.

### 15.2 Compile order
1. Validate source signatures and cross-object identity; reject stale Story/Voice/Asset versions.
2. Resolve semantic intents to allowed template via **intent-to-template rules**. User may explicitly specify a valid ID; code does not generate new templates.
3. Group consecutive semantic utterances into **persistent setups** based on topic/subject/map focus, rather than one image per line. Stable setup IDs allow progressive reveal.
4. Resolve asset requirements to approved bindings. Missing/rights-unclear/illustration-unapproved = BLOCK, not fallback.
5. Resolve per-word IDs from alignment into integer frames, using consistent documented rational conversion and start/end clamping; ensure monotonic temporal ordering. Frame quantization choice frozen/tested; no duplicate zero-duration events.
6. Instantiate template layout variant based on text measured with actual loaded fonts, asset aspect/crop, safe areas and semantic emphasis. Reject/flag unresolved collisions and low readability.
7. Assign motion entrance/hold/exit to each layer; periods anchored to spoken start/end; visible text must meet estimated readability dwell or produce `READABILITY_INSUFFICIENT` with suggested re-layout/split.
8. Insert controlled transitions at setup boundaries, account for overlap frames **without shortening narration**.
9. Validate map source/date/route paths, evidence labels, image class badges, texture/source attribution policy.
10. Serialize in canonical order; compute fingerprint including every template/preset/style/font version; two compiles of identical frozen inputs yield identical canonical JSON bytes and deterministic target frames.

### 15.3 Failure behavior
- No approved exact photo → G3 asset BLOCK, not generate art.
- Unknown cue word ID → `INVALID_WORD_REFERENCE`, no synthetic timing.
- Required layout overflows → compiler tries compatible **bounded** layout variants; if none passes, G4 shows manual edit and targeted diagnosis.
- No approved era map → `MAP_SOURCE_REQUIRED` and G3 decision.
- Repeated visual motif → `EDITORIAL_VARIETY_WARNING`, not a reason to use historically inappropriate image.
- Renderer missing font/asset file → preflight hard fail with file ID and recovery action.

### 15.4 Sample timeline event (contract illustration)
```json
{
  "event_id": "evt_042",
  "setup_id": "setup_008",
  "layer_id": "headline_01",
  "layer_kind": "text",
  "preset_id": "title-mask-reveal",
  "start_frame": 3600,
  "duration_frames": 20,
  "cue_word_id": "w_0128",
  "params": {"direction": "up", "distance_px": 32, "easing": "ease_out"},
  "text_source": "approved_story:sec_008:headline_01"
}
```
Example frames/IDs are **not from the provided video**; in production the compiler must derive and validate them.

## 16. Storyboard editor and render requirements

### 16.1 Scene editing
- Main layout: scene strip + active scene Player + separate setup/asset/text/map/caption/audio tracks + inspector + QC panel.
- Common actions: change approved image within allowed binding, crop, move/scale, choose template layout variant, adjust entrance/preset duration, move word cue within validated range, edit **non-factual** decorative text, request copy/caption edit as a G1-affecting story change if factual.
- Apply local editing to draft revision; G4 re-review only affected scenes and global boundaries. Still produces **new approved timeline head**, never modifies prior approval.
- Preview and render read same Remotion composition and same local media copies; no independent CSS simulator.

### 16.2 Renderer
- Windows local Node process using pinned Remotion package versions and Chromium; `@remotion/renderer.renderMedia` consumes approved CompiledTimeline; optional FFmpeg/FFprobe for mux/verification [S1–S3].
- Output default **1920×1080, 30fps, H.264/AAC MP4** (video sample used HEVC; no obligation to match codec). Separate source artifact hashes for final WAV, fonts, image versions and timeline.
- Support user-visible render queue, progress, cancel, safe retry, crash recovery and after-render probe QC; protect process ownership on Windows.
- Export: video.mp4; JSON QC report; credits/attribution HTML/TXT/JSON; optional project snapshot zip with **no provider API secrets**.

### 16.3 Automated QC vs editorial judgment
| Test dimension | Machine-verifiable V1 | Human judgment at gate |
|---|---|---|
| Video/audio | fps, codec, duration, nonempty audio, black-frame/silence/anomalies | pleasant pace, expressive narration |
| Assets | required paths exist; hashes; declared license fields; no unknown class | authentic context, legal confidence where ambiguous |
| Timing | cues monotonic, inside WAV, no impossible frame interval | emphasis looks right, pauses natural |
| Layout | safe area, measured bounding box, text duration heuristic, collisions | pleasing composition and hierarchy |
| Motion | preset params valid, transitions bounded, frame parity fixtures | variation, rhythm and emotional tone |
| Historical facts | existence of citations and approved decision records | historical truth and avoidance of misleading depiction |
| Delivery | required files, source credits, exact head hashes | publication readiness |

**The renderer must not declare editorial PASS based solely on deterministic QC.**

## 17. Quality benchmark, pilot and acceptance

### 17.1 Test A — recreate reference language, not content plagiarism
Pick a licensed/approved 60–90s segment in subject family of Sarajevo reference: map→portrait→archive card→event route→emphasis title; compare frame contacts, readability, graphic hierarchy, controlled motion. Use **new production assets** and authored narration; do not copy copyrighted arrangement one-to-one.

### 17.2 Test B — cross-topic generalization
60–90s *German Unification 1871* or comparable verified topic, same 5 pilot templates, **zero project-specific JSX/JS edits** and same data contracts. New assets must be independently sourced; map-era verification required.

### 17.3 Acceptance gates — implementation evidence, not design assertion
| Gate code | Evidence for engineering PASS |
|---|---|
| E0 Build Integrity | Clean Windows fresh install/launch; Node/Python pinned; no old repo code/database; basic app/UI smoke |
| E1 Authoring | One JSON external import, valid + adversarial invalid cases, G1 versioned approval |
| E2 Voice | Real Kokoro + ElevenLabs sample; sections regenerate; final audio approval; ElevenLabs alignment with real word cues; language support test |
| E3 Archive | At least 2 archive adapters real searches, source/rights persistence, manual+managed missing asset resolution with human approval |
| E4 GLabs | Real server health→submit→status→download→scoped cancel under operator-provided test account; quota/error case |
| E5 Visual | 5 pilot templates/8+ motion presets; two topics; evidence no per-scene code; layout/overflow/timing golden frames |
| E6 Preview | Browser Player and rendered MP4 sample frames correspond on actual assets/fonts under defined image-diff tolerance |
| E7 Editorial | Director/editor/motion-design reviewers judge both pilots; targeted revisions possible without repeating unaffected stages |
| E8 Durability | Crash/cancel/retry, no duplicate jobs, scoped provider cancellation and immutable approval invariants |
| E9 Delivery | 60–90s two pilot MP4s H.264/AAC + QA/rights report; G5 manual approve; no unreviewed fallback |

**Targets**: 2 distinct 60–90s pilots first. Broader 4–6 minute reference-like video only after E0–E9 pass. Performance/cost/throughput SLAs are measured during pilot, not guessed now.

## 18. Implementation order — engineering plan, not phase bureaucracy

### M0 — Architecture & contracts freeze
Deliver this master spec, versioned JSON schemas/interface mocks, UI wireflow, error/status taxonomy, 5 approval state machine and 5 visual template designs. Exit: six-role spec audit passed with unresolved external tests explicitly tracked.

### M1 — End-to-end vertical slice (early actual MP4)
Fresh project + external Story JSON + G1/G2/G3 (minimal UI), Kokoro/ElevenLabs adapters + ElevenLabs align, manual licensed assets, 5 templates and Remotion, G4/G5, 60–90s MP4. No G-Labs required for the first infrastructure-render test if manually approved assets suffice, but G-Labs integration still V1 required.

### M2 — Archive + G-Labs + fallback branch
All three archive adapters as planned (prioritize two reliable first), asset rights board, missing two-option modal, managed candidates, G-Labs real webhook, deterministic derivatives, complete G3 and provenance report.

### M3 — Robust editor + full 10-template registry
Layer/cue/asset inspector, selective recompilation/invalidation, compare attempts, long-form UI performance, expanded 10 templates/presets and style variants.

### M4 — Production validation & packaging
Two-source topic pilots + one 4–6 minute full-length test, reference-style editorial QA, Windows one-click launcher, crash-resume, licensing/attribution package, user guide and quality gates.

**Not allowed:** call any milestone PASS based on mocks only; postpone real G-Labs/align verification forever; auto-merge/push main without user approval; resurrect legacy app database or code for convenience.

## 19. Risks and decision register

| ID | Severity | Risk / status | Mitigation or decision required |
|---|---|---|---|
| R01 | P0 | Vietnamese ElevenLabs Forced Alignment support unverified | Explicit language gate; English initial lane; actual provider test before `vi` certification; no unapproved provider substitution |
| R02 | P0 | Historic source copyright/provenance fuzzy | Mandatory G3 + source/right inspector + safe blocking and attribution, operator review |
| R03 | P0 | Silent fallback could falsify history | Hard code 2 user options, no auto fallback, fallback candidate approval |
| R04 | P1 | Template reuse yields boring repeated slideshow | 2–3 variants/template, persistent multi-layer setups, editorial pilot against video sample |
| R05 | P1 | Timing drift after voice correction | SHA-bound final WAV and aligned word IDs; invalidate G4/G5 on audio change |
| R06 | P1 | Historical map anachronism | Era-specific source/geometry and manual approval; no modern border substitution |
| R07 | P1 | G-Labs quotas / app offline / files evicted | health, provider task ledger, bounded retries, save local immutable copy, operator resolution |
| R08 | P1 | Generated picture falsely appears archival | Asset classification and disclosure label in visual template |
| R09 | P1 | Shot-specific code debt | Unknown template -> review/re-layout, never generate JSX, cross-topic pilot no code edits |
| R10 | P1 | Preview looks different from MP4 | One composition, pinned fonts/media and parity tests |
| R11 | P1 | Render crash/cancel loses job state | leased durable queue and Windows process ownership |
| R12 | P2 | Cost/quota surprise | provider model usage ledger and user opt-in for managed fallback |
| R13 | P2 | Remotion license obligations change with team size | verify vendor license at implementation/release [S10] |
| R14 | P1 | Claim research via ChatGPT hallucinated source leads | Source evidence verification and G1 manual claim review, never auto-confidence=verified |
| R15 | P1 | Readability on Vietnamese diacritics / font missing | font package/pinning + glyph coverage + 1080p long-text tests |

### 19.1 Open decisions — intentionally **not** assumed
- `D01`: final narration languages for initial release beyond English. Impact: Kokoro voice/model and ElevenLabs alignment test matrix. **Owner: operator**.
- `D02`: historical scope (global history or primarily European/modern), impacts archive datasets and maps. **Default for pilot: 19th–20th century Europe** only.
- `D03`: target output duration long-form, aspect ratios and voice budget. **Default pilot: 60–90s 16:9**; full validation 4–6 minutes.
- `D04`: allowed licenses/monetization policy and attribution styling (CC BY/CC BY-SA handling). **Default: license-aware review; block unknown**.
- `D05`: willingness to install optional image-processing models GPU/CPU. **Default: graceful photo-card behavior** if cutout unavailable.
- `D06`: G-Labs image default provider/model/paid quota under actual user account. **Default trial `nano_banana_2`, configured at runtime**.
- `D07`: image/text style similarity target (exact re-creation vs genre resemblance). **Default: genre-level visual grammar, not pixel imitation**.

---

# PHẦN C — SELF-AUDIT ACROSS SIX ROLES

## 20. Audit methodology and outcome
Each reviewer lens independently asks: **Can this design produce two different history videos in reference style without coding changes? Can operators fix failure without breaking previous approvals?** Issues were reviewed, incorporated into matching clauses (§ references), and reclassified. This is a **design-review result**; it is not evidence of actual product/video performance.

| Role | Main findings | Remediation included in this spec | Design judgment |
|---|---|---|---|
| **Director** | Risk of semantically random shot types, no cause/effect continuity, overuse novelty | §11 semantic grammar, persistent setups, source-context match; §13 templates with semantic conditions | PASS WITH PILOT TEST |
| **Scriptwriter / editorial observer** | Script claims not necessarily true, speculative depiction could imply documentary fact, only one external ChatGPT pass may be brittle | §6 claim source leads not verified; §2 G1; §9 content class; optional targeted repair | CONDITIONAL PASS |
| **Editor** | Audio changes invalidate cue timing; hard cuts can truncate hold; long scene should allow multiple additions | §2.5 invalidation, §8 real final WAV align, §11 persistent setups, §15 transition/hold constraints | PASS WITH PILOT TEST |
| **Motion Designer** | 120 prompts ≠ production presets; need variants, frame-specific deterministic effects, font/readability and map transform ownership | §12 tokens, §13 template sheets, §14 port license/constraints, §15 compiler checks | PASS WITH PILOT TEST |
| **Software Architect** | Provider coupling, missing data identity, unsafe external JSON, uncontrolled retries, preview/render divergence | §4–10 adapters, immutable SHA artifacts, scoped cancels, strict schemas, shared composition, job states | PASS WITH INTEGRATION TEST |
| **QA Engineer** | Vietnamese alignment unsupported risk; missing asset fallback loopholes; rights heuristics; complex dependency regression | §8.4 hard language gate, §2.4+§10 two-option approvals, §17 negative/real gates, §19 risks | CONDITIONAL PASS |
| **Operator** | Five gates can feel heavy; queue lacks visibility; manual missing-asset flow must be easy | §3 exception board + bulk review, §5 progress and recovery, §10 manual/fallback UX, review-action clarity | PASS WITH UX TEST |

**Additional sixth-role interpretation note:** user requested six roles: director, editor, motion designer, architect, QA and operator. The scriptwriter row is an added editorial viewpoint, **not a substituted role**.

### 20.1 Defects found in first design pass and repaired before this deliverable
1. **Critical: silently extending alignment support to Vietnamese** → now explicit `R01/D01`/§8.4 compatibility block with genuine provider test.
2. **Critical: fallback permission confused with fallback approval** → §2.4 and §10 separate authorization to search/generate from human approval of result; G3 cannot pass otherwise.
3. **High: vague archive rights** → §9.2–9.4 separate provenance, copyright eligibility and claim relevance; archive host ≠ clearance.
4. **High: one ChatGPT JSON implies invented absolute cue times** → §6 and §15 resolve only after final ElevenLabs alignment.
5. **High: Motion Prompt mistaken for ready-made Remotion motion package** → §4.1 and §14 require locally implemented tested presets with source attribution.
6. **High: repeated photos/persistent context ignored** → §11 and §15 group narration into long-lived setups; avoid one-image-per-beat slideshow.
7. **High: editor/voice revision cascades unnecessarily** → §2.5 dependency invalidation matrix and immutable revisions.
8. **High: no actual cross-topic proof** → §17 two distinct pilot topics with no scene-specific code and Player–MP4 parity.
9. **High: missing map-era truth gate** → §9.6 source-verified historical polygons/paths, no modern border shortcut.
10. **Medium: operator could trigger global G-Labs cancel accidentally** → §5 and §9.7 scoped task cancellation only.

### 20.2 Remaining design-only blockers / follow-up evidence
- **B01 (external / pre-implementation):** Check actual narration language and real compatibility across chosen Kokoro voice(s), ElevenLabs TTS and ElevenLabs **Forced Alignment** (Vietnamese unresolved).
- **B02 (external / integration):** Prove G-Labs MAX webhook health, create, poll, save, targeted cancel on the operator's machine. Supplied manual is not execution proof.
- **B03 (editorial):** Define a licensed set of archival assets + a period-specific map for both pilots; manually verify factual/copyright claims.
- **B04 (render):** Show actual five-template 60–90s pilot and full frame-based Player/MP4 parity; no video engine built in this task.
- **B05 (operator choice):** Confirm accepted output narration language(s), allowed content licenses and publishing region before locking release gates.

### 20.3 Final spec disposition
- **Product/Architecture spec:** **CONDITIONAL PASS** — sufficiently explicit for design and vertical-slice engineering kickoff.
- **Visual template spec:** **CONDITIONAL PASS** — concrete V1 registry/quality rules, but artistic quality remains unverified until 2 real pilots.
- **Provider integration readiness:** **NOT PASS / NOT TESTED** — intentional; must meet E2/E4 before claiming operational.
- **Historical source/rights readiness:** **NOT PASS / SUBJECT TO ASSET REVIEW** — no real pilot archive set audited here.
- **Implementation:** **NOT STARTED.**

---

## 21. Source register and provenance

### User-supplied primary inputs
- **[U1]** `1015.mp4` provided in this conversation. Local FFprobe measured 298.283991s, 1920×1080 @30fps, HEVC video, AAC audio; sampled contact sheets `vid_review/sheet_1.jpg`, `_2.jpg`, `_3.jpg` for visual analysis. No authoritative transcript or source authenticity of footage provided.
- **[U2]** `WEBHOOK_INTEGRATION.vi(1).md`, user-supplied local G-Labs Automation Webhook REST API documentation; §1–4 host/license/API-key/status, §5.1 image models and params, §6 reference images, §7–8 errors, stop and task semantics. Describes API contract, not proof that user's server is running.

### Repository and provider references (read at design time)
- **[S1]** Remotion GitHub README — https://github.com/remotion-dev/remotion
- **[S2]** Remotion Player docs — https://www.remotion.dev/docs/player
- **[S3]** Remotion renderer & transitions — https://www.remotion.dev/docs/api ; https://www.remotion.dev/docs/transitions/
- **[S4]** Motion Prompt README + actual 001–048 catalogs — https://github.com/showheyohtaki/motion-prompt ; https://github.com/showheyohtaki/motion-prompt/blob/main/packs/motion/README.md ; https://github.com/showheyohtaki/motion-prompt/blob/main/packs/camera/README.md
- **[S5]** Motion Prompt porting guidance — https://github.com/showheyohtaki/motion-prompt/blob/main/skills/motion-prompt/references/porting.md
- **[S6]** Motion Prompt MIT LICENSE — https://github.com/showheyohtaki/motion-prompt/blob/main/LICENSE
- **[S7]** ElevenLabs Forced Alignment API — https://elevenlabs.io/docs/api-reference/forced-alignment/create
- **[S8]** ElevenLabs Forced Alignment language overview — https://elevenlabs.io/docs/overview/capabilities/forced-alignment
- **[S9]** Wikimedia Commons external reuse policy — https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia
- **[S10]** Remotion licensing FAQ — https://www.remotion.dev/docs/license/pricing ; https://www.remotion.dev/docs/license/faq

### Intellectual property and evidence note
The design reproduces **genre-level visual mechanics**, not the exact authored arrangement of the reference footage; its original sources/licenses must be checked before reuse. Motion Prompt code porting retains required MIT notices. Archive images are copyrighted or license-governed individually. No redistributable archival content is embedded in this spec.

---

# APPENDIX A — Mandatory negative test matrix

| Test ID | Input/adversarial condition | Expected outcome |
|---|---|---|
| N01 | External JSON contains JS/JSX or arbitrary file path | schema rejects; no execution |
| N02 | Duplicate section/word/asset IDs | import fails with specific pointers |
| N03 | Unverified key historical claim | G1 cannot pass silently; evidence or operator explicit decision required |
| N04 | Voice approved but final WAV replaced | word map stale, G4/G5 invalidated |
| N05 | ElevenLabs alignment unsupported language | explicit BLOCKED_LANGUAGE_SUPPORT, not fake map |
| N06 | A G3 missing exact image but user has not selected option | no managed fallback task dispatched |
| N07 | User selects managed fallback, no candidate approved | G3 remains BLOCKED |
| N08 | AI illustration imported as ARCHIVAL_PHOTO | classification validator blocks |
| N09 | Archive source license missing | cannot silently rights-approve |
| N10 | Historical map uses current border geometry without period source | G3/G4 block |
| N11 | Source portrait photo cutout fails mask QC | downgrade visual treatment to photo-card candidate; no forgery |
| N12 | Text cue before word start/outside audio | compiler fails event |
| N13 | Long Vietnamese diacritics label overflows | re-layout or warning, no hidden crop |
| N14 | G-Labs returns HTTP202 but task later fails 429 | bounded retry/hold with visible quota status |
| N15 | Cancel one G-Labs job while others active | only matching provider task is targeted |
| N16 | Render crashes/restarts after output staging | only current owned attempt publishes |
| N17 | Change one approved asset derivative | only affected G3 binding and downstream scenes/render marked stale |
| N18 | Same input compiled twice | identical canonical timeline hash/frames |
| N19 | Player scene font fallback differs from render | parity test FAIL until font fixed |
| N20 | Unsupported/unknown preset | compile blocked; never generate code at runtime |
| N21 | Archival exact scene photo mismatch found by operator | reject candidate; do not auto-promote contextual photo |
| N22 | User upload metadata/license claimed but unverified | G3 review evidence warning; no auto-approve |
| N23 | Scene template forced across inappropriate semantic intent | rule blocks or requests operator override with audit trail |
| N24 | Retry after approval while source head changed | stale attempt cannot publish |

# APPENDIX B — Minimal UI acceptance walkthrough

1. Start clean Windows app; create project English, 16:9, `HistoryEditorialPaper.v1`.
2. Click Build ChatGPT Prompt; user imports single valid StoryPackage JSON; G1 shows claims and source leads; approve exact revision.
3. Launch Kokoro sample, compare alternate ElevenLabs voice, regenerate a single section; approve final voice; final WAV and ElevenLabs word timing hash visible.
4. Search Wikimedia/LOC candidates; mark one req missing; observe exactly two choices. Choose Manual, upload/source/approve; in another req choose Managed, produce illustration candidate but reject first, approve second and verify disclosure label.
5. Launch storyboard compile with 5 templates; watch Player, edit one portrait crop and one word highlight; approve G4. Verify no unrelated voice task reruns.
6. Render MP4; compare reference frames / codecs / audio, read credits and QC; approve G5; export deliverables.
7. Repeat with different history topic, **without changing any source code**.

**END — MASTER DESIGN SPECIFICATION V1.0 / CONDITIONAL DESIGN PASS**