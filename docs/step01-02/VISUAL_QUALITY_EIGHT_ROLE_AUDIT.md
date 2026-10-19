# EIGHT-ROLE FINAL SELF-AUDIT — VISUAL QUALITY CONTRACT V1.1
**Project:** Historical Video Studio | **Repository:** plthien/Historical-Video-Studio | **Scope:** four targeted P0 design repairs; no runtime implementation. **Method:** one systematic, adversarial self-review conducted through eight professional perspectives; this is NOT eight independent reviewers, NOT rendered-video QA, NOT official approval of historical or licensing claims.

## 0. Decision criteria and evidence
**Baseline defects (confirmed in prior audit):** three recycled layout geometries advertised as 30 variants; one-photo T03 / one-map T07 template structure; ungrounded generic motion IDs; StoryPackage visual setup missing beat-level staging and explicit object relationships; CompiledTimeline lacked render group/slot source mapping; prior synthetic 48 scenes were uniformly 2 layers + 1 animation.
**Artifacts inspected for repair:** strict StoryPackage/VisualBlueprint/CompiledTimeline/TemplateLayout schemas; 10 discriminated template payload branches; 30 distinct registry compositions; 19 specialized motion parameter schemas/phase recipes; source-aware annotations; visual editor revision provenance; ten multi-layer adversarial stage fixtures and 24-section/48-scene structural longform fixtures; scripts/validate_visual_design.py + tests/contracts/test_visual_design_v11.py; full-flow plan and API.
**Pass meaning:** the contract can represent targeted cinematographic setups and the offline validator can reject tested invalid configurations. **Not pass meaning:** actual generated scenes, aesthetics, image/source accuracy, animation easing, player/export parity and end-to-end auto-director quality are NOT demonstrated by CI.

## 1. Director (visual storytelling)
**Attack:** Do ten templates actually express different visual ideas, or just keep pushing a camera across one photo?
**Prior P0:** 30 variants were three recycled layouts and narration had no shot-level causal focus change.
**Repair evidence:** registry now explicitly differentiates collage, paired-era map, route+period map, vertical chronology, document close-up, event-to-consequence network and portrait placements. Every authored setup has 1+ visual beats with semantic action, focus, ordered staging, relationship and continuity group; one setup can persist across multiple beats.
**Tests:** ten adversarial scenes span T01–T10; 30 distinct geometry checks; beat focus/relationship refs reject unknown IDs.
**Residual runtime/P1:** no guarantee external ChatGPT will choose good scenes or overall 5–10-minute pacing. G4 must show filmic variation and approve after watching actual output, not just green schema.
**Verdict:** DESIGN FIX VERIFIED / creative quality UNPROVEN.

## 2. Editor (rhythm, continuity and audio)
**Attack:** Will visual reveals follow final spoken words, and will a repair create broken transitions or repeated generic shots?
**Repair evidence:** visual beats carry section/phrase occurrence, and CompiledTimeline staging has local start/end frames, entry/exit focus, active layer sets and continuity groups. 19 presets have event-local contiguous phases. Final seconds remain derived from approved WAV samples and ElevenLabs alignment, not draft WPM.
**Tests:** invalid staging frame intervals, absent camera focus, mismatched phase recipe, missing layer ID and out-of-bound frame must fail closed; original audio/QC suite remains separate.
**Residual runtime/P1:** reference video's exact shot cuts/easings not measured, so no exact imitation claim. Actual readable holds, pronunciation, music/SFX and cut pacing require full rendered footage.
**Verdict:** TIME REPRESENTATION FIXED / final editorial flow untested.

