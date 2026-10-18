# 03 — VISUAL PRODUCTION & TEMPLATE SPECIFICATION · V1.0
**Scope:** Step 02; defines reusable Remotion visual grammar, not a claim of rendered implementation. **Authority:** original MASTER_DESIGN_SPECIFICATION_V1 §§11–17 and six-role audit. This edition resolves the first 10 templates' technical/design slots and narrows the Step 03 pilot to T01/T02/T03/T04/T08.

## 1. What the reference video supports
Reference **1015.mp4**, sampled/inspected as the basis for design: 298.284 s, 1920×1080/30fps, story about Sarajevo/Franz Ferdinand and cascading European events. Representative passage types:
- 00:00–00:10: territorial map, labels, emphasis on location.
- 00:10–00:45: portrait/collage + informative typography.
- 00:45–01:10: archival context/organization/photo cards.
- 01:35–02:10: date/text/document montage.
- 02:25–02:50: route explanation / turning-point schematic.
- 03:35–04:15: zoom from local event to regional/world consequences.
- 04:15–04:58: archival/referential end montage.
Observation caveat: sparse sampling does **not** measure exact easing curves, cuts, source accuracy, user rights, or quality of actual audio narration. Video aesthetic is an editorial **reference**, not template-for-template duplication.

## 2. HistoryEditorialPaper.v1 style tokens
Design defaults for prototype; must be adjusted in visual review and frozen by style version.
- Canvas 1920×1080, 30fps 16:9, safe outer 96 px horizontal / 60 px vertical for vital labels. Title region min 14% margin from edge when overlays are present.
- Paper light background #ECE8DB / ink #202020 / dark map #252A2E / warm gold #D7B652 / territory red #A3443D / restrained slate #6D8A91. These are proposed palette tokens, not measurements of input video.
- Fonts: licensed, embedded sans heavy for headline; legible body/caption face and restrained mono-like date label. Font family chosen and bundled in implementation; browser and render hashes must match. Never render with silently substituted font.
- Image treatment: archive-original is immutable. Derivatives are photo-card (off-white border+shadow), grayscale/contrast (non-destructive), cutout (mask+outline), contextual crop or layered parallax if separation QC passes; source type and rights remain bound.
- Typography hierarchy: primary headline 72–122 px; section labels 40–64; captions 28–42; citations 23–30 at 1080p (all provisional). Use measured text width, max line count and readable dwell before deciding font scale. English-first. Never make type tiny to fit.
- Texture under text low contrast; do not cover primary factual content. Historical photo may be framed like paper but never cosmetically retouched to change evidence.
- Sound cues and scene cuts derive from content and voice, not random effects. Quiet hold is allowed; avoid continuous pan for every photo.

## 3. Shot grammar and automated selection
Voice/semantic intent decides the visual *form*, not the animation for its own sake.
| Semantic cue | Preferred template | Alternative if asset constraint |
|---|---|---|
| geography/territory/border | T01 map focus / T07 comparison | T06 verified document (requires explicit G3 decision if map requirement unresolved) |
| person/role | T02 portrait explainer | T03 photo card with verified identity |
| historic primary evidence | T03 archival collage / T06 document | T09 quote/headline with truthful attribution |
| route/movement/turning point | T04 route reconstruction | T05 timeline if route geometry cannot be supported, with G3 operator decision |
| sequence of time | T05 timeline | T11 future causal chain |
| numeric fact/date | T08 fact impact | T09 headline |
| world consequences | T10 global consequence | T05 sequence, subject to evidence |
A template variant may change **presentation**, never change the historical claim. If a REQUIRED ARCHIVAL requirement has no approved binding, compilation BLOCKS; choosing a different type of *asset* requires G3 decision. Unverified history cannot be “fixed” by better motion.

## 4. Generic scene model
Scene is a persistent **setup**, not necessarily a sentence/shot. Core fields: setup_id, template_id+version, variant_id, source section/claim IDs, estimated semantic intent, approved asset bindings, layer slots, timing anchors referencing WordTimingMap, motion event assignments, safe frame/scene duration, map provenance, captions, attribution linkage, editorial diagnostics.

