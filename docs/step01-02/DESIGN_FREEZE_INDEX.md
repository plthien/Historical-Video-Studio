# Design Freeze Index — Step 01 and Step 02
**Product:** Historical Video Studio | **Language:** English-first | **Mode:** Windows local, new clean build | **Scope:** Product & Architecture + Visual System.
**Status:** Step 01/02 design frozen pending green latest Windows design-contract CI. Step 03 (real video PoC) and Step 04 (full app) are NOT built.

## Canonical documents
1. [01_PRODUCT_SPEC.md](01_PRODUCT_SPEC.md) — product, user journeys, six workspaces and five explicit review gates.
2. [02_SYSTEM_ARCHITECTURE.md](02_SYSTEM_ARCHITECTURE.md) — adapters, tasks, revision DAG, provider ownership and renderer.
3. [03_VISUAL_PRODUCTION_SPEC.md](03_VISUAL_PRODUCTION_SPEC.md) — reference breakdown, style, motion grammar and T01/T02/T03/T04/T08 detailed sheets.
4. [04_DATA_CONTRACTS_AND_GATES.md](04_DATA_CONTRACTS_AND_GATES.md) — schema inventory, semantic validation and five approval transitions.
5. [05_IMPLEMENTATION_PLAN.md](05_IMPLEMENTATION_PLAN.md) — Step 03 60–90s two-topic pilots, Step 04 full application, acceptance gates.

## Supporting machine-readables and UX
- [TEMPLATE_DESIGN_SHEETS_T05_T10.md](TEMPLATE_DESIGN_SHEETS_T05_T10.md): full remaining T05–T10 V1 sheets.
- [UI_WIREFRAME_AND_API_MATRIX.md](UI_WIREFRAME_AND_API_MATRIX.md): screen/route/gate behavior.
- [Interactive UI mockup](../../ui/mockups/index.html): static HTML/JS design prototype, open directly on a desktop browser. No Remotion Player or live backend embedded.
- [Schema and fixture folder](../../contracts/README.md): 10 JSON Schema Draft 2020-12 shapes, 10 synthetic fixture instances.
- [OpenAPI](../../contracts/openapi.yaml): design-level local service routes, no endpoints currently active.
- [Provider contracts](../../contracts/providers): ElevenLabs alignment and G-Labs webhook projection.
- [Final six-role audit](STEP01_STEP02_FINAL_SIX_ROLE_AUDIT.md) and original [Master Spec](../design/MASTER_DESIGN_SPECIFICATION_V1.md), [latest decisions](../design/DESIGN_DECISIONS_2026-10-19.md).

## Precedence
1. User-agreed decisions in docs/design/DESIGN_DECISIONS_2026-10-19.md (English-first, G-Labs documented-contract-first).
2. This Step 01/02 detailed package for field/interaction specifics.
3. Original MASTER_DESIGN_SPECIFICATION_V1 and original six-role audit as historical baseline.
Any new scope amendment after freeze requires documented decision and revisioned schema/style/template contract; never silently rewrite old evidence.

## Step 01/02 vs Step 03/04
**Done at design layer:** reproducible authoring data shape, user approval transitions, source/rights policy, ten visual template contracts, motion preset dictionary, renderer architecture, UI wireflow, implementation tasks, offline tests.
**Not implemented:** Python backend, React production UI, Kokoro synthesis, ElevenLabs real alignment, G-Labs live provider, archive search, Remotion preview/render, MP4 outputs, real source licensing; all require Step 03 and Step 04.

## Validation
Windows workflow .github/workflows/design-contracts-windows.yml:
~~~
python -m pip install -r requirements-design.txt
python scripts/check_design_contracts.py
python -m unittest discover -s tests/contracts -p "test_*.py" -v
~~~
The suite covers schema shape, sample semantics, no fallback auto approval, historical asset class, date evidence and preset type; it **does not** run a real provider or check actual photographic content.
