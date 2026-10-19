# Full V1 Scene Template Design Sheets — T05–T10
**Supplement to:** 03_VISUAL_PRODUCTION_SPEC.md. Together they define all ten V1 scene templates; T01, T02, T03, T04 and T08 are documented in 03 and are the only five first full-flow template implementations.
**Status:** Design freeze, not implemented components. Default coordinates assume 1920×1080 and HistoryEditorialPaper.v1. All historical visuals must be G3-approved, all cues use frozen ElevenLabs WordTimingMap.

## Shared sheet format
- Template ID and immutable version; no runtime template code generation.
- Required/optional slots and valid asset classes; explicit rule for fake/AI evidence.
- A/B/C layout variants with 96px horizontal and 60px vertical critical safe areas.
- Default and alternate motion choreography; entrance/hold/exit timings constrained by final voice, no forced WPM guess.
- Operator editing controls and max text/element limits, test fixture, negative fixture and fail-closed outcomes.
- All examples below are conceptual production fixtures, not source licensing certificates.
- “Fallback” in a layout sheet means a **compatible layout treatment** of the same G3-approved asset; it never grants permission to replace a missing archive asset.

## T05 — CHRONOLOGY_TIMELINE · v1
**Narrative role:** explain chronological progression rather than spatial motion. Required: at least 2, at most 6 dated claims each linked to approved G1 claim ID, chronological label, short event text. Optional: one reviewed archive image/icon per event, period label. Asset classes accepted: none for pure dates, ARCHIVAL_PHOTO/HISTORICAL_ARTWORK/HISTORICAL_DOCUMENT if attributed; AI illustrations only with G3 approval and screen disclosure.

**Layouts:** A horizontal rail from left to right with 3–5 event anchors, body labels alternating above/below. B vertical date stack on left, event card right for long narrative. C one emphasized “current” date full-screen with 2 compact previous/next cards; suits narrow captions. A/B/C always keep current date visible and readable. Avoid more than 6 event cards; split setup instead.

**Choreography:** timeline-line-draw or subtle path reveal following claim order; each event appears 0.2–0.55s after its voice cue; hold text long enough for narration, keep already revealed events dimmed rather than repeatedly disappearing. Alternative: masked date-reveal then hard-cut between phases. Never animate later event before speaker introduces it if that implies the chronology is settled.

**Constraints:** date strings <=20 characters, card headline <=55, body <=110, 2-line preferred. No historical dates created from guessed year. Verify start/end dates stable with claim/source; “around 1871” remains approximate if evidence says approximate. Require G1 revision for a corrected year.

**Operator controls:** choose A/B/C, chronological direction, selected highlights, annotated source per event, cue offsets bounded <=0.4s from aligned word, color accents. **Tests:** timeline of 1866→1870→1871; Sarajevo → declaration sequence with supported dates. **Reject:** misordered/duplicate unsupported dates, text collision, one event missing G1 claim ref, >6 events without split, timeline continuing past end of audio.

## T06 — DOCUMENT_EVIDENCE · v1
**Narrative role:** foreground historical written evidence while preserving author/context. Required: approved HISTORICAL_DOCUMENT (or source-verified historical artwork depicting original document), page/location info, exact sourced excerpt or marked editorial paraphrase, citation label. Optional: magnifying crop, date, annotation leader. No generated “original documents”; synthetic reconstructions require different asset class + explicit label.

**Layouts:** A left 60% full page, right 40% source callout. B full-bleed document with enlarged crop inset in safe region. C hero excerpt in paper card with original page small but legible as reference. In A/B keep source year, attribution legible; when text source low-res, prefer contextual card over false OCR reconstruction.

**Choreography:** photo-card-enter then camera push on approved source rectangle, followed by annotation draw and transcript reveal at aligned claim. Alternate uses spotlight mask pan then hold. Original document pixels remain unchanged (crop/brightness only non-destructive). Do not make document appear to say words not present in it. Letter-by-letter typewriter is only allowed for exact verified excerpt.

**Constraints:** preserve visible citation on any factual excerpt; quoted text matching verified transcript; overlay max 2 callouts and 1 active crop box; minimum readable source excerpt not guaranteed by OCR. Layout collision and OCR uncertainty can hard BLOCK with documented repair.

**Operator controls:** exact crop rectangle, page reference, quote text source, typography variant, annotation placement. **Tests:** dated 1914 newspaper front page from approved source; government statement excerpt from approved scan. **Reject:** fabricated quote, low-res OCR silently accepted, cropped sentence that changes meaning, removed source attribution, unknown rights.

## T07 — TERRITORY_COMPARISON · v1
**Narrative role:** explain territorial changes across two historically meaningful dates. Required: period-specific G3-approved start and end geography with valid year windows, common region ID, compatible coordinate/projection model or explicit reprojected geometry version, date labels and source notes. Optional: highlight differences, explanatory callout. Modern country shapes never substitute for 1871/1914 by assumption.

**Layouts:** A split-screen before/after with synchronized labels. B controlled mask-wipe comparing same frame/projection, dates pinned upper corners. C full map with two inset mini-maps and a legend of documented change. When geometry is not directly comparable, choose split explanatory diagrams with explicit scale/projection note; **do not** run deceptive wipe.