Layer kinds allowlisted: map, territory, route, portrait, archival_photo, document, text, date, headline, callout, annotation, stamp, decorative_paper, camera, evidence_marker. All layers are declarative and carry asset/text references. No SVG/HTML/React code from JSON. Transform keys bounded: scale, translate, opacity, rotation, mask extent, path draw progress, focus rectangle. Template provides responsive layout variants and collision tests.

## 5. Timing and storytelling rules
- Voice-aligned start/end of word or section establish cue anchor; never derive final timing from WPM after WAV exists.
- A layer enters, holds for reading and exits only when needed; if scene is long, extend **hold**, not entrance animation. Tentative entry 0.25–0.85 s, transition 0.15–0.65 s. Tune from real player.
- Hierarchy: identify location/subject → reveal factual label → explain movement/cause → show consequence. No simultaneous appearance of all labels unless the concept calls for it.
- Minimum visible dwell based on words and reading rate is diagnostic, not blanket clip padding. If duration inadequate: choose compact variant, reduce text, spread cue across continuous setup or G4 request edit.
- Camera must preserve focus/legibility, match map-world coordinates for map annotations; zoom crop cannot cut out evidence context.
- Editorial variety warnings: detect 3 consecutive setups with same template/entrance; prefer other *semantically valid* variants, not historically false imagery.
- Sequential scene boundary continuity: no snap/jump unless intentional hard-cut event; audio must remain continuous and G5 render duration match final WAV within muxing tolerance.

## 6. Scene template design sheets — common contract
Every template implements registry entry: id/version, slots with allowed asset_classes/text evidence type, min/max duration, layouts with normalized coordinates and safe margins, motion sets (default and alternative), entry/hold/exit timing policy, editable parameters, collision detection, accessible/reduced-motion alternative, editor controls, two fixture cases and a negative test. The layout uses canonical 1920×1080 coordinates but may scale from normalized percentages. Values are **design defaults**.

### T01 MAP_TERRITORY_FOCUS · Step 03 pilot
Purpose: establish where and which territory. Slots: required approved historical/map source and period/region identity, optional territory mask, <=5 geographic labels, one headline/citation; only verified geometry for border overlays.
Variants: A full-bleed map with anchored title at top-left; B map two-thirds + right claim card; C zoomed detail panel inset on broader map.
Motion: camera-pan/2D-push and map-region-wipe with pinned geographic points; region highlight 0.4–0.9s after map establishes. Hold 1.5s minimum for place names, longer by speech.
Operator: choose valid date/map, highlight palette, focal region, zoom endpoints and label offsets; all map coordinates derive from approved data. Reject date mismatch, unknown map source, label crosses safe area, region highlights modern border as past.
Fixtures: (1) Austria-Hungary/Bosnia period map; (2) Germany 1871 map; negative: 2026 border polygon used for 1914 without explicit schematic interpretation.

### T02 PORTRAIT_EXPLAINER · Step 03 pilot
Purpose: identify and contextualize a person. Slots: exact identified portrait asset, name/role, optional date and verified fact; portrait cutout is optional treatment, not historical substitution.
Variants: A left portrait/right title; B centered portrait with side note; C framed archival-card when segmentation edges fail.
Motion: subtle portrait enter (photo-card-enter or small pop) + staggered title, optional camera-push with scale limits; reveal name on first mention, hold to read. Foreground is anchored; no arbitrary bounce for death/war tragedy.
Operator: crop/mask mode, name width, fact strip and motion strength. Reject wrong-person asset, damaged cutout head, mislabeled portrait and overlapping text.
Fixtures: Franz Ferdinand; Bismarck. Negative: model generated lookalike labeled archival portrait.

### T03 ARCHIVAL_PHOTO_COLLAGE · Step 03 pilot
Purpose: show a collection of sourced context/evidence. Slots: 1–3 reviewed archive assets, each with date/source attribution, optional one callout, no unsupported factual caption.
Variants: A overlapping 3-card paper; B one hero photo and two supporting details; C sequential full-card focus and mini thumbnail tray.
Motion: stagger-reveal, photo-card-enter, subtle Ken Burns on selected card; do not animate all frames continuously. Factual caption appears only while associated photo is unambiguously dominant. Hold individual material long enough to read context.
Operator: choose card order/crop/rotation within conservative bound, source caption and highlight. Reject photo selection that implies wrong location/time or occludes the only relevant evidence.
Fixtures: Sarajevo context collage; Prussian archival collection. Negative: related period city photo mislabeled exact assassination photograph.

