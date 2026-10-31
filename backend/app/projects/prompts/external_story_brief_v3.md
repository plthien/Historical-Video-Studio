# EXTERNAL CHATGPT — HISTORICAL VIDEO STUDIO STORY AUTHORING V3

Brief version: HVS-EXTERNAL-STORY-BRIEF.v3

## 1. Operator inputs — binding values, not output fields

The following metadata is the operator's exact input. Use it to make editorial decisions. Copy its `project_id`, `language`, and `style_id` into their corresponding canonical `StoryPackage.v1.project` fields. Set `project.title` to the supplied topic unless a shorter accurate title better preserves its meaning. Other metadata such as `audience`, `runtime_minutes`, `output`, `editorial_goals`, and `brief_version` is NOT an additional StoryPackage JSON property; do not inject it into the output object.

~~~json
@@HVS_OPERATOR_METADATA_JSON@@
~~~

Honor the supplied topic, period, audience, runtime and editorial goals. Do not substitute a different topic, style or production profile. Write all narration and editorial text in natural spoken English. Output only one complete canonical `StoryPackage.v1` JSON object, not a screenplay, prose review, outline, prompt or executable rendering code.

The Historical Video Studio app does NOT call an LLM or browse. Any research or writing you perform occurs in this external chat and remains UNVERIFIED until the operator reviews it at G1. G2 owns recorded and aligned audio, G3 owns assets/rights and sourced maps, and G4 owns typed template payloads, geometry and rendering. Never claim those later approvals have happened.

## 2. Mandatory internal work order — one final artifact

Before emitting JSON, carry out these internal passes in order. Do not output the intermediate notes, and do not omit any pass:

**Pass A — evidence and feasibility.** Identify the central historical question, the material evidence leads, the important uncertainties, and which kinds of visual materials could actually exist for the named period. Distinguish contemporary sources, later depictions, modern reconstructions and schematic graphics. If the external chat has access to browsing, inspect trustworthy relevant sources and use only URLs actually checked. If browsing is unavailable, do not pretend to have browsed or fabricate a citation. An empty `source_leads` list is allowed and means operator research is needed; preserve `critical=true` for pivotal unresolved claims.

**Pass B — complete spoken story.** Write and internally freeze the entire section-by-section narration before creating cues or visual setups. Construct a discovery-driven arc, not an encyclopedia list or chronology-only lecture. Keep uncertainty in the narration itself, not just in metadata. The spoken script is the source of truth for all downstream cue phrases; after cue authoring, do not casually reword narration and leave stale cues.

**Pass C — production direction.** Turn each consequential change in viewer understanding into a filmable visual setup with appropriate registered T01–T10 capability. Only then assign asset requirements, on-screen text, visual beats, reveal intentions, section refs, claim refs and cue locations. Prefer visuals achievable without pretending a camera, portrait, period map or photograph existed when it did not.

**Pass D — validation and output.** Validate JSON syntax, all required schema fields, reference identity, chronological cue order, source honesty and whole-film coverage. If anything changes in narration or setup order, repair all affected cues and references before output. Emit the ENTIRE JSON exactly once. Do not output a truncated or partial object. If the external environment can produce a complete UTF-8 `.json` file without changing its contents, that is acceptable; the app still imports only one canonical StoryPackage object.

Do not produce a research memo, section headings, implementation notes, media asset binaries or multiple separately importable objects. Intermediate passes are internal planning discipline, not additional app states or output contracts.

## 3. Historical evidence and credibility — non-negotiable

A statement is not reliable simply because it is commonly repeated or visually appealing. For every material event, date, person, place, chronology, quantitative estimate or asserted cause, create a traceable entry in `claims[]` and link it from the relevant sections/setups. Source leads are research leads, NOT human verification, permission to reuse an image, or proof of an exact historical map. Set every model-authored claim `status` to `UNVERIFIED`; never self-assign `REVIEWED` or `VERIFIED`.

Mark `critical=true` when an unverified claim materially affects the core thesis, hook, major date, quantitative conclusion, or visualized route/cause. Phrase unresolved claims cautiously and avoid putting weak, isolated speculation into the film. If research is genuinely unavailable, favor fewer well-bounded claims over invented source lists. Do not fabricate links, precise historical border coordinates, dates, outbreak data, mortality statistics, quotes or copyright permissions.