**Choreography:** map establish 0.6–1.0s → source date A hold → map-region-wipe 0.4–0.8s → date B and delta label hold. Alternative static split with sequential label emphasis. Camera zoom centers on same world region, does not shift territorial outline to create artificial gain/loss.

**Constraints:** no polygon interpolation for undocumented intermediate borders, no automatic “gain” label from area difference without approved claim, legends legible. Two map source hashes/periods pinned to revision; if one changes invalidate G3 related binding and G4 map scene.

**Operator controls:** date pair, region, layer opacity, side-by-side vs wipe, label/legend positions. **Tests:** German states pre/post 1871 with approved map provenance; border comparison with explicitly matched projection. **Reject:** wrong era, switched projection, unverified modern border as historic, missing one date label.

## T09 — QUOTE_HEADLINE · v1
**Narrative role:** deliver quote, short title or interpretive claim without falsely attributing speech. Required: headline/caption text from approved story; for direct quotation, verified source speaker/document and quotation match G1 record. Optional: photo card and date. Quotes and paraphrases must be distinguishable in data and typography.

**Layouts:** A large typographic page with 1 emphasis word, citation footer; B left quote/right archival source preview; C newspaper-type clipping headline with text block and timestamp. Typography wraps by word at measured font metrics, limited to 2–3 lines by variant. If too long, split into two setups or trim with G1 approval, never shrink below caption minimum.

**Choreography:** title-mask-reveal (0.35–0.75s), optionally word-by-word highlight on ElevenLabs word IDs, hold for legibility. Alternate typewriter for short fully supported excerpts (not long paragraphs). Avoid pop or excessive kinetic type for tragedies. Existing source card has quieter motion than actual spoken headline.

**Constraints:** max 120 characters for hero quote by default, <=2 highlights, exact punctuation from approved text, speaker/date source attribution. A label “paraphrase” must be displayed when original quote not verified. Do not duplicate quotation marks in unverified editorial summaries.

**Operator controls:** headline text source pointer, emphasize phrase/word_id, citation placement, line breaks only inside safe reading region, animation variant. **Tests:** properly sourced public statement + source card; an editorial summary visibly marked “In effect”. **Reject:** invented direct quote, cue references nonexistent word, overflow, unsourced attribution.

## T10 — GLOBAL_CONSEQUENCE · v1
**Narrative role:** change scale from local incident to regional/international consequences without overstating causation. Required: G1-approved causal claim(s), at least two named region/political entities with dates, verified map or conceptually accurate approved network diagram. Optional: archive cards and timeline anchors. For non-geographic causal chains prefer cards/graph, not pseudo-geographic arrows.

**Layouts:** A full region/world map, local focus then progressive zoom-out with callouts. B regional network diagram with 3–5 linked entities and evidence captions. C top/bottom: archival card of initial event and regional/global map lower pane. Map variant only if source period/dates and geographic relations are validated.

**Choreography:** initial evidence anchor → camera-pan/push-out (2D simulated) → staggered regional labels and controlled annotation connectors. Alternate cross-dissolve into wider political map while retaining original location marker. Each new relationship appears when corresponding G1 claim is spoken, not at random.

**Constraints:** max 5 simultaneous labels, 3 causal arrows unless deliberately edited, badge “context/overview” where not exact geospatial change, no speculative territory/historic alliance visuals. Zoom-out must preserve readability and not exceed safe camera travel. Factually debatable claims must be represented as attribution or described uncertainty.

**Operator controls:** initial/final region, annotation links, source/claim binding, map era and accepted geography, headline, transition. **Tests:** Sarajevo to European alliance overview with reviewed sources; German unification to later European balance-of-power context (careful causal wording). **Reject:** invented international alliances, unsourced causality line, wrong-period map, unreadable five-region collage.

## Template Registry Acceptance Matrix
| ID | Mandatory slots validated | Three variants | Timed motion choices | Historical review negative |
|---|---|---|---|---|
| T01 | approved era map, region marker | A/B/C | pan/push/region reveal | modern map labeled old |
| T02 | identified portrait, exact name | A/B/C | cutout or photo card/stagger | lookalike as archival |
| T03 | 1–3 archived photos/metadata | A/B/C | stagger/held focus | related photo mislabeled exact event |
| T04 | approved route/path and chronology | A/B/C | route draw, marker follow | invented route |
| T05 | 2–6 source-dated events | A/B/C | chronological reveal | wrong dates/order |
| T06 | approved document, exact excerpt source | A/B/C | crop focus + annotation | fabricated quote |
| T07 | 2 comparable period maps | A/B/C | map wipe/split | projection / era mismatch |
| T08 | exact number/date/claim | A/B/C | mask/count/freeze | wrong year/number |
| T09 | quote or marked paraphrase | A/B/C | mask/text highlight | invented attribution |
| T10 | approved regions and causal claims | A/B/C | focus-out/network labels | unsupported causal arrow |

## Freeze rule
Runtime implementation of each template must supply visual fixtures (first/mid/hold/boundary frames), editable inspector parameters, deterministic state, accessibility contrast and preview/export parity test. If any output uses a replacement historical asset, it must be an **already-approved G3 binding**, not a creative code fallback. The 10 template descriptions and their schema IDs are stable for V1, but exact motion values remain provisional pending full V1.