## 3. Motion Designer (layer quality, shot grammar, effects)
**Attack:** Can a T03 really render 3 independent photo cards with depth, or a T07 show two period maps, or a T04 show a route with waypoint progress?
**Repair evidence:** typed template payloads, three separate collage cards, route geometry+waypoints, chronological dated events, original document crop+quotation provenance, paired maps, evidence-backed causal arrows; CompiledTimeline layers include parent/group/source slot, crop, mask, transform origin, depth, typography, path and treatment.
**New design finding repaired during audit:** geographic route drawings were incorrectly reused for nongeographic timeline/causal graph connectors. V1.1 now has geographical route-line-draw on reviewed map-world geometry AND a separate editorial-connector-draw on annotation/canvas geometry. 19 specialized presets define typed params, phases, transform spaces and no runtime state.
**Tests:** scene role cardinality, missing second T07 map, invalid route ref, parallax missing near/far, incompatible layer/preset, swapped editorial/geographical geometry, unknown template slot and cloned layout.
**Residual runtime/P1:** real segmentation masks, consistent collage crop, typography kerning and GPU/CPU render performance cannot be proven by JSON.
**Verdict:** REPRESENTATION & BOUNDARIES FIXED / rendered beauty unverified.

## 4. Software Architect (system ownership and immutable sources)
**Attack:** Are story facts accidentally changed by a visual edit, or do scripts pass model-generated code into Remotion?
**Repair evidence:** Stage 1 semantic direction (no pixels), Stage 2 oneOf typed visual design per template and G4 revision, Stage 3 frame-ready layered render data. Template/motion registries stable; API source hashes and G1–G5 state-machine contract preserved. No arbitrary JSX from ChatGPT.
**Failure closed:** unknown G1 reference, fabricated source, stale map year, unsupported motion/layer/geometry and asset slot identity must never reach approved G4 timeline.
**Residual runtime/P1:** generated TS/Python models, SQLite transactions, renderer optimization and real source ingestion are still to be implemented. This audit is a contract freeze, not code architecture certification.
**Verdict:** CONTRACT OWNERSHIP FIXED.

## 5. QA Engineer (adversarial evidence)
**Attack:** Can the suite distinguish schema-valid slideshow shortcuts from multi-layer production requirements?
**Repair evidence:** visual_cases has ten separately typed setups with 3–5 layers and two or more event tracks, a three-beat staging sequence per setup and negative mutations. 24-section longform fixtures remain structural/synthetic, and are explicitly not being passed off as a rendered visual benchmark. A dedicated Windows visual validator runs with existing contract suite.
**New negative coverage:** clone geometry, wrong hero card reveal order, unknown G1 beat focus, wrong map year, unverified verbatim quote, bad route geometry, editorial connector swapped into period route, unsupported motion space, bad camera target, missing two maps, G4 edit tampering with protected G1 source.
**Residual QA:** need real media/wave tests, font and decode frames, source rights, 5–10 minute MP4 output and same-Composition parity. No synthetic “historical truth” success.
**Verdict:** DESIGN TEST COVERAGE IMPROVED / MEDIA QUALITY NOT TESTED.

## 6. Solo Operator (workflow and review effort)
**Attack:** Will the studio demand manual coding for each shot or require resetting approvals when only a crop changes?
**Repair evidence:** G4 edits are revisioned through a scene editor and a new direction-revision API, with original G1 story claim/cue locked. The schema can express multi-beat storyboards without writing JSX for each video. G2/G3 changes invalidate precise downstream dependents, not everything; archival fallback is explicit and never automatically approved.
**Residual runtime/P1:** current UX mock is illustrative only. Production UI must expose 30 variations as semantic options, with preview, per-layer evidence, safe reset/undo, responsive inspectors and bulk source review.
**Verdict:** WORKFLOW REPRESENTABLE / live operator UX unproven.