Keep documented fact, inference and representative reconstruction visibly and verbally distinguishable. On-screen depictions from a later era MUST NOT be represented as contemporary eyewitness material. Assess period-specific media feasibility before selecting templates: for events before photography, do not request contemporary photographs of the event; use a surviving appropriate document/artwork/object if supportable, or mark a permitted reconstruction as reconstruction. A portrait/image may be a later depiction, not a verified likeness. For a topic set in 1347–1353, do not claim a photograph was taken in that period.

For estimates, use context, units, affected population, date range and denominator where relevant; note disagreement and uncertainty. For attributed speech, use only a genuinely supportable source-attributable verbatim quote; otherwise clearly paraphrase. Do NOT instruct G4 to use `verbatim_verified` unless a subsequent authorized G1 correction genuinely records `VERIFIED` in the frozen source claim. Do NOT assert a `documented` causal link with an UNVERIFIED source claim. Prefer a qualified on-screen inference that does not falsely upgrade the source's status.

Maps represent evidence-bounded periods and geography. A map template does not grant historical truth. Do not turn a plausible propagation sequence into a documented route, or convert a modern political map into medieval borders. If exact route or dual-period geometry cannot be supported, use an honest non-route graphic, a qualified illustration, or another available template instead. Historical `HISTORICAL_MAP` requirements must have `start_year <= end_year`, meaningful `exactness`, suitable `map_reconstruction_policy`, and consistent requirement references; G3 and G4 still perform original-source review and geometry ingest.

## 4. Spoken storytelling quality — write for retention, not a lecture

The opening 15–25 spoken seconds must create a **specific, evidence-compatible tension**: a danger, unresolved contradiction, surprising implication, or consequential question. Do not begin with a generic encyclopedia definition, ceremonial welcome, or long list of background dates. The hook must lead into the investigation without making a historically unsupported claim.

The narrative is an evolving chain: a familiar assumption or urgent question → one concrete piece of evidence → what that evidence changes → a human-scale consequence → a more interesting unresolved question. Repeat with escalating stakes and new information, not repetitive rhetorical questions. Each section must either advance this chain or deliver a necessary short bridge. If two adjacent sections teach essentially the same thing, consolidate or differentiate them. The conclusion should resolve the opening question as far as evidence allows, explicitly distinguish remaining uncertainty, and leave one coherent takeaway rather than merely repeat the timeline.

Use natural, conversational, intelligible English intended to be SPOKEN by a narrator. Prefer short and medium sentences with variable rhythm and precise verbs. Translate complexity into familiar human consequences without anachronistic jokes, unsupported psychology, melodrama, academic hedging in every sentence, slogan-like clickbait, or textbook transitions such as “Next, let us discuss.” A rare technical term or date is allowed when necessary; explain it in everyday words. Avoid the unchanging rhythm “In YEAR, something happened” at every section opening.

Every section must contain: (i) one clear question or narrative purpose, (ii) a meaningful new discovery or shift in understanding, (iii) its connection to the broader question, and (iv) a natural handoff. Write those elements as **actual narration**, not section labels or production notes. The opening and conclusion can be shorter. Suggested 6–9 sections for 7 minutes is an editorial heuristic, not a schema minimum. No spoken heading, `[SFX]` tag, producer note, JSON label, or camera instruction inside `sections[].narration`.

@@HVS_RUNTIME_BUDGET_LINE@@

The word budget is NOT a mandate to pad with fluff or cut necessary qualifiers. The G2 recorded Final WAV, spoken pauses and alignment determine the achieved duration, not this estimate. Prefer an effective narrative over exact word quotas. Respect the operator's `editorial_goals` when they remain compatible with history and contracts.

## 5. Filmable visual direction — content must change, not only the camera

Think in visible events and transformations, not a series of narration subtitles. A useful visual setup gives the viewer a new relationship, comparison, location, document detail, timeframe, quantity or consequence. A camera push-in on unchanged text is not itself a new information beat. Alternate appropriate visual families: geography, archival objects/primary text, dated chronology, contextual reconstruction, evidence comparison and concise explanatory graphics. Do not force a map into every section or produce repetitive headline cards.

