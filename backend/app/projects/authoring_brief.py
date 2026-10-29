"""Deterministic, external-only StoryPackage authoring brief (no model calls)."""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.contracts import ContractViolation
from backend.app.projects.storage import ProjectStore

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "contracts/schema/StoryPackage.v1.schema.json"
LAYOUTS_PATH = ROOT / "contracts/registries/layouts.v1.json"
BRIEF_VERSION = "HVS-EXTERNAL-STORY-BRIEF.v2"

# Editorial meaning is policy, while supported IDs are checked against the
# canonical registry at build time. This prevents prompt drift into fictitious capabilities.
TEMPLATE_GUIDANCE = {
    "T01": ("period map plus headline/callout", "map year and G3 source must support geography"),
    "T02": ("sourced portrait plus identity/date", "label authentic versus reconstructed"),
    "T03": ("rights-reviewed archival image/collage", "never fake archival media"),
    "T04": ("map plus evidence-backed ordered route", "never invent vectors or documented routes"),
    "T05": ("dated chronology", "events/dates need attributable support"),
    "T06": ("historical document/excerpt", "verbatim_verified requires G1 source authority"),
    "T07": ("two-period map comparison", "justify both years and sources"),
    "T08": ("numerical fact/metric explanation", "needs reviewed values, units, subject, period and denominator"),
    "T09": ("documentary headline plus evidence", "avoid narration dumps/static-card repetition"),
    "T10": ("map-contextual consequence/causal callouts", "an editorial causal connector is not a geographic route"),
}


def _template_guide() -> list[str]:
    registry = json.loads(LAYOUTS_PATH.read_text(encoding="utf-8"))
    layouts = registry.get("layouts", [])
    registered = {layout.get("template_id") for layout in layouts}
    if registered != set(TEMPLATE_GUIDANCE):
        raise ContractViolation("BRIEF_TEMPLATE_GUIDE_STALE", "layouts.v1.json",
                                "Update V2 guidance to match the canonical T01-T10 registry.")
    lines = []
    for template_id, (usage, caution) in TEMPLATE_GUIDANCE.items():
        lines.append(f"- {template_id}: {usage}. Caution: {caution}.")
    return lines