## 7. Senior Full-stack Developer (Python–TypeScript implementation friction)
**Attack:** Can a developer connect imported JSON to player/render without inventing hidden fields, and can local scene edits be implemented without bypassing G1?
**Repair evidence:** CompiledTimeline requires template_slot_id + source_asset_slot_id in every layer; scene layouts and motion params resolve from version-pinned registries; typed 10-way VisualBlueprint payload schema and per-preset parameter_schema provide implementable decoder boundaries. The validator checks source slot role/cardinality, render group edges, ordered phases and camera focal layers.
**Additional blocker found and fixed:** G4 visual beats originally had exact-equality requirement with G1 direction, making legitimate local staging edits impossible. Direction_revision now allows explicit operator_visual_edit of presentation-only fields while protecting claim refs, narrator cues, source slots and factual screen text. Added 26th API operation for G4 direction edits without exposing claim mutations.
**Residual implementation risk:** JSON Schema to TypeScript/Pydantic generators must preserve oneOf discriminators, strict nullable arrays, param validation, error codes and asset hash provenance. Cross-language parity tests and browser/Node rendering are required; only data-contract test is green.
**Verdict:** DEVELOPER HANDOFF DESIGN FIXED / executable application unbuilt.

## 8. Business Analyst (requirements traceability and acceptance)
**Attack:** Do “30 variants”, “19 presets” and “Full Flow” actually translate into concrete user-visible behavior instead of feature-label counts?
**Acceptance traceability:**
- R-VIS-01 (readable historical storytelling): Story visual_beats→Blueprint typed staging→Timeline beat windows→G4 scene review→actual MP4 evidence.
- R-VIS-02 (evidence integrity): G1 factual claim→required asset slot→G3 approved source/rights→layer source_asset_slot_id and badge→G5 attribution.
- R-VIS-03 (reusable multi-shot grammar): T01–T10 specialized payload + 30 role-specific variants + validator negative fixture→two different full-length stories rendered without custom JSX.
- R-VIS-04 (truthful maps/diagrams): dated historical map/route only with G3 period evidence; editorial timeline/causal connectors are distinct nongeographic annotation geometry; G4 cannot conflate.
- R-VIS-05 (operator correction): G4 presentation-only direction revision stores source story SHA and selected paths; story fact/narration changes route to G1, asset provenance changes route G3.
- R-VIS-06 (No pilot distraction): same full production codebase implements all 10 templates and full 5–10 minute pipeline; 60–90 second technical smoke tests are not a separate product milestone.
**Missing final acceptance evidence:** Actual 5–10 minute MP4 and end-to-end review of rendering quality under user content. This is a future implementation gate, NOT a P0 unfilled data field.
**Verdict:** DESIGN REQUIREMENTS TRACEABLE / user-outcome acceptance OPEN.

## 9. P0 closure summary / nonblocking outstanding risks
| Original P0 item | Design closure and tests | What remains for implementation |
|---|---|---|
| Cloned layouts / non-template-specific slots | 30 distinct layout geometry + role cardinality per template, typed payload and tests | Real React templates/font/asset variations |
| Missing beat-level multi-layer visual direction | visual_beats, staging/relationship/continuity refs, G1 protection and negative tests | External ChatGPT actual quality and G4 preview |
| Generic motion & camera grammar | 19 typed motion params, frame phases, layer depth, camera focus/slot lineage, route vs editorial connector split | Deterministic frame evaluator and visual parity |
| Weak examples/negative coverage | ten adversarial scenes, 24-section synthetic scale fixture, Windows suites and adversarial mutations | Real historical sourcing, G3 approvals, full-length video |
| Full-stack review additional | versioned G4 visual-edit revision and API, immutable G1 source refs and slot mapping | Type-generation/browser/API integration |
| BA review additional | explicit R-VIS-01..06 mappings and acceptance labels | Actual operator validation of full flow |

## 10. Decision and guardrails
**Design-level P0 closure: PASS only when latest Windows CI at exact committed SHA is green.** Full application **NOT IMPLEMENTED**. Reference-video aesthetic equivalence **NOT VERIFIED**; a contract can represent multi-layer motions but cannot ensure their beautiful execution. Do not overclaim synthetic fixture quality or real historical rights. Codex implementation should consume repaired schemas + registries + this audit, and test all ten templates on genuine media inside the full-flow application without disposable pilot.