For a seven-minute film, approximately 20–30 distinct setups is a **starting estimate**, not a validation requirement or reason to invent filler. Prefer fewer justified, developed setups over many empty ones. Provide enough distinct sections/setups and meaningful within-setup visual beats to cover the full spoken narrative without minutes of static content. Vary framing and camera intention only when they support a reveal or spatial explanation. A section may have more than one setup; setup order must remain compatible with spoken cue order.

Every `visual_setups[]` element MUST include a `preferred_template` selected from T01–T10 even though the frozen schema does not require it. Do not output null, omit it, or invent another template. `preferred_template` expresses editorial intent; it is NOT a completed G4 `template_payload`, approved asset, map geometry, final animation or render instruction. Match `intent`, `composition_intent`, `camera_intent`, available slots and asset requirements to the selected registered template and actual source feasibility.

For every setup, declare all visual source slots and on-screen text IDs before referencing them. Each `visual_beats[]` entry must have a meaningful `shot_goal`, one resolvable `focus_ref`, a cue into the frozen narration, valid optional relationships, explicit staging and honest continuity. `staging[].ref`, `after_ref`, relationships, `continuity.carry_refs` and `focus_ref` may refer only to declared `asset_slots[].slot_id` or `on_screen_text[].text_id` in that setup. Never use an undeclared name as a layer. Only use source claims/requirements that exist in the top-level arrays and are linked to the relevant section/setup. Keep beat IDs globally unique across all `visual_beats[]`.

**Separate reveal intention from execution time:** `visual_beats[]` plus their spoken cues drive G4 beat windows and animation scheduling after G2 Final WordTimingMap exists. `reveal_plan[]` describes the intended editorial reveal order and targets; it does NOT create a second independent timeline or provide approved timestamps. To avoid contradictory authoring, reference the **same beat_id and cue** as a corresponding local `visual_beats[]` entry when describing that beat in `reveal_plan[]`. This is a V3 authoring convention, not a claim that the frozen schema requires 1:1 entries or that every reveal action becomes a renderer event. Do not invent extra “timing beats” inside `reveal_plan`.

`reuse_setup_id` is null unless there is a deliberate editorial reuse of an EARLIER different setup. Reuse does not transfer ownership of asset slots or source rights and does not permit cloning an undocumented image. In a new setup, explicitly declare its own relevant slots/refs. Use `continuity` to explain what the viewer carries forward, not to assert an asset is historically identical without evidence.

## 6. Registered template capabilities — choose for visual meaning

Use T01–T10 only. Do not force one of every template. These are **editorial capabilities**, not a license to invent underlying media. Select a layout variant only within the registered A/B/C/AUTO options allowed by the schema and later G4 controls.

- **T01 — Period geography:** a sourced map with headline/callout. Use for justified location and historical context; map year and G3 original must support the shown geography. Without evidence, use a non-geographic graphic instead.
- **T02 — Person/identity:** a portrait, name/date and concise context. Distinguish authentic contemporary depiction, later portrayal, and reconstructed illustration. Do not claim a verified likeness when unsupported.
- **T03 — Archival photograph collage:** use only for actual historically possible, rights-reviewed photographic sources matching the registered archival-photo slot. Never place medieval artwork in a photographic slot or pass a modern reenactment off as archival photography. For pre-photography events, prefer a document/artwork-compatible T06/T09 or another suitable template instead of forcing T03.
- **T04 — Verified route:** period map plus evidenced route. Do not hypothesize exact paths, create fake waypoints, or claim a geographic LineString from narrative plausibility. Requires later G3-approved source and G4 route geometry.
- **T05 — Chronology:** date/sequence comparisons tied to sourced events. The sequence must reveal a real development, not merely repeat years already spoken.
- **T06 — Document/excerpt:** present an attributable historical document with honest excerpt status. Never choose a verified-verbatim mode from model-authored UNVERIFIED claims.
- **T07 — Two-period map comparison:** needs TWO distinct defensible periods, source identities and map geometries. Not a generic before/after invented boundary transition.
- **T08 — Sourced quantitative/date fact:** use reviewed figures with units, period and denominator. A static qualified figure is safer than an animated counter; actual intermediate numeric-series animation requires separately reviewed G1 evidence.
- **T09 — Evidence headline/document:** concise textual synthesis anchored in a named claim and source requirement where relevant. Avoid full-screen narration transcripts and repeated static slides.
- **T10 — Contextual cause/consequence:** supported callouts on a scene/map context or non-geographic composition as available. A causal connector is an editorial relation, NOT a geographic route. Never mark an unverified causal link as documented.

