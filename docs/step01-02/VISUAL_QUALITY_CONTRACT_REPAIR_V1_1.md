# VISUAL CONTRACT REPAIR V1.1 — BEAT, COMPOSITION, MOTION AND NEGATIVE TESTS
**Scope:** Full-flow Historical Video Studio design only, no pilot, no running video engine. The benchmark is reference 1015.mp4 (historical map/photo/document editorial motion graphics), assessed from existing sampled reference analysis. Exact cuts, easing and audio patterns were not established and are **not claimed matched**.

## 1. Why the prior design was insufficient
- 30 named layout variants represented only 3 cloned geometry families; required slot counts did not encode T03 photo collage, T04 route+map or T07 dual-map truth conditions.
- Generic StoryPackage visual intents named scene category/camera but did not encode object-to-object relationships and timed reveal narrative.
- CompiledTimeline held 2-layer/one-event synthetic examples; layer parenting, groups, typography, per-beat staging, camera focus paths and source-specific motion constraints were underspecified.
- Generic motion params could not describe ordered layer arrays for stagger/parallax, geographic route geometry, verified quote rules or synchronized period map wipes.

## 2. Stage 1 — StoryPackage (authoring, no pixels)
New required visual_beats for every visual setup. Each beat identifies beat_id, source narration section and phrase occurrence, semantic action (establish/reveal/trace/compare/annotate/reframe/consequence), explicit focus_ref pointing to a declared asset slot or on-screen text ID, source claim references, ordered staging steps (enter, hold, exit, move, draw path, reveal mask), spatial relationships (foreground/background, points-to, compares-to, follows, inside), focus move and hold policy. Continuity defines group_id, carried object references, entry and exit transition and reason. reuse_setup_id allows a prior setup as background, without requiring a new scene per spoken sentence.

ChatGPT is NOT asked to specify final frames, code, license grants, invented historical map polygons or accurate word timestamps. G1 controls narrative facts, actual approved assets arrive at G3 and exact time arrives from G2 ElevenLabs word map.

## 3. Stage 2 — VisualBlueprint: strict tagged payload per template
Each setup plan now requires template_payload with a JSON Schema oneOf discriminator matching template_id. No unknown field is accepted. Slot IDs, text IDs and source claims are semantically checked, not merely schema-shaped.
| ID | Required semantic content | Explicit negative |
|---|---|---|
| T01 | dated map requirement, focused historic feature, location labels/claim references | wrong map period |
| T02 | exactly identified portrait slot, subject name/role IDs, evidence claim and reviewable cutout fallback | lookalike as source |
| T03 | 1–3 photo cards, exactly one hero, crop/role/depth, unique ordered reveal list | duplicate or missing card reveal |
| T04 | approved route geometry ref, era map, >=2 ordered waypoints and beat cues, source claim, schematic disclosure | waypoints unmatched or guessed modern path |
| T05 | 2–6 source-dated timeline events, ordered chronology, beat/label links and active event | chronology reversed/duplicated |
| T06 | original document, excerpt page, verbatim verified or disclosed paraphrase, exact crop and annotation beat | fabricated quote/crop beyond image |
| T07 | two distinct period maps/dates, shared projection/viewport, before/after labels and mode | same date or mismatched era |
| T08 | source claim and exact displayed date/number, unit and safe count-up rule | visually different number from approved claim |
| T09 | original quote source or disclosed paraphrase, attribution, optional document and emphasis IDs | unverified source portrayed verbatim |
| T10 | >=2 named entities, directed evidence-backed causal links with certainty and framing scale | unsupported arrow marked documented |

This is how specialized templates become truly reusable without hardcoding each story inside JSX. A template's default may adjust layout, but never substitute the historical asset without G3 approval.

## 4. Stage 3 — CompiledTimeline: fully resolved art direction
Each scene now includes:
- composition_graph with group IDs and typed layer relationship edges, local beat_sequence with entry/exit focus and active/hidden layer sets, continuity group/carry;
- layers with position, crop/mask, text_layout, original-source-preserving treatment, group parent, depth, transform origin, optional geo/path geometry source;
- camera frame keyframes AND focus_path anchored to real layer (or verified historical map feature), with fixed transform order layer_then_group_then_camera;
- motion events with affected_layer_ids, typed preset parameters, transform space, optional stagger order and near/far depth, and contiguous enter/track/hold/exit phase recipe bound to actual audio words.

