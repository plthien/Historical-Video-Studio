# PR #13 V2 baseline audit · pre-repair source inspection
Date 2026-10-28; immutable starting HEAD `6048c72af5968af5c1f0da361ff379d28b989c6b`.
Source authority: user-approved V2 plan, repository owner files, GitHub Actions evidence; screenshots mentioned by plan are operator feedback, not independently regenerated here.

| Finding | Type | Exact owner | Observed baseline | Evidence |
|---|---|---|---|---|
| Child overflowing grid track | GEOMETRY | frontend/src/styles.css | No global border-box; sidebar track 238px plus padding | Direct source |
| Empty-project disabled authoring wall | HIERARCHY | frontend/src/App.tsx | Authoring fields rendered without project; complete CTA | Direct source |
| Generic stacked Voice/Assets/G4/G5 | HIERARCHY | workspace owner components | Rendered form-first, media secondary | Direct source |
| G4 map bridge empty map_requests | FUNCTIONAL | backend/app/api/storyboard.py | compile_from_store(...map_requests={}) | Direct source and compiler |
| G4 raw JSON-only | FUNCTIONAL | BlueprintAuthoring.tsx | Schema details + textarea | Direct source |
| Static mock PNG comparisons only | EVIDENCE | ui-parity.spec.ts | Fresh empty projects for all six spaces | Direct source |
| Stale frontend bundle accepted | FUNCTIONAL | start-studio.ps1 | Build only when dist/index.html missing | Direct source |
| Windows CI FFmpeg failed | INFRA | post-pr12-ui-parity-windows.yml | Bootstrap before FFmpeg preflight | V2 user inspection of run 40659903613 |
| Pre-repair actual browser images | EVIDENCE | Native Windows Chromium | Not captured by this session; no false PASS | NOT_RUN |

Owner protection: A1–B3 historical contracts and prior pass evidence cannot be changed to silence failures. No separate PR.
