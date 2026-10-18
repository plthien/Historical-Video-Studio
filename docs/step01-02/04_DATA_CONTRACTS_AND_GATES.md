# 04 — DATA CONTRACTS & FIVE GATES · V1.0
**Authority:** Step 01/02 frozen contracts; implementation evidence still belongs to Step 03. JSON Schema sources live in contracts/schema/*.schema.json (Draft 2020-12); HTTP surface in contracts/openapi.yaml; examples in contracts/examples; offline checks in tests/contracts.

## 1. Canonical source of truth
- **User-imported one file:** StoryPackage.v1, containing approved-to-be-reviewed sections, claim source leads, asset requirements and visual_setups. The package is untrusted creative intent; imported metadata is not historical truth or rights clearance.
- **Internal normalized data:** VisualBlueprint.v1 resolves scene/template intents after story review; audio artifacts after TTS; WordTimingMap.v1 after approved final WAV; HistoricalAsset/AssetResolution.v1 after archival review; CompiledTimeline.v1 after G2/G3; ApprovalRecord.v1 per gate; RenderJob.v1 after G4.
- **Strict version strategy:** reject unknown schema_version, unknown fields, unrecognized template/preset/provider IDs, code/html/script fields, unsafe IDs and arbitrary filesystem paths. Migration is an explicit later versioned operation, never silent.
- **Serialization:** canonical UTF-8 JSON with lexicographically sorted keys, stable ordered arrays, no NaN/Infinity; SHA256 on canonical bytes. Revision hash identifies the exact artifact under review. String content and source leads are data only, not prompts to be executed.
- **Runtime-validated relationships** cannot be encoded reliably in standalone JSON Schema. Semantic validators MUST validate them explicitly and produce structured errors.

## 2. Exact schema and producer/consumer matrix
| Schema | Producer | Consumer | Gate |
|---|---|---|---|
| StoryPackage.v1 | external ChatGPT JSON, manually imported | story/claim validator, AssetRequirement index, blueprint normalizer | G1 |
| VisualBlueprint.v1 | normalizer + operator edits | compiler | G1→G4 |
| VoiceRequest.v1 | selected G1 text + provider controls | Kokoro/ElevenLabs TTS adapters | G2 |
| FinalAudio.v1 | assemble approved attempts from G2 | ElevenLabs alignment + renderer | after G2 |
| WordTimingMap.v1 | ElevenLabs Forced Alignment normalizer | cue compiler, G4, QC | before G4 |
| HistoricalAsset.v1 | archive/G-Labs/manual import → evidence records | G3 + scene asset resolver | G3 |
| AssetResolution.v1 | G3 operator choice/approval | orchestrator, G3, compiler | G3 |
| ApprovalRecord.v1 | user decision transaction | dependency ledger | G1–G5 |
| CompiledTimeline.v1 | deterministic compiler | shared Remotion Composition / editor | G4→G5 |
| RenderJob.v1 | render queue | worker/QC/G5 | G5 |

**OpenAPI is design-level, not running endpoints.** JSON examples are fixtures, not historically sourced proof or media. Data types/IDs are implementation authority until amended with versioned ADR.

## 3. Semantic validator V1 rules (failure codes)
| Code | Hard invariant | Repair |
|---|---|---|
| SECTION_ID_DUPLICATE | unique sections and ordered narration | regenerate/import corrected file |
| CROSS_REFERENCE_MISSING | every section, claim, req, setup reference exists | edit import JSON |
| CLAIM_CRITICAL_UNRESOLVED | no unresolved critical claim at G1 approval | human research/approve contextual rewrite |
| PERIOD_INVALID | requirement.start_year <= end_year | fix dates |
| PROVIDER_LANGUAGE_UNSUPPORTED | TTS/align support selected language | choose English or supported provider policy |
| FINAL_AUDIO_STALE | audio text/source hash differs from approved script | regenerate/approve G2 |
| WORD_RANGE_INVALID | 0 <= start < end <= final audio samples, monotonic | alignment retry, manual voice correction |
| WORD_MAP_STALE | map hashes do not match final WAV/transcript | rerun ElevenLabs alignment |
| REQUIRED_ASSET_MISSING | required binding unresolved or not approved | manual upload or user-authorized managed fallback |
| FALLBACK_NOT_AUTHORIZED | auto fallback attempted with NONE/MANUAL choice | ask user |
| FALLBACK_NOT_APPROVED | candidate generated but operator not approved | G3 candidate review |
| RIGHTS_REVIEW_REQUIRED | rights unknown / not established | source/legal review |
| MAP_PERIOD_MISMATCH | map date/region source not valid for story event | replace approved map or mark schematic truthfully |
| INVALID_CUE_WORD | event cue not in frozen WordTimingMap | remap cue/repair storyboard |
| SCENE_RANGE_INVALID | scene or event outside 0..total_frames, non-positive duration | recompile |
| LAYER_REF_MISSING | event references missing scene layer | repair blueprint |
| ASSET_BINDING_STALE | scene asset ID missing from exact G3 approved snapshot | rebind/reapprove |
| INVALID_PRESET | preset not allowlisted or params out of bounds for layer kind | choose supported preset |
| TEXT_OVERFLOW | no validated layout variant for readable content | shorten split/relayout |
| GATE_ILLEGAL_TRANSITION | stage not READY_FOR_REVIEW or predecessor missing | show required action |
| APPROVAL_REVISION_CONFLICT | expected_revision / candidate SHA mismatch | refresh review and approve exact revision |
| RENDER_REVISION_MISMATCH | MP4 belongs to old G4 timeline/asset/audio | rerender |
| ATTRIBUTION_INCOMPLETE | source/rights credits missing | complete credits before G5 |
| PROVIDER_TASK_TERMINAL | 4xx invalid or permanent provider refusal | show actionable error |
| PROVIDER_RETRYABLE | provider temporary failure/quota | retry bounded or wait |

Mandatory: validation errors include {code, path, entity_id, gate, message, remediation, severity}. Never substitute fake success or fake word times. Distinguish errors from editorial warnings.

## 4. Gate transitions and exact approval records
Every G1–G5: DRAFT → PREPARING → READY_FOR_REVIEW → (APPROVED | CHANGES_REQUESTED | REJECTED). BLOCKED can originate in preparation or pre-approval validation; resolve → PREPARING. STALE is a retained old approval that no longer authorizes the latest dependency fingerprint; produce new candidate READY_FOR_REVIEW after repair.

**G1** candidate: canonical imported story revision; critical claims have reviewed dispositions and source links as applicable, operator explicit review. No factual certainty inferred from ChatGPT alone.
**G2** candidate: voice attempts and intended final audio assembly plan; Approve invokes assembly and ElevenLabs alignment as one downstream workflow; failed alignment does not erase human audio selection but blocks G4.
**G3** candidate: per-asset/version evidence and rights; required binding approved exact version. Missing historical asset has **two options** only, manual upload or user-authorized fallback+later review. Per-item fallback authorization must be persisted and is NOT candidate approval.
**G4** candidate: compiled timeline revision with all G2 alignment/G3 bindings PASS and visual diagnostics available; approval pins style/font/scene registry versions and exact asset/audio hashes.
**G5** candidate: exact rendered MP4 digest with technical QC + attribution and operator visual/audio check. Separate RENDER_COMPLETED from FINAL_APPROVED.

Approve algorithm transaction:
1. load candidate, expected_revision and dependency hashes; reject if stale/missing.
2. check required predecessor gate statuses and semantic rules; G2 and G3 are parallel, G4 requires both plus valid alignment.
3. persist ApprovalRecord and new approved head atomically; increment project revision.
4. enqueue only downstream jobs tied to that dependency fingerprint.
5. return approval id, new gate status and next eligible action. Reject double click / stale expected revision with 409, not duplicate approval.

## 5. Invalidation and localized recovery
| Edit | Invalidates/reviews | Preserves |
|---|---|---|
| change story narration/critical claim | G1 revision; dependent G2, word map, blueprint/G4 and G5; affected asset relevance G3 as applicable | unrelated immutable media |
| regenerate voice section / change final WAV | G2 audio decision, word map, impacted timed scenes/G4, G5 | archived asset originals + provenance |
| replace one image / correct rights | affected G3 row/bindings, corresponding G4 scenes and G5 | Voice, other assets/scenes |
| adjust scene layout/preset/cue | G4 scene draft and G5 | G1/G2/G3 |
| rerender same pinned timeline | G5 render candidate only | G1–G4 approvals |
| change map era evidence | related G3/map scene and downstream | unrelated audio |

A scene edit is never allowed to mutate exact factual wording in approved StoryPackage without G1 revision; create focused “request story correction” action.

## 6. Dependency fingerprint and normalized media
Audio assembly uses explicit sample offsets; WordTimingMap always binds final audio_sha256 and transcript_sha256 and uses native integer samples, not floating scene time. CompiledTimeline references that word map and approved assets; Node and Player map frame = current Remotion frame. Frame conversion: start_frame=floor(start_sample*fps/sample_rate); end_frame=ceil(end_sample*fps/sample_rate), clamp to scene; ensure min 1 positive frame. Render worker consumes only frozen CompiledTimeline; no outgoing model queries while rendering.

Do not infer word identity from text alone when repeated; word_id is stable within one timing map, not across audio revisions. If text “war” occurs twice, cue must reference explicit occurrence/word_id.

## 7. Public local API (proposed)
API paths and response models are specified in contracts/openapi.yaml. POST approval and any job-start endpoint requires Idempotency-Key and expected_revision fields. API returns 202 for queued work, 200 for synchronized reads/decisions, 409 stale/invalid transition, 422 malformed schemas/references, 424 upstream missing, 429 provider quota, 503 unavailable provider. Every async operation returns job_id immediately; UI displays RUNNING on click, handles polling/resume. No named route exposes provider keys or arbitrary disk paths.

## 8. Negative tests required before Step 03
- duplicate section ID, dangling claim ref, nonexistent asset requirement, invalid period;
- visually plausible AI illustration marked ARCHIVAL_PHOTO;
- unresolved historical asset silently switched to image generation;
- managed fallback generated with no authorization; authorized but unapproved candidate used;
- wrong rights claim, missing source/creator fields; uploaded local file falsely considered approved;
- G2 approved but alignment failed; old map used after new final WAV;
- cue word missing, non-monotonic timestamps, event overruns scene, wrong map year;
- unknown template, unknown preset, illegal param, unreadable long headline;
- stale approve after concurrent edit; G5 passes render of previous timeline;
- cancel one G-Labs task cannot cancel a different task; crash/recovery doesn't duplicate submitted job.
Make fixture versions valid+invalid and ensure every hard failure returns stable code and gate remediation.

## 9. Step 01/02 contract review PASS criteria
All schema files JSON parse under Draft 2020-12 and validate at least one positive instance and documented negative instances. Semantic cases have implementation functions identified. Every UI control has an intended API and permitted transition; no inert approve/cancel. Nothing here asserts live G-Labs/ElevenLabs provider test or functioning Remotion renderer.