Render code must be deterministic per frame; text must have measured glyph bounds. Source photos are immutable. A clip/mask adjustment is a derivative or layout change, not evidence rewriting. Camera transform order and map coordinate projection are locked in the map engine contract. Beat sequencing must not alter the final voice WAV.

## 5. Template registries — no more cloned layout variants
contracts/registries/layouts.v1.json defines ten distinct layout families, each with A/B/C using actual different compositions and slot cardinalities, not just changing the role string:
- T01 geographic overview, alternate-side map narrative, map with inset.
- T02 portrait left, right and centered with lower third.
- T03 layered three-card collage, inverted hero/card evidence layout and equal-width contact strip.
- T04 map with route overlay, route plus independent archival evidence panel and route+waypoint rail.
- T05 horizontal chronology, vertical chronology and current milestone focus.
- T06 original scan with excerpt, document magnifier and quote-first source inset.
- T07 period before/after maps side by side, actual wipe and change-detail inset.
- T08 centered number, numeral/context split and date over sourced photo.
- T09 quote-first headline, quote plus source and clipping collage.
- T10 local-to-region map graph, non-geographical causal network and incident photo with consequence nodes.

Each layout binds required_role_counts, layer_relations, max_simultaneous_labels, source caption policy and overflow rule. Some intended spatial overlap is allowed (map + reviewed route, cards, two comparison maps in wipe variant). Unintended text/camera collision is still blocking at G4. Exact fonts/resize measured by renderer, not inferred from rough rectangles.

## 6. Motion registry — 18 preset-specific contracts
Each motion preset now includes strict parameter_schema, valid default_params, render_recipe primitive and transform_space, ordered phase_recipe, compatible layer kinds and geometry prerequisites. The shared scene schema allows bounded layer ID arrays but does NOT replace preset-specific validation.
- route-line-draw requires reviewed geometry and optional following marker.
- parallax-layers requires separated near/far IDs, relative drift strengths and reviewed separable source treatment.
- stagger-reveal requires explicit layer order/gap and semantic evidence order.
- map-region-wipe requires historical map ID, approved features and era-year.
- camera-pan and camera-push require actual focus layer IDs and bounded travel.
- text-highlight and typewriter require source word/quote linkage.
- count-up requires truthful intermediate values; no fabricated facts.
- photo-card-enter has border, source SHA, subtle shadow/rotation, not fake archival provenance.

User edits must go through typed timeline revisions and rerun layout/timing validation. G2 word map and G3 assets remain frozen until separately changed.

## 7. Adversarial fixtures and scope of confidence
contracts/examples/visual_cases includes ten synthetic examples T01–T10, each with multiple actual layer roles (3–5), three visual beats and two or more motion events, covering portrait, collage, route, timeline, document, territory pair, quote, facts, world causal graph. Companion validators execute:
- ID/cue/focus/relationship and cross-stage consistency;
- per-template payload invariant and source reference checks;
- actual template required role cardinality, phase order, typed motion params and transform space;
- G1 barrier on all synthetic critical claims.

Original longform synthetic 24-section/48-scene fixtures remain a **structural scale test**, not proof of multilayer visual quality; ten adversarial visual cases fill that separate need. All fixture assets, maps and WAV hashes are placeholders. No video, no checked source rights, no live TTS, no approval is claimed from fixture validation.

## 8. Implementation non-negotiables
Senior Full-stack Developer must generate/consume the same versioned types in Python and TypeScript, implement template payload decoders and per-preset evaluators, maintain one shared Remotion composition for Player and render, carry approved source hashes through all media transformations and return typed G4 diagnostics. Runtime must not invent fallbacks when a required slot/crop/path/claim is missing.

BA traceability from user outcome → authored visual goal/beat → approved source → normalized template payload → compiled scene/layer/event → UI/G4 review → MP4/G5 is mandatory. Every “automatic” claim refers to deterministic work BETWEEN five human gates, not unconditional acceptance or historical fact verification.

## 9. Verification limit
Schema/fixtures/Windows CI can prove the data model can REPRESENT the target visual primitives and reject defined bad inputs. They cannot guarantee attractive staging, no slideshow monotony in generated editorial choices, exact similarity to the competitor or accurate history. This still requires actual full-flow implementation, rendered frames, editorial self-review and user G4/G5 approval.