No model-authored visual direction can itself approve a photograph, artwork, portrait, historical document, map, quote, numeric series or copyright license. These assets and typed template payloads are supplied and reviewed later by the operator at G3/G4.

## 7. Exact cue contract — mirror the existing backend tokenizer

The external story does NOT contain WordTimingMap IDs, audio timestamps or precomputed frames. But its cues must be prepared for the existing G2/G4 word resolver.

1. Freeze `sections[].narration` before choosing cues. The backend splits each narration section into whitespace-delimited tokens (`narration.split()`). It then normalizes **each token independently** by removing all non-word characters and case-folding. Phrase tokens are created by the same whitespace split and normalization. Punctuation cannot join or split token counts. Thus narration `Black-Death` is one normalized token (`blackdeath`), while cue `Black Death` is TWO tokens and does NOT match. Never write a cue by merely paraphrasing what the narration appears to say.
2. For each beat choose a DISTINCTIVE contiguous sequence of roughly 3–8 spoken whitespace tokens copied from that exact narration section, with the same token boundaries and words. Avoid empty-normalized tokens, too-common short phrases or fragile punctuation-only tokens. You may use a shorter phrase only when necessary for exact source matching.
3. `cue.section_id` must equal that beat's `section_ref`, and this section must appear in its setup's `section_refs`. `occurrence` is the ZERO-BASED position of the complete normalized phrase among ALL matches within that section: first match 0, second 1, third 2. It is NOT the cue's position among beats or an index across all sections.
4. Traverse the setups in output order and, within each setup, `visual_beats[]` in array order. Their resolved phrase spans must move strictly forward across the ENTIRE film. No duplicate timing span, backward jump, overlapping spoken words, or section regression. Prefer one cue at each genuinely new spoken idea. A later repeated phrase may use `occurrence: 1` (or more) only if it truly is that occurrence in that SAME section.
5. `reveal_plan[]` can refer to matching local beat IDs/cues to describe its editorial intent, but it does not get an extra timeline slot. Do not add separate overlapping timing anchors for that description.
6. A successful textual check does not guarantee G4 timing: ElevenLabs alignment, the actual Final WAV, frame rounding and frozen source SHA can still reject cues. Do not fabricate word IDs, frame IDs, sample timestamps, alignment scores or duration. Operator G2/G4 must resolve them from real audio.

Illustrative token-matching rule (NOT output JSON): if a narration section says `The Black-Death reached the port; then the Black-Death returned.`, the phrase `the Black-Death` appears twice as normalized adjacent tokens; use occurrence 0 and occurrence 1 for those two different locations. The phrase `the Black Death` does NOT match the original tokenization.

## 8. IDs, continuity, scope, historical maps and output readiness

Use valid, stable, human-readable IDs conforming to the canonical schema (examples: `sec_001`, `claim_001`, `req_001`, `setup_001`, `slot_001`, `text_001`, `beat_001`). IDs must be unique inside each domain; **all `visual_beats[].beat_id` must be globally unique**. `reveal_plan` may intentionally refer to one of those existing beat IDs under the authoring convention above; this is not a second globally unique visual beat.

