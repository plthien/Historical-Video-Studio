# FINAL SIX-ROLE DESIGN AUDIT — STEP 01 + STEP 02
**Product:** Historical Video Studio (clean new build) | **Date:** 2026-10-19 | **Scope:** design contracts, UX wireflow, scene-template grammar and implementation handoff.  
**Method:** six adversarial professional perspectives applied to design artifacts and executable *offline* contract fixtures. This is **a structured self-review**, not six external human assessors, not a review of a working app, and not historical fact verification.

## Review boundary, evidence, and vocabulary
**Inspected:** original MASTER_DESIGN_SPECIFICATION_V1.md + original SIX_ROLE_DESIGN_AUDIT_V1.md; DECISIONS_2026-10-19; detailed 01–05 docs; 10 V1 schema files and 10 fixtures; semantic validator + Windows CI; local OpenAPI proposed surface; HTML UX mockup; 10 scene sheets and user reference video 1015.mp4.
**Design PASS** means requirements, interfaces, negative cases and handoff constraints are internally specified and inspectable. **Implementation PASS** will require working Windows app/provider calls, real Remotion video and editorial review and is not asserted here.
**English-first override:** Vietnamese ElevenLabs alignment is **not** a Step 01/02 blocker. **G-Labs override:** build from user's documented webhook, no mandatory live call for design/code kickoff. Actual provider behavior remains untested.

## 1. Director / Narrative Design
**Attack question:** can a fact-heavy script be told with visual cause–effect rather than interchangeable photo zoom?
- DIR-F01 (high): one narration sentence = one generated image gives slideshow repetition. **Closed in design:** 03 §4, §8 persistent setups and layer reveal grammar. Target scene sequencing from map → portrait → archive collage → route → fact, tied to semantic intent.
- DIR-F02 (high): motion selection by visual novelty may misrepresent story. **Closed in design:** intent-to-template mapping + exact asset role and G1/G3 evidence constraints; variant changes cannot change facts.
- DIR-F03 (high): no place for holding context after the key revelation. **Closed in design:** first establish subject, then reveal, hold according to aligned speech, then consequence; 2–3 variants/template, not continuous pan.
- **Open Step 03 validation:** two different topics must reuse same templates with convincing cause–effect and not repetitive gimmicks. Design alone cannot prove cinematic quality.
**Director verdict:** DESIGN PASS / VISUAL PILOT REQUIRED.

## 2. Editor / Audio and Timing
**Attack question:** will edits move speech, text and transitions out of sync or invalidate entire project?
- EDT-F01 (critical): sections generated in separate attempts; fake WPM-derived cue timings drift. **Closed in design:** FinalAudio sample-hash + assembled final WAV → separate ElevenLabs Forced Alignment → word sample map → compiler frames.
- EDT-F02 (high): overlapping alignment words not rejected by first validator despite individually valid words. **Fixed and regression tested:** semantic validator checks non-overlapping monotonic intervals; failing initial Windows CI repaired, subsequent success evidenced in workflow runs.
- EDT-F03 (high): changing one visual asset inadvertently regenerates full audio. **Closed in design:** exact dependency matrix, selective scene draft invalidation.
- EDT-F04 (medium): soundtrack mix may bury narration. **Scope decision:** Step 03 PoC permits voice-only. Step 04 BGM/SFX must define loudness, ducking and tail QC before inclusion; avoid pretending fixed preset exists.
- **Open Step 03 validation:** real TTS pronunciation, English alignment timing, joins/pauses, wave-end and browser/export audio sync.
**Editor verdict:** DESIGN PASS / AUDIO QUALITY DEFERRED TO PILOT.