### T04 ROUTE_RECONSTRUCTION · Step 03 pilot
Purpose: explain cause/effect movement. Slots: reviewed path geometry/map or expressly schematic path, start/end/event markers, optional vehicle icon, step labels and dates.
Variants: A full route draw; B event waypoint stepper; C side-by-side route and evidence photo strip.
Motion: SVG line draw, marker follow at reviewed temporal cues, optional camera-pan that respects map frame; keep paths and labels grounded. Step pacing by aligned narration, no uncontrolled overshoot at coordinates.
Operator: inspect geometry, order waypoints, point labels, choose schematic badge, focus camera. Reject guessed path, impossible waypoint order, vehicle outside route, modern streets passed off as 1914 facts.
Fixtures: Sarajevo route reconstruction from sourced path; Bismarck-era railway itinerary where documented. Negative: route asset missing but automatically generated by AI.

### T08 FACT_NUMBER_IMPACT · Step 03 pilot
Purpose: punctuate exact date, figure or number. Slots: exact user-approved fact value, optional source/date, context one sentence; style neutral for grave content.
Variants: A large centered date; B left large numeral/right context; C paper stamp overlay on current map/photo.
Motion: title-mask-reveal or restrained pop-in; number-count only if interim values do not falsely claim measurements; freeze-hold over spoken numeral/claim. Treat final numerals as data, not generated image text.
Operator: format and source citation, cue word, scale and placement. Reject changed magnitude, truncated number, count-up semantics on categorical values.
Fixtures: 1914 date and 1871 proclamation year. Negative: visually displayed “1870” while spoken claim is “1871”.

### T05 CHRONOLOGY_TIMELINE · Full V1
Purpose: sequence 2–6 distinct dated events. Required dated claim IDs and order; optional icons, one archival thumbnail per event. Variants: horizontal time rail, vertical stack, page-turn sequence. Motion: event-pin reveal, connector line draw, camera pan on overflow. Set event cue to aligned sentence; allow extended holds. Editor: reorder only if corrected source chronology. Negative: date misorder.

### T06 DOCUMENT_EVIDENCE · Full V1
Purpose: read a period document without manufacturing text. Required document original + review-approved transcript/quote excerpt + source label. Variants: full paper + magnification inset; split page+headline; highlight focus card. Motion: crop-focus, annotation underline, typewriter only for verbatim excerpt. Editor: select exact text rectangle and preserve context. Negative: quotation synthesized from OCR uncertainty shown as verbatim.

### T07 TERRITORY_COMPARISON · Full V1
Purpose: compare two dates. Requires two approved compatible map states, date labels and geographic consistency; may include separate projection note. Variants: split map, timed before/after wipe, synchronized double panes. Motion: map-region-wipe, fade/hold, anchored camera. Editor: date pair and labels. Negative: mixing incompatible projected polygons and calling it a territorial gain.

### T09 QUOTE_HEADLINE · Full V1
Purpose: explain evidence or quote. Requires approved quotation/source or editorial paraphrase marked as such. Variants: left-heavy typography, newspaper clipping, two-level headline/date. Motion: title mask, typewriter and text highlight. Editor: quote provenance and typography. Negative: invented quote marks around a paraphrase.

### T10 GLOBAL_CONSEQUENCE · Full V1
Purpose: move scale from local to regional/global outcomes. Requires approved map/relationships and label/claim IDs. Variants: map zoom-out with linked labels, network of regional cards, headline + map evidence; motion: restrained map pan/push, staggered labels, annotation line-draw. Editor: causal links and geographic regions. Negative: unsupported arrows asserting direct causation without evidence.

T11 EVENT_CAUSAL_CHAIN and T12 SOURCE_COMPARISON are **future optional**; not required for V1 acceptance and must not grow the Step 03 pilot scope.