Every section `claim_refs` and `asset_requirement_refs` must resolve to top-level `claims[]` and `asset_requirements[]`. Every setup `section_refs`, `claim_refs`, `requirement_refs` must resolve to top-level IDs. Every `direction.asset_slots[].requirement_id` must resolve to an existing requirement associated with the setup. Every `on_screen_text[].claim_ref` and every beat `source_claim_refs` must resolve to declared claims when non-null or non-empty. No dangling focus, staging, relationship, continuity or setup-reuse references. A `historical_map_requirement_id` is null when no authorized map is relevant; otherwise it must refer to a suitable declared historical-map requirement. All `visual_beats[]` and `reveal_plan[]` must be present with at least one entry each, as the frozen schema requires.

A requirement classified `MODERN_RECONSTRUCTION` or `AI_ILLUSTRATION` must be described as representative when its exact historical appearance is unknown. A `HISTORICAL_MAP` requirement is a request for possible sourced map data, not a guarantee it exists or that its period can be rendered. Keep maps/years/source periods internally consistent, including `start_year <= end_year`. A truthful image that cannot support a selected template is not a reason to invent missing details; select a feasible template and revise direction.

The metadata block is NOT the output schema. The final object's top-level keys are exactly those allowed by `StoryPackage.v1`: `schema_version`, `project`, `sections`, `claims`, `asset_requirements`, `visual_setups`, and `authoring_source`. `authoring_source` is exactly `external_chatgpt`; `schema_version` is exactly `StoryPackage.v1`; `project.project_id` must equal the operator metadata. Do not add `brief_version`, `runtime_minutes`, `editorial_goals`, `audience`, `output`, `research_notes`, `validation_report`, or custom fields to that JSON.

## 9. Silent final quality and contract preflight

Complete each check **before** emitting the object; do not output the checklist:

**NARRATION:** Is the hook a concrete conflict or question in the first ~15–25 spoken seconds? Does each section change the viewer's understanding, progress the causal investigation and bridge to the next? Is the narration natural spoken English rather than documentary boilerplate? Are uncertain facts accurately qualified? Is the conclusion a genuine synthesis? Is the approximate length proportionate without padding?

**HISTORICAL FEASIBILITY:** Is every material assertion represented and honestly UNVERIFIED? Are only genuinely known/checked URLs used? Are critical claims marked? Do media classes match their historical period (especially pre-photography eras)? Are reconstructions, later artwork and period originals distinguished? Are routes/quantities/causal links no more precise than their evidence?

**FILMABILITY:** Are visual setups purposeful across the whole film rather than repetitive cards? Are template IDs within T01–T10 and present on every setup? Does each template have a plausible source requirement and achievable visual role? Are map, route, portrait, document and counter dependencies honestly deferred to G3/G4? Does every setup have a real visual information change?

**TIMING:** Do phrase strings precisely match whitespace-token sequences in their own frozen narration section after per-token punctuation removal/casefold? Is every zero-based occurrence correct? Are all visual-beat cue spans chronological and non-overlapping across every setup? Do reveal intentions reuse the matching visual-beat anchor rather than competing timing cues?

**REFERENCES AND SCHEMA:** Is the result one syntactically valid JSON object? Are all required properties and enum/const values exact, without unexpected properties? Are IDs unique and refs resolvable? Are mandatory `preferred_template`, `visual_beats`, `reveal_plan`, staging and continuity populated? Are project, source and runtime metadata kept in their correct places? Is there no JSX, media binary, approved asset, G2 WordTimingMap, G4 template payload or invented geometry in StoryPackage?

If you can programmatically validate the proposed output using an available JSON tool, do so before returning it, but never claim that silent reasoning alone proves schema or compiler PASS. Do not assert G1 approval, G2 Final WAV alignment, G3 rights approval, G4 compilation, or final media production.

**FINAL OUTPUT RULE:** Return ONE complete canonical `StoryPackage.v1` JSON object as raw UTF-8 JSON, with no markdown code fence, comments, prose, wrapper, outline or second artifact. Never return a truncated object. If a file-output facility is available in this external chat, a complete `.json` file is also acceptable. The operator will import the file/object into Historical Video Studio, where backend validators and human gates remain authoritative.

## APPENDIX — Exact frozen StoryPackage.v1 JSON Schema

Canonical on-disk schema copied unchanged as one JSON value. This appendix constrains the final output but is NOT itself an additional output object:

~~~json
@@HVS_CANONICAL_SCHEMA_JSON@@
~~~
