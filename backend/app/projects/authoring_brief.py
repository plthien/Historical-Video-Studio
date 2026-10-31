"""Deterministic, external-only StoryPackage authoring brief (no model calls)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from backend.app.contracts import ContractViolation
from backend.app.projects.storage import ProjectStore

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "contracts/schema/StoryPackage.v1.schema.json"
LAYOUTS_PATH = ROOT / "contracts/registries/layouts.v1.json"
V3_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "external_story_brief_v3.md"
BRIEF_VERSION = "HVS-EXTERNAL-STORY-BRIEF.v3"
SENTINELS = (
    "@@HVS_OPERATOR_METADATA_JSON@@",
    "@@HVS_RUNTIME_BUDGET_LINE@@",
    "@@HVS_CANONICAL_SCHEMA_JSON@@",
)

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
                                "Update V3 guidance to match the canonical T01-T10 registry.")
    lines = []
    for template_id, (usage, caution) in TEMPLATE_GUIDANCE.items():
        lines.append(f"- {template_id}: {usage}. Caution: {caution}.")
    return lines


def _render_v3(metadata: dict, schema: dict, runtime_minutes: int) -> str:
    template = V3_PROMPT_PATH.read_text(encoding="utf-8")
    if any(template.count(token) != 1 for token in SENTINELS):
        raise ContractViolation("BRIEF_TEMPLATE_INVALID", str(V3_PROMPT_PATH),
                                "Repair the checked-in V3 prompt sentinel contract.")
    substitutions = {
        SENTINELS[0]: json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2),
        SENTINELS[1]: (
            f"At the provisional 150–170 spoken WPM planning envelope, {runtime_minutes} minutes "
            f"corresponds to approximately {runtime_minutes*150:,}–{runtime_minutes*170:,} spoken "
            "words before allowances for pauses, difficult names, titles and audio gaps. "
            "Treat this as editorial guidance, not a schema or timed-audio gate; "
            "G2 Final WAV/alignment owns actual duration."
        ),
        SENTINELS[2]: json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2),
    }
    marker_pattern = re.compile("|".join(re.escape(token) for token in SENTINELS))
    matches = marker_pattern.findall(template)
    if len(matches) != 3 or set(matches) != set(SENTINELS):
        raise ContractViolation("BRIEF_TEMPLATE_INVALID", str(V3_PROMPT_PATH),
                                "V3 prompt markers must occur exactly once each.")
    # One pass is essential: sentinel-looking operator text is data, not a marker.
    return marker_pattern.sub(lambda match: substitutions[match.group(0)], template)


def build_brief(store: ProjectStore, project_id: str, *, topic: str, audience: str,
                runtime_minutes: int, editorial_goals: str) -> str:
    if (type(runtime_minutes) is not int or not 5 <= runtime_minutes <= 10
            or not topic.strip() or not audience.strip()):
        raise ContractViolation("BRIEF_INPUT_INVALID", project_id, "Provide topic, audience, and 5-10 minute runtime.")
    store.revision(project_id)
    _template_guide()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    metadata = {
        "brief_version": BRIEF_VERSION, "project_id": project_id, "topic": topic,
        "audience": audience, "runtime_minutes": runtime_minutes,
        "editorial_goals": editorial_goals, "language": "en",
        "style_id": "HistoryEditorialPaper.v1", "output": "16:9 1920x1080 30fps",
    }
    return _render_v3(metadata, schema, runtime_minutes)
