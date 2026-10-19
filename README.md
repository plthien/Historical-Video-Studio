# Historical Video Studio

**NEW Windows-only local application — design/contract repository. Production code has not yet been implemented.**
Goal: build the entire 5–10 minute historical motion graphics production flow in one production codebase (no standalone pilot), from one external ChatGPT JSON → Five Human Review Gates → Voice + Historical Assets/G-Labs → Deterministic Remotion Storyboard → Rendered MP4 + Attribution.

## Current authority (19 October 2026)
**[FULL-FLOW IMPLEMENTATION PLAN](docs/step01-02/05_IMPLEMENTATION_PLAN.md)** — target is complete application V1 (2 engineering phases, overlapping workstreams), **not** Step03/Step04 PoC-first development. The original Master Spec/pilot sequencing is retained in docs/design as historical design baseline only.

## Start here
- [Design freeze and handoff index](docs/step01-02/DESIGN_FREEZE_INDEX.md)
- [01 Product Spec](docs/step01-02/01_PRODUCT_SPEC.md) • [02 Architecture](docs/step01-02/02_SYSTEM_ARCHITECTURE.md) • [03 Visual Production](docs/step01-02/03_VISUAL_PRODUCTION_SPEC.md) • [04 Data Contracts & Gates](docs/step01-02/04_DATA_CONTRACTS_AND_GATES.md) • [05 Full-Flow Implementation Plan](docs/step01-02/05_IMPLEMENTATION_PLAN.md).
- [Complete StoryPackage→VisualBlueprint→CompiledTimeline Contract](docs/step01-02/FULL_FLOW_VISUAL_COMPILER_CONTRACT.md) and [historical map projection rules](docs/step01-02/HISTORICAL_MAP_ENGINE.md).
- [Contracts](contracts/README.md): 12 JSON Schema shapes, full-length 24-section/48-scene synthetic fixtures, 30 layout variants, 18 motion presets, base OpenAPI and 25-operation full-flow extension.
- [Original G-Labs webhook — verbatim](contracts/providers/reference/WEBHOOK_INTEGRATION.vi(1).md), [archival adapter matrix](contracts/providers/ARCHIVE_ADAPTER_MATRIX.v1.md).
- [UI design mockup](ui/mockups/index.html): static interactive mock ONLY; not running real providers or Remotion.

## Frozen user decisions
English-first. Kokoro and ElevenLabs TTS provider registry; **ElevenLabs Forced Alignment of the approved final WAV** regardless of synthesizer. G-Labs implementation from user-provided webhook (no live integration prerequisite before coding). Missing historical image requires user to choose Manual Search+Upload or Managed Fallback and later individually review/approve the returned candidate. Five gates: G1 Story, G2 Voice, G3 Assets, G4 Storyboard, G5 Final Video. No LLM API / Codex / other coding agent needed by the finished studio. No old Historical-Motion-Graphics-Studio runtime or database migration.

## Validate contracts on Windows
python -m pip install -r requirements-design.txt
python scripts/check_design_contracts.py
python -m unittest discover -s tests/contracts -p "test_*.py" -v

**A green design CI validates contracts only. No real TTS, forced alignment, archive/G-Labs account action, renderer, video or G5 approval is claimed.**
