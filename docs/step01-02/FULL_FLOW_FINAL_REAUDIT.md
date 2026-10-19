# FINAL TARGETED RE-AUDIT — FULL-FLOW DESIGN REPAIR (2026-10-19)
**Repo:** plthien/Historical-Video-Studio, Windows-only clean new application. **Scope:** user-requested five targeted design changes; no runtime implementation, no real MP4. **Review:** self-review through six professional roles, not independent human experts. DESIGN-SCOPE PASS requires latest Windows contract CI success.

## 1. Executive verdict
The previous status **Design PASS** was too broad for an end-to-end implementation handoff: StoryPackage lacked granular directions, compiled layers lacked physical layout/camera motion, map projection was underspecified, API missing edit/regenerate/export, original G-Labs contract absent, and plan was pilot-first. These gaps have been repaired **as design and machine-checkable contracts**, not as executable video engine. There is no technological need for a throwaway PoC app because Remotion supports programmatic video rendering; quality of the custom compiler/templates still requires full app execution and video acceptance.

## 2. Five requested repairs and evidence
| Request | Change | Evidence | Status |
|---|---|---|---|
| Complete three-stage pipeline | Extended StoryPackage.direction, VisualBlueprint.editorial_direction/slot bindings and CompiledTimeline layer geometry/masks/style/map/camera/motion/cues | Three JSON schemas + FULL_FLOW_VISUAL_COMPILER_CONTRACT.md; 24 sections/48 scene/360-second synthetic fixture | DESIGN COMPLETE, NOT RENDERED |
| Lock layouts/maps/motion | HistoricalMap.v1, TemplateLayout.v1, WGS84/date/CRS policy; 30 A/B/C registry layouts; 18 bounded motion presets | contracts/registries + HISTORICAL_MAP_ENGINE.md and semantic/negative tests | DESIGN COMPLETE |
| Missing real workflow API | Extended base OpenAPI by standalone OpenAPI 3.1 JSON extension of 25 non-colliding methods incl script edit, per-section voice regenerate/select/correction, archive search/batch, scene edit, render retry and approved export | contracts/openapi.yaml + contracts/openapi-fullflow-extension.json + API sanity tests; UI/API matrix | DESIGN COMPLETE |
| Original G-Labs + three sources | Verbatim user-supplied webhook document; independent Wikimedia Commons, LoC and Europeana request/mapping/paging/rights error contracts | contracts/providers/reference/WEBHOOK_INTEGRATION.vi(1).md (byte-for-byte compared with original 61,785 chars/1,148 lines), source adapter docs | DESIGN COMPLETE, LIVE UNTESTED |
| Replace pilot sequencing | Single full-flow app plan with two engineering phases, dependencies, native Windows acceptance, 10 templates, all G1–G5, provider branches and full 5–10min video | 05_IMPLEMENTATION_PLAN.md replaced; index and root README updated | DESIGN COMPLETE |

## 3. Six-role adversarial audit
### Director
**Prior blocker:** storyboard director picks a generic template but not a story-relevant visual moment. **Repair:** explicit visual purpose, viewer takeaway, on-screen script claim refs, ordered beats and camera/composition intent in imported JSON; same template can reveal evidence differently across chapters. **Residual implementation risk:** automatically generated creative quality and pacing must be judged on a completed 5–10min video, not inferred from schemas.

### Editor
**Prior blocker:** WPM-driven or estimated word timing, confusing what changes when section audio regenerated. **Repair:** final WAV sample offsets + ElevenLabs alignment word samples drive frame cues; event/camera local keyframes, immutable audio lineage, targeted render invalidation. **Residual:** actual English pronunciation, correction artifacts, voice section joins, timeline duration and export audio sync must be tested with real media.

