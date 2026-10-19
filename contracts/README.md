# Contracts — Full-Flow Design V1
All files are design authority for future implementation, not a running app.

- **Twelve** strict Draft 2020-12 JSON schemas under schema/ and twelve valid example shapes under examples/.
- longform/: synthetic 24 English sections / 48 scenes / 360-second, 10800-frame full-length structure; not real audio, approved source or render proof.
- registries/: 30 template variants (T01–T10/A–C) and 18 bounded motion presets; enforced by semantic validators and future compiler.
- openapi.yaml: original core API; openapi-fullflow-extension.json: additive **25** typed edit/regenerate/asset review/storyboard/export/provider endpoints. They have no overlapping path-method keys; implementation merges both specs and maintains one FastAPI router namespace.
- providers/reference/WEBHOOK_INTEGRATION.vi(1).md: byte-for-byte original user-supplied G-Labs webhook document, 1,148 lines. Do not replace it with our summary.
- providers/: separate detailed adapters for Wikimedia Commons, Library of Congress, Europeana, ElevenLabs forced alignment and G-Labs scoped image generation; candidate source evidence is not historical accuracy or rights approval.
- ../scripts/check_design_contracts.py and ../tests/contracts/: Windows-only static shape and negative semantic tests. Mock passing does not imply live audio, G-Labs, real assets or MP4 success.

Run from root on Windows: python -m pip install -r requirements-design.txt; python scripts/check_design_contracts.py; python -m unittest discover -s tests/contracts -p "test_*.py" -v.

Latest design implementation authority: docs/step01-02/05_IMPLEMENTATION_PLAN.md (FULL-FLOW, NO PILOT) and FULL_FLOW_VISUAL_COMPILER_CONTRACT.md.
