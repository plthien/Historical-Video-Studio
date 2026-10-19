# Full-Flow Video Data Pipeline — Frozen V1
**Authority:** Step 01+02 targeted repair. Supersedes legacy Step 03 pilot wording. New repo, no old runtime/migration. Remotion renderer is deterministic, not a decision-making agent.

## 1. Three-stage data ownership
**StoryPackage.v1 (external ChatGPT JSON):** sections/claims/source leads/required assets and detailed editorial direction. Per setup, include purpose, takeaway, on-screen text with source claim IDs, ordered reveal beats anchored by narration phrase and occurrence, asset slots, camera/composition/transition intention. No code or invented word times.
**VisualBlueprint.v1 (normalized draft):** after G1, normalize semantic intent into exact template/variant, reviewed editorial direction, required slot bindings, safe-area/text-density/focus controls. Null asset binding until G3. User edit creates new revision, not mutation of frozen approval.
**CompiledTimeline.v1 (compiler-produced):** after G2 approved final WAV + ElevenLabs word map and G3 asset approvals, resolve each shot into exact integer start_frame/duration_frames, per-layer rect_px/crop/mask/style/z-index/asset/map binding, camera keyframes, animation event local keyframes, word cues, transitions and dependency SHA. Remotion only consumes this JSON + local immutable media/fonts + fixed registered template code.

## 2. Deterministic compile sequence
1. Strictly validate StoryPackage plus semantic section→claim→asset requirement→setup refs. G1 user approves actual source/claim and script revision; unknown assertion blocks.
2. Normalize setup order into VisualBlueprint. Precedence: explicit approved user edit > supported template variant > documented layout defaults. Never execute imported JS/CSS/SVG.
3. G2 section approval triggers exact sample-based WAV assembly and ElevenLabs forced alignment (both Kokoro and ElevenLabs TTS). Every phrase+occurrence maps to an exact WordTimingMap word/span; ambiguous/missing cue hard-blocked (CUE_MISSING/CUE_AMBIGUOUS).
4. G3 exact approved asset snapshot binds all required slots. Missing archive opens two-option operator review; managed fallback candidate generation is **not** approval.
5. Resolve narration cues to frames using integer arithmetic: start=floor(sample*30/sample_rate), end=ceil(sample*30/sample_rate); positive half-open [start,end) scene intervals. Motion event keys in event-local frames, camera keys in scene-local frames. No WPM derived final cues.
6. Select version-pinned TemplateLayout A/B/C; convert normalized rect to 1920x1080 rect_px; place approved layer crops/fit/anchor/style/mask and optionally map geo feature positions. Measure real fonts, collision/text-safe areas; try same-asset layout variant else G4 blocker, never swap source automatically.
7. Expand bounded MotionPreset registry into explicit keyframes; frame-deterministic camera track. Layer transform → camera transform → final viewport. No provider/network calls at frame render time.
8. Canonicalize timeline JSON, hash Story/Audio/WordMap/G3Snapshot/LayoutRegistry/MotionRegistry/Fonts/Renderer version; compare same-input compilation bytes; Remotion Player and final renderer load identical Composition and inputs.

## 3. Map and temporal rules
HistoricalMap.v1 binds source image SHA, period coverage, reviewed feature IDs and date, source CRS and normalized EPSG:4326 lon/lat, chosen map projection, bbox, local geometry bytes and rights approval. Vector GPKG reprojected to GeoJSON before renderer; period raster needs reviewed UV control points or no geospatial placement claim. Route is approved ordered geometry or explicit labeled schematic, never inferred modern driving route. T07 compares dates only in same projection and frame. Block mismatched 1914 vs modern boundaries.
Scene duration derives from final approved WAV samples, not text WPM; output total frames computed once. Transitions within scene bounds, no duplicate overlap. Repeated words disambiguated with explicit occurrence/word_id.

## 4. Versioned machine-readables
Contracts/schema/StoryPackage.v1, VisualBlueprint.v1 and CompiledTimeline.v1 are authority; HistoricalMap.v1 and TemplateLayout.v1 define map/layout boundaries. Registry files in contracts/registries hold all ten templates and supported motion presets. Template slots enforce asset class and reviewed G3 evidence.
Longform fixture is synthetic: 24 narration sections, 48 setups/scenes, 360 seconds/10,800 frames. It is a stress data fixture, not an authentic aligned audio, historical evidence or MP4.

## 5. Mandatory blocking examples
Unknown cue, duplicated section/setup, wrong-era map, unapproved fallback/rights, scene-camera overshoot, unknown template/preset, source-dependent statement mismatched to image, text overflow, overlap, missing on-screen disclosure for AI illustration, editing while stale revision. Expose the setup/layer/word/requirement that failed and concrete repair path.

## 6. No isolated pilot phase
Implementation plan is full application; incremental integration tests within same app do not create temporary prototype architecture or postpone core asset/G-Labs branch to a later product.

## 7. P0 Visual quality repair authority v1.1
The ten VisualBlueprint template_payload variants must be decoded by exact template ID and cannot silently downgrade to an unrelated scene. The external ChatGPT package now requires visual_beats with relationship/reveal/focus continuity; each compiled scene now pins a composition graph, staging beat windows, per-layer source_asset_slot_id/template_slot_id, text metrics, source treatment, camera focus path and preset-specific phase recipe. 30 layout variants are truly template-specific, NOT cloned generic positions. Motion registry has 19 typed presets; **route-line-draw is geographic with evidence-bound geometry**, while **editorial-connector-draw uses annotation canvas paths for chronology/causal graphs**. UI G4 may change staging/layout with recorded direction_revision/operator permission, but cannot silently change G1 claims or selected G3 source identity. Full details: VISUAL_QUALITY_CONTRACT_REPAIR_V1_1.md.