## 3. Motion Designer / Template Practicality
**Attack question:** can in-house templates render as well as the reference rather than exposing arbitrary motion IDs?
- MOT-F01 (high): motion-prompt library mistaken for ready-to-render Remotion components. **Closed:** docs 03 + source port guidance; licensed selected motion recipes compiled into bounded in-house preset registry.
- MOT-F02 (high): T05–T10 were initially too shallow relative to pilot five. **Repaired:** supplementary T05–T10 design sheets supply required slots, A/B/C variants, cues, controls, limits, fixtures and negative cases.
- MOT-F03 (high): route-line-draw could be assigned to a non-route layer. **Repaired in semantic validator with negative test** and target-layer constraints.
- MOT-F04 (high): cutout artifacts and font/caption collisions make archive motion look cheap. **Closed in design:** portrait photo-card visual-treatment option; measured font and collision diagnostics; safe margins, textured-paper token rules and frame parity expectation.
- **Open Step 03 validation:** actual entrance/hold/exit stills, fonts on Windows and clean cutout mask on real archive images; motion parameters are provisional and not exact reference-video measurements.
**Motion Designer verdict:** DESIGN PASS / RENDERED LOOK UNKNOWN.

## 4. Software Architect / System Boundaries
**Attack question:** is the application extendable, deterministic and resistant to stale or unsafe inputs?
- ARC-F01 (critical): ElevenLabs synthesis and forced alignment conflated. **Closed:** TTSAdapter registry for Kokoro/ElevenLabs, separate ElevenLabs AlignmentAdapter for both final WAV sources.
- ARC-F02 (critical): external ChatGPT can inject code/URLs and bypass renderer logic. **Closed at schema design:** strict enums/no arbitrary executable keys, immutable source-bound IDs and no JSX execution from JSON. Implementation must additionally sanitize network/download and protect local paths.
- ARC-F03 (critical): gate approval accepted while project revision has changed. **Closed in contract:** candidate SHA + dependency fingerprint + expected_revision atomic CAS; semantic checker has stale revision case.
- ARC-F04 (high): confusing duplicate Voice Approve API bypassing G2. **Repaired:** single gate endpoint POST /gates/G2/decision, which triggers approved WAV assembly + ElevenLabs alignment.
- ARC-F05 (high): renderer may differ from preview. **Closed in architecture:** same HistoryComposition, pinned font/asset/timeline versions for Player and renderer.
- **Open Step 03 validation:** durable SQLite transactions/jobs, provider cancellation, real preview–export parity and idempotency on Windows.
**Architect verdict:** DESIGN PASS / RUNTIME IMPLEMENTATION NOT STARTED.

## 5. QA / Adversarial Negative Cases
**Attack question:** which historical, approval and integration failure conditions sneak through valid JSON?
- QA-F01 (critical): silent fallback when no exact photo. **Closed:** two explicit options, persisted per requirement; operator authorization != candidate approval != collective G3 approval. Negative regression checks.
- QA-F02 (critical): G-Labs generated illustration may masquerade as archive source. **Repaired:** origin glabs_webhook cannot classify as ARCHIVAL_PHOTO; regression check.
- QA-F03 (high): map approved without date support. **Repaired:** HistoricalAsset period fields and G3 semantic validator; negative case blocks.
- QA-F04 (high): malformed OpenAPI $ref parser in static design-integrity test created a false failure. **Repaired:** parse YAML mapping and walk $ref values, not regex against inline YAML.
- QA-F05 (high): validated shape doesn't prove historic accuracy or reuse permission. **Explicit human review boundary:** G1, G3, G5 approval records; output credits lineage, rights unknown stays unresolved.
- QA-F06 (high): planned Windows tests could be green only on mocks. **Report rule:** separate Contract CI PASS from Step 03 real provider and MP4 PASS; do not equate them.
- **Open implementation:** map/source historical verification, real providers, renderer parity, final MP4 QC, correctness of visually inferred dates.
**QA verdict:** DESIGN PASS WHEN LATEST WINDOWS CI GREEN; COVERAGE IS DESIGN-SCOPE ONLY.

