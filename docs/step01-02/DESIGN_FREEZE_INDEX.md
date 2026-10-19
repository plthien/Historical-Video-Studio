# Step 01–02 — Full-Flow Design Handoff (2026-10-19 targeted repair)
**Status:** design authority for complete Windows V1 implementation; no isolated PoC/Pilot product stage. Live provider/video acceptance still requires implementation evidence.
**Execution roadmap:** [05_IMPLEMENTATION_PLAN.md](05_IMPLEMENTATION_PLAN.md) — full app in two engineering phases with dependency-aware workstreams.

## Canonical documents
1. [01_PRODUCT_SPEC.md](01_PRODUCT_SPEC.md) — workflow, review gates, UI.
2. [02_SYSTEM_ARCHITECTURE.md](02_SYSTEM_ARCHITECTURE.md) — adapters, jobs, storage, renderer.
3. [03_VISUAL_PRODUCTION_SPEC.md](03_VISUAL_PRODUCTION_SPEC.md) — historical editorial grammar and 10 templates.
4. [04_DATA_CONTRACTS_AND_GATES.md](04_DATA_CONTRACTS_AND_GATES.md) — semantic guards, versioning, review approvals.
5. [05_IMPLEMENTATION_PLAN.md](05_IMPLEMENTATION_PLAN.md) — **full flow and Windows release**, replacing prior pilot-first plan.

## Mandatory complete-machine-readable extensions
- [StoryPackage → VisualBlueprint → CompiledTimeline](FULL_FLOW_VISUAL_COMPILER_CONTRACT.md): source precedence, cue-to-frame binding, absolute layer/crop/mask/camera/keyframe output and dependency hashes.
- [Historical map engine](HISTORICAL_MAP_ENGINE.md): historical year-aware geometry, projection, routes and source review.
- [Template T05–T10 sheets](TEMPLATE_DESIGN_SHEETS_T05_T10.md) and [all 30 versioned layout variants](../../contracts/registries/layouts.v1.json); [18 motion presets](../../contracts/registries/motion-presets.v1.json).
- [12 JSON Schemas](../../contracts/schema), 12 strict fixtures and [24-section/48-scene/360s long-form synthetic fixtures](../../contracts/examples/longform).
- [Base OpenAPI](../../contracts/openapi.yaml) plus [25 full-flow extension operations](../../contracts/openapi-fullflow-extension.json) (zero overlapping method/path; implementation combines).
- [Original verbatim G-Labs webhook](../../contracts/providers/reference/WEBHOOK_INTEGRATION.vi(1).md) and [three archival-source adapters](../../contracts/providers/ARCHIVE_ADAPTER_MATRIX.v1.md).
- [UI mockup](../../ui/mockups/index.html) and [UI/API mapping](UI_WIREFRAME_AND_API_MATRIX.md).

## Precedence (avoid conflicting pilot statements)
1. Latest direct user requirements: **implement full production flow, no separate pilot**; English-first; G-Labs contract-first; five review gates.
2. FULL_FLOW_VISUAL_COMPILER_CONTRACT, HISTORICAL_MAP_ENGINE, updated 12 JSON Schemas and registries, API core+extension.
3. **05_IMPLEMENTATION_PLAN.md** (replaces all legacy pilot-first phase sequencing).
4. Remaining Step01/02 supporting specs and prior Master Spec only as historical rationale. When a legacy document uses the term Pilot, treat that language as superseded rather than implementation authority.

## Validation and truth-in-status
Windows-only .github/workflows/design-contracts-windows.yml checks JSON schemas/fixtures, semantic negatives, long-form shape, OpenAPI and registry coherence. This is contract CI, **not** a video quality or provider-runtime test. The long-form fixture contains unverified claims and synthetic timestamps; it cannot receive G1/G3 approval. Production acceptance requires full 5–10min MP4 and G1–G5 real human review.
