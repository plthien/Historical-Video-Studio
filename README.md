# Historical Video Studio

**New Windows-local video production application — design-only repository (Step 01/02).** The implementation will produce English-first source-aware historical motion graphics via external ChatGPT StoryPackage JSON, reusable Remotion templates and five mandatory human approvals. No old Historical-Motion-Graphics-Studio runtime/migrations, no LLM API or coding agents during video production.

## Status (19 October 2026)

**Step 01 — Product & Architecture Specification:** design freeze package created, pending/latest Windows contract CI.  
**Step 02 — Visual System & Template Specification:** ten scene-template design sheets and selected motion preset grammar, design freeze.  
**Step 03 — End-to-End Proof of Concept:** NOT IMPLEMENTED; needs two 60–90s real videos with the same five initial templates.  
**Step 04 — Full Application Implementation:** NOT IMPLEMENTED; needs production UI, archive and G-Labs, full editor/render and Windows release.

## Start here

- **[Step 01/02 Design Freeze Index](docs/step01-02/DESIGN_FREEZE_INDEX.md)** — canonical five documents, schemas, UI mockup, final audit.
- [Product Spec](docs/step01-02/01_PRODUCT_SPEC.md) · [System Architecture](docs/step01-02/02_SYSTEM_ARCHITECTURE.md) · [Visual System](docs/step01-02/03_VISUAL_PRODUCTION_SPEC.md) · [Data Contracts & Gates](docs/step01-02/04_DATA_CONTRACTS_AND_GATES.md) · [Implementation Plan](docs/step01-02/05_IMPLEMENTATION_PLAN.md).
- [UI clickable mockup](ui/mockups/index.html) — static HTML demonstrating transitions only, **not connected to providers**.
- [JSON Schema fixtures, API, provider specs](contracts/README.md) and [Windows Design CI](.github/workflows/design-contracts-windows.yml).
- [Updated Six-Role Audit](docs/step01-02/STEP01_STEP02_FINAL_SIX_ROLE_AUDIT.md).

## Frozen decisions

ChatGPT is external and exports one importable JSON. Kokoro and ElevenLabs are interchangeable TTS adapters; ElevenLabs **separately** provides Forced Alignment on approved final WAV. For missing historical archival assets, the operator chooses Manual Search + Upload **or** Managed Fallback, with mandatory **later** human review of generated candidates. Five gates: G1 Story, G2 Voice, G3 Assets, G4 Storyboard, G5 Final Video. G-Labs is implemented against the user-supplied webhook document without requiring live access for design/code kickoff, but no actual API test or successful video output has been claimed.

## Historical baseline

[Original Master Design Specification V1.0](docs/design/MASTER_DESIGN_SPECIFICATION_V1.md) · [Original Six-Role Audit](docs/design/SIX_ROLE_DESIGN_AUDIT_V1.md) · [Latest design decision overrides](docs/design/DESIGN_DECISIONS_2026-10-19.md). These are preserved as design history; detailed 01–05 specs and the decision record take precedence on implementation detail.

## Contract checks (Windows)
~~~
python -m pip install -r requirements-design.txt
python scripts/check_design_contracts.py
python -m unittest discover -s tests/contracts -p "test_*.py" -v
~~~
Contract PASS does not mean real provider, historical rights, storyboard quality, Remotion parity or MP4 acceptance. Step 03 proves these through real pilot evidence.