## 7. Motion preset registry v1
The following references are catalog **names/IDs** from showheyohtaki/motion-prompt; not native Remotion components:
| In-house ID | Source concept | Targets / constraints |
|---|---|---|
| pop-in | #001 Pop-in | badge/portrait, subtle overshoot |
| stagger-reveal | #002 Stagger | <=5 labels/cards, speaking order |
| route-line-draw | #004 Line draw | approved SVG route paths |
| title-mask-reveal | #005 Mask reveal | short headline |
| typewriter | #006 Typewriter | verified quotes only |
| number-count | #007 Count-up | verified final value |
| kinetic-type | #008 Kinetic typography | word-cue aligned and measured |
| parallax-layers | #016 Parallax | separable approved foreground/background |
| mask-transition | #017 Mask transition | bounded scene wipe |
| camera-pan | #025 Pan | flat 2D transform constrained to subject |
| camera-push | #027 Dolly in concept | simulated zoom, not literal dolly |
| freeze-hold | #040 Freeze frame | measured hold |
| whip-pan | #043 Whip pan | exceptional accent, avoid repetitive blur |
| cross-dissolve | #044 Cross dissolve | sober archival cut |
| hard-cut | #046 Smash cut | deliberate editorial punctuation |
| text-highlight | in-house | word cue emphasis |
| map-region-wipe | in-house | period-validated territorial overlay |
| photo-card-enter | in-house | paper-framed archival image |
No runtime dynamic JS. Params bounded by JSON Schema/in-code checks: duration positive <= scene; scale default 1–1.12 for documentary pan; translation to safe crop, opacity 0–1, rotation usually <=4 degrees. Each preset has registry semantic version, supported layer kinds, motion graph, entry/hold/exit controls, reduced-motion alternative and source notice where third-party code/numbers carried over. Remotion spring/interpolate/masks/paths used to implement, with same component for Player and Node render. Porting Motion Prompt requires preserving MIT attribution in copied code.

## 8. Automatic compiler rules
1. Validate canonical Story revision, finalized English audio, ElevenLabs word map, G3 approved bindings, style/template registry version.
2. Resolve semantic intent → one allowlisted scene template (and one bounded variant), maintain persistent setups across adjacent narration if subject/map remain.
3. Resolve layer assets; if required historical asset unresolved, block and open G3 (never silent fallback).
4. Assign word-cue times → integer frames using single documented conversion (floor for start, ceil for end, then clamp); enforce positive frame duration and stable cue ordering. No invented word IDs.
5. Allocate content layout with embedded font metrics; test safe area, no overlap and acceptable text dwell. Try bounded alternative variant or produce G4 diagnostic, not microscopic text.
6. Schedule entry, hold, exit and transition without altering final WAV; cap camera movement and checked documentary reading hold. All mutation resides in a draft timeline revision.
7. Attach selected source/rights and on-screen labels for AI_ILLUSTRATION / MODERN_RECONSTRUCTION and render credit manifest.
8. Canonicalize JSON sort and derive SHA256 fingerprint from approved story/audio/alignment/assets/style/fonts/template versions. Recompilation of same inputs produces identical timeline bytes.

## 9. Temporal and visual QA fixtures
Positive fixture per pilot template: at least one Sarajevo + one Germany example; all reuse same code and template slot schema. Negative fixture per template as described in §6. Test frames at entrance, mid-motion, long hold, scene boundary; test widescreen 1920x1080 and smaller Player viewport; test longer names, missing asset, nonempty source caption, masks, source text clipping and contrast. Compare Player still and exported still from same frame with finite tolerance (fonts/media decoded consistently).

QC failure codes:
- VISUAL_TEXT_OVERFLOW, VISUAL_SAFE_AREA, VISUAL_SHORT_DWELL, VISUAL_COLLISION
- MAP_PERIOD_MISMATCH, MAP_SOURCE_REQUIRED, ROUTE_UNVERIFIED
- ASSET_UNAPPROVED, ASSET_PROVENANCE_UNKNOWN, FALLBACK_NOT_APPROVED
- CUE_NOT_FOUND, TIMING_NON_MONOTONIC, EMPTY_SCENE, UNKNOWN_TEMPLATE_OR_PRESET
Warnings are different from blocking errors: repeated template, subtle camera monotony or heavy visual complexity are editorial warnings for G4 operator.

## 10. Visual acceptance Step 02 design
Each T01–T10 has purpose, slots, variants, motion, timing rules, editor controls and negative case. Five pilot templates fully enumerated and frozen to Step 03 scope. A change to template grammar after freeze increments registry version and invalidates affected CompiledTimelines. Design PASS is possible before video proof; “looks like sample” requires Step 03 filmed evidence and multi-role visual review.
