# Design-time Contracts — Step 01/02

**Version:** V1.0 design freeze. These files are authoritative *proposed interfaces*, not implemented application code or evidence of a working provider.

- schema/: twelve strict JSON Schema Draft 2020–12 contracts, filename matches each schema_version.
- examples/: one synthetic shape-valid fixture per schema; plus a 360-second/48-scene long-form synthetic contract set. **They do not establish historical truth, production rights or a working provider.** Cross-object fixtures require explicit binding and semantics checks.
- openapi.yaml: proposed local FastAPI endpoints for six UI workspaces, review gates and jobs.
- providers/: boundary-specific adapter behavior from official docs / user-supplied contract.
- ../scripts/check_design_contracts.py and ../tests/contracts/: Python validation, ten positive fixtures and negative semantic cases.

Run on Windows (Python 3.12):
~~~
python -m pip install -r requirements-design.txt
python scripts/check_design_contracts.py
python -m unittest discover -s tests/contracts -p "test_*.py" -v
~~~
The distinction matters: JSON Schema verifies shape/type/allowlisted keys. Semantic validation must additionally verify ID uniqueness, revision hashes, word samples and ordered ranges, exact asset approval and mapping, route/date rights, layer cue relationships, scene clipping and human approval state. Partial validators are **design acceptance scaffolding**, not production validation coverage.

No schema gives permission to run code, arbitrary URLs, or object-selected JSX/React. Voice alignment is ElevenLabs regardless of TTS source; English is V1 lane. See docs/step01-02/04_DATA_CONTRACTS_AND_GATES.md and /05_IMPLEMENTATION_PLAN.md.