## 6. Solo Operator / Workflow UX
**Attack question:** are five gates confusing and do failures demand terminal/coding-agent use?
- OPS-F01 (high): five gates cause excessive individual clicks. **Closed in wireflow:** one gate-level approve per phase plus batch candidate evidence review; exception queue and filter; no auto-approve shortcut.
- OPS-F02 (critical): selecting fallback option mistakenly means image accepted. **Closed in UI/API:** route selection button ≠ preview candidate approval ≠ G3 gate approval. Explicit checkbox in mock models the human review moment.
- OPS-F03 (high): click appears inert during a long provider operation. **Closed in API+UX design:** UI immediate processing state + job ID + idempotency/cancel/polling. Interactive HTML mock demonstrates only state machine, not real async work.
- OPS-F04 (high): approval might silently skip G2/align or G4. **Closed:** global gate board and next-valid-action; G4 waits G2 alignment+G3, G5 waits actual render+human sign-off.
- OPS-F05 (medium): 1366px Windows laptop vs wide timeline. **Closed in design:** adaptable inspector layout and viewport, keyboard target. Test mock layout with real browser in Step 03.
- **Open Step 04 validation:** large collection performance, actual keyboard/a11y ergonomics, crash resume and one-click start.
**Operator verdict:** DESIGN PASS / REAL USABILITY VALIDATION DEFERRED.

## 7. Cross-role contradiction and implementation blocker register
| Ref | Conflict tested | Resolution / owner |
|---|---|---|
| X01 | One ChatGPT JSON vs two artistic passes | StoryPackage contains semantic visual_setups; only optional targeted external repair; all normal scene edits local UI. Step 03 validate quality of one-pass authoring. |
| X02 | Full auto vs mandatory five gates | Auto jobs *between* explicit G1–G5; no provider task or compiler ever auto-approves human review. |
| X03 | G2 approve then alignment fails | Preserve approved voice selection; alignment job BLOCKED, G4 cannot start; user retry or voice correction, no sixth gate. |
| X04 | “Fallback” also used for cutout failure | Visual treatment photo-card of same approved original permitted; **historical asset substitution** requires explicit G3 resolution choice and later approval. |
| X05 | Right to reuse vs accuracy of depicted event | Rights and historical relevance remain independent, operator evidence review required; archive host alone proves neither. |
| X06 | English-first vs 1015.mp4 Vietnamese sample | Visual style is the reference; primary new narration English; no claim of Vietnamese forced alignment. |
| X07 | G-Labs contract-first vs unverified operation | Implement from user's API contract and mock tests; user live test deferred, never labeled operational PASS. |
| X08 | Five Step 03 templates vs ten V1 templates | Pilot T01/T02/T03/T04/T08; full V1 T01–T10; supplemental design sheets avoid missing spec. |
| X09 | Source sample and route too imprecise for real map | G3 blocks any unresolved exact map/route; schematic only when authorized/labelled, not silently generated. |

## 8. Design-only exit checklist
- [x] Five independent design documents, explicit scope and Step 03/04 owner breakdown.
- [x] Five review gate states/inputs/outputs and selective dependency invalidation specified.
- [x] Separate Kokoro/ElevenLabs TTS adapters; ElevenLabs alignment over approved final WAV.
- [x] G-Labs documented async provider contract + deferred live integration evidence noted.
- [x] Archive missing two-option resolution and human review, source/rights separation.
- [x] Ten template sheets with pilot five specified in extra depth and motion preset allowlist.
- [x] Ten strict schema shapes + fixtures + offline semantic negative test code.
- [x] Proposed API endpoints and six-screen interactive UX mockup plus action-to-API mapping.
- [x] Windows-only CI on contract shapes and semantic negative tests (require final SHA green).
- [ ] **Step 03:** two real 60–90-second videos and exact source attribution.
- [ ] **Step 03:** true Windows Remotion Player/renderer parity and actual English aligned speech.
- [ ] **Step 04:** archive adapters, fully working G-Labs and real render queue/editor end-to-end.
- [ ] **Step 04:** final 4–6 minute video and Windows packaged application.

## 9. Final decision
**Step 01 + 02 = DESIGN PASS** when the latest Windows design-contract workflow passes. “DESIGN PASS” asserts frozen and testable contracts, not video quality, copyright clearance, real G-Labs API execution, live ElevenLabs outcomes or functional UI/backend. If latest workflow is red, revert status to BLOCKED until resolved. Step 03 is next, not an additional new “M0” phase.

**Handoff:** use docs/step01-02/01–05 with 03's supplemental template sheets, contracts/schema, contracts/openapi.yaml, contracts/providers and the UI mock as authority. Original Master Spec and 2026-10-19 decision record remain provenance; overrides take precedence when text conflicts.