def build_brief(store: ProjectStore, project_id: str, *, topic: str, audience: str,
                runtime_minutes: int, editorial_goals: str) -> str:
    if not 5 <= runtime_minutes <= 10 or not topic.strip() or not audience.strip():
        raise ContractViolation("BRIEF_INPUT_INVALID", project_id, "Provide topic, audience, and 5-10 minute runtime.")
    store.revision(project_id)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    word_min, word_max = runtime_minutes * 150, runtime_minutes * 170
    metadata = {
        "brief_version": BRIEF_VERSION, "project_id": project_id, "topic": topic,
        "audience": audience, "runtime_minutes": runtime_minutes,
        "editorial_goals": editorial_goals, "language": "en",
        "style_id": "HistoryEditorialPaper.v1", "output": "16:9 1920x1080 30fps",
    }
    lines = [
        "# Historical Video Studio - External ChatGPT authoring brief",
        f"Brief version: {BRIEF_VERSION}", "",
        "## Operator inputs & production boundaries",
        "Treat metadata as exact operator input; preserve editorial_goals verbatim unless it conflicts with accuracy or contract.",
        "~~~json", json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2), "~~~",
        "Draft a coherent, evidence-led historical film for this project, not disconnected facts or an encyclopedia entry.",
        "The app makes no LLM/browsing request. Do not imply it or the operator verified your research.",
        "Keep language=en, style_id=HistoryEditorialPaper.v1, 16:9 1920x1080 30fps; 5-10 minutes.",
        "StoryPackage.v1 is the only output. Do not invent aligned word IDs/timestamps, approved assets, template payloads, map geometry, JSX, or render code; G2/G3/G4 own those.", "",
        "## Historical research and uncertainty policy",
        "Distinguish documented evidence, scholarly inference, and unsupported speculation. Browse only if you actually can; never pretend to have browsed.",
        "Source leads are unreviewed, not verification/rights evidence. Use only checkable URLs genuinely observed or known; empty source_leads is truthful and requires operator attention. Never add arbitrary homepages.",
        "Represent each material claim, event/date, quantity, and map/route assertion as a claim. Set all model-authored claims[].status to UNVERIFIED. Keep unresolved critical claims critical=true; qualify or omit weak assertions.",
        "Quote named speakers only with source-attributable verbatim wording; otherwise paraphrase transparently. Never choose verbatim_verified without G1 source authority or present reconstruction as archival footage.",
        "For quantities, state units, subject, period and denominator; report ranges/disagreement. Never invent mortality or spread-rate points.",
        "Match map periods/geography to evidence; never infer historical boundaries from modern maps. Without route evidence, avoid literal T04/T07 or request a permitted non-literal illustration.",
        "G1 claim and G3 rights review remain human. claim_review does not rewrite frozen claims[].status: UNVERIFIED remains ineligible for G4 verbatim_verified/documented causality unless an authorized, versioned G1 Story correction occurs. Never upcast it.", "",
        "## Narration architecture & spoken pacing",
        "Open with a concrete high-stakes question/conflict/paradox in the first 15-25 spoken seconds. Build an investigation arc: evidence -> implication -> next causal question, with fresh revelations and temporal/geographic bridges.",
        "Escalate to human/social consequences; close with evidence-bounded synthesis that answers the opening. Prefer natural spoken English over lecture tone, padding, year lists, empty adjectives, fake cliffhangers, or inflated certainty.",
        f"At the V2 planning envelope of 150-170 spoken WPM, aim for approximately {word_min:,}-{word_max:,} spoken words for {runtime_minutes} minutes, then leave a modest margin for pauses, titles, difficult maps, quotations and audio gaps.",
        "This is advisory; distribute by narrative purpose and never distort facts for a count. The approved G2 Final WAV/alignment, not words or target WPM, determine achieved duration.",
        "For seven minutes, roughly 6-9 sections is useful, not required. Each needs a micro-question, forward motion, bridge, and visual reason; openings/conclusions may be shorter. Keep production notes/headings out of narration.",
        "Operator goals outrank generic story heuristics when accuracy and contract remain intact.", "",
        "## Visual storytelling & continuity",
        "Plan the full duration. For seven minutes, 20-30 distinct setups is an editorial starting point, never an import/compiler minimum; adapt proportionally without quota scenes or text-card fatigue.",
        "Every visual_setups[] item MUST include preferred_template as T01-T10 although schema-optional. Never use null, omit it, or invent T11. Match intent/composition_intent/camera_intent to its capability.",
        "A setup is one composition; visual_beats are purposeful changes; reveal_plan schedules them. Include a meaningful beat/reveal and vary maps, timelines, sources, locations and justified reconstruction.",
        "Use declared asset_slots/on_screen_text only. Resolve focus_ref, staging ref/after_ref, relationships, continuity carry_refs and reveal references locally. Make every beat_id globally unique and stable.",
        "Continuity is deliberate camera/graphic evolution, not cloned assets. Reuse must name a previous different setup_id for an editorial reason. Image identity/rights await G3.",
        "HISTORICAL_MAP needs start_year <= end_year, honest exactness/map_reconstruction_policy, known genuine leads, and correct historical_map_requirement_id links. A template never verifies geography.", "",
        "## T01-T10 capabilities and dependencies",
        "Choose only evidence-supported templates; using all ten is not required.", *_template_guide(), "",
        "## Cue, IDs and semantic invariants",
        "Use unique IDs per section/claim/requirement/setup domain and globally unique beat IDs. Every claim, requirement, slot, text, setup, relationship, staging, continuity/reuse and focus reference must resolve.",
        "A cue is {section_id, phrase, occurrence}: section_id equals beat section_ref and belongs to setup section_refs. Choose a distinctive 3-8 word phrase wholly in that narration section.",
        "Occurrence is the zero-based index across exact normalized word-token matches in that section: 0 first, 1 second. Never use zero for a later repeat or borrow another section's match.",
        "Across authored setups/beats, cue ranges must be chronological and non-overlapping. Each reveal_plan cue resolves to its intended beat/section.",
        "This narration self-check is pre-alignment only. Real G2 normalization/tokenization and WAV timing may still produce CUE_MISSING, CUE_AMBIGUOUS, CUE_OCCURRENCE_INVALID, CUE_SECTION_MISMATCH, CUE_OVERLAP, or CUE_RANGE_INVALID. Never manufacture WordTimingMap data or timestamps in StoryPackage JSON.", "",
        "## Silent preflight & exact output format",
        "Check silently; do not emit this checklist or an extra object:",
        "A. Shape: exact schema keys/consts, mandatory fields, no additional properties/comments, finite numbers, valid supplied URIs, exact project ID/style/language, valid JSON.",
        "B. References: unique IDs and globally unique beats; all claim, requirement, slot, text, setup, focus, relationship, staging, continuity and reuse references resolve; preferred_template is present despite being schema-optional.",
        "C. Timeline: each phrase exists in its own section at the stated zero-based occurrence; beat/section equality; ordered non-overlapping spans and plausible visual coverage.",
        "D. History: every model-authored status UNVERIFIED; critical uncertainty explicit; no fabricated source, licence, quote, quantity, route, geometry or modern boundary; map period/geography matches known leads.",
        "E. Narration: coherent hook, causal arc, escalation, synthesis, natural English, approximate planning budget, varied evidence-led visuals, no repetitive production prose.",
        "F. Readiness: this is schema/semantic preflight only, never G1 APPROVED, G2 aligned, G3 rights-approved, G4 map-ingested, or G4 PASS.",
        "Return ONLY one complete StoryPackage.v1 JSON object: no prose, markdown fence, comments, wrapper, research audit, or second artifact.", "",
        "## APPENDIX - Exact StoryPackage.v1 canonical JSON Schema",
        "Canonical on-disk schema, copied unchanged as a JSON value:",
        "~~~json", json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2), "~~~",
    ]
    return "\n".join(lines)
