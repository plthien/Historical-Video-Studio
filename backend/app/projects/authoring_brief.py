"""Deterministic, external-only StoryPackage authoring brief (no model calls)."""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.contracts import ContractViolation
from backend.app.projects.storage import ProjectStore

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts/schema/StoryPackage.v1.schema.json"
BRIEF_VERSION = "HVS-EXTERNAL-STORY-BRIEF.v1"


def build_brief(store: ProjectStore, project_id: str, *, topic: str, audience: str,
                runtime_minutes: int, editorial_goals: str) -> str:
    if not 5 <= runtime_minutes <= 10 or not topic.strip() or not audience.strip():
        raise ContractViolation("BRIEF_INPUT_INVALID", project_id, "Provide topic, audience, and 5–10 minute runtime.")
    store.revision(project_id)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    metadata = {
        "brief_version": BRIEF_VERSION,
        "project_id": project_id,
        "topic": topic,
        "audience": audience,
        "runtime_minutes": runtime_minutes,
        "editorial_goals": editorial_goals,
        "language": "en",
        "style_id": "HistoryEditorialPaper.v1",
        "output": "16:9 1920x1080 30fps",
    }
    return "\n".join((
        "# Historical Video Studio — External ChatGPT authoring brief",
        "## Versioned operator inputs", "~~~json",
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2), "~~~",
        "## Authoring task",
        "Write one English-language historical documentary StoryPackage.v1 JSON for the exact project ID.",
        "Respect the requested topic, audience, runtime, and editorial goals.",
        "Use historically accurate, explicitly attributable claims. Source leads are UNVERIFIED suggestions,",
        "not confirmation of history, media identity, copyright clearance or archival licensing.",
        "Use unique stable identifiers, consistent section/claim/requirement/setup cross-references.",
        "Include all required visual_setups.direction details, including visual_beats, reveal_plan,",
        "staging, continuity and cue phrases that occur verbatim in the corresponding narration.",
        "Choose T01–T10 according to the actual visual intent and approved historical evidence.",
        "For maps, use period-appropriate reviewed requirements: never assume modern borders.",
        "Do not invent verified sources, dates, quotations, routes, claims, asset rights or licensed photographs.",
        "Do not produce JSX, JavaScript, render code, commentary, markdown fences or a second artifact.",
        "Required negative examples: do not assign a fake archive URL; do not claim a source is VERIFIED",
        "without human review; do not reference a section, claim or asset requirement that does not exist.",
        "Assets remain unapproved until independent G3 review; all facts remain unapproved until G1.",
        "Return ONLY one valid JSON object matching this complete canonical schema:",
        "## StoryPackage.v1 JSON Schema", "~~~json",
        json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2), "~~~",
        "The user will manually import your JSON into the local app for validation and review.",
    ))