### Motion Designer
**Prior blocker:** CompiledTimeline layers had only kind/asset/text, no rectangles, crop, z-index, mask, typography, camera or motion properties; renderer would hardcode guessing. **Repair:** every layer now has resolved pixel geometry and style/mask/map binding, each scene a camera track, each event bounded keyframes; 30 A/B/C layout records + 18 preset contracts. **Residual:** text metrics, fine typography and actual scene components still to implement; exact aesthetic match is not proven by design.

### Software Architect
**Prior blocker:** missing typed mutation APIs, multiple source-of-truth possibilities, passing raw ChatGPT output directly to renderer. **Repair:** three-stage ownership and precedence, typed 25-operation full-flow API extension, expected revision and idempotency, clean new codebase plan, separation of source and approved media, all gates. **Residual:** production server must merge two OpenAPI specs and implement safe filesystem/binary access, transactions, queue/restart behavior; schemas are not running code.

### QA
**Prior blocker:** green contract CI mistaken for historical accuracy, video quality or running provider proof. **Repair:** explicit synthetic longform fixtures with unverified claims, no real audio/assets, negative guards for stale refs, wrong map year, invalid camera/layout, fallback authorization, provider archive license uncertainty. Full-flow extension and registry coherence tests. **Residual:** mock provider responses cannot certify production endpoints or rights; must have Windows integration evidence.

### Solo Operator
**Prior blocker:** pilot-first path creates a disposable UI then full rewrite, and review options may auto-approve hidden fallback. **Repair:** two-phase same-production-app plan, G1–G5 always human, manual/managed choice + candidate approval separate, edit/regenerate/export APIs and production UI responsibilities. **Residual:** mockup only simulates flows; actual responsive keyboard and long-form project UX must be tested on Windows.

## 4. Contradiction register and disposition
- **Master Spec legacy M0–M4 and Step03 pilot references:** historical record, superseded by FULL-FLOW 05 plan and explicit precedence in DESIGN_FREEZE_INDEX/README. No pilot artifact required.
- **One external ChatGPT JSON vs local scene editing:** imported editorial direction provides defaults; local edits create VisualBlueprint revisions, never code generation or new ChatGPT round for crop/layout motion.
- **G2 approval vs alignment failure:** preserve selected audio approval; automated post-G2 alignment blocked/retry; G4 waits aligned final WAV, no sixth human gate.
- **Historical map provenance vs modern data:** separate HistoricalMap source/date geometry review and WGS84 projection; no default modern border substitution.
- **Managed fallback vs asset approval:** option authorizes candidates only; image remains unapproved until human G3 candidate and collective gate approval.
- **English-first vs sample's language:** primary runtime language English; Vietnamese ElevenLabs Forced Alignment support not V1 prerequisite.
- **G-Labs contract-first:** original webhook supplied; live account test not a blocker to coding, but real run cannot be marked PASS until observed.
- **Preview vs render:** both must eventually run same pinned HistoryComposition and same CompiledTimeline; UI HTML mock is only a UX reference.

## 5. Required implementation evidence; not design blockers
- Genuine 5–10 minute English voice audio with ElevenLabs final-WAV alignment and WordTimingMap lexical/timing QC.
- Exact G3-approved archival assets (Wikimedia/LOC/Europeana) with rights/evidence and one user-authorized G-Labs fallback path; user-led live provider test when available.
- All ten template components render all variants, text collision and historical maps/route corrections, actual Remotion Player/export parity frames.
- All UI edit/regenerate/batch/resolve/export operations wired to one FastAPI revisioned backend, Windows queue crash recovery.
- Full rendered MP4 H.264/AAC, video/audio QC, attributions, G1–G5 operator approvals and a different-topic long-form story to demonstrate no hardcoding.

## 6. Status boundary
**DESIGN CONTRACTS: PASS** after the latest Windows schema/registry/API checks pass. **FULL-FLOW IMPLEMENTATION: NOT STARTED.** **VIDEO QUALITY / LIVE PROVIDERS / HISTORICAL CLAIMS: NOT VERIFIED.**
No further PoC phase is recommended or required; proceed directly with 05_IMPLEMENTATION_PLAN.md as the only execution roadmap.
