# Post-PR12 UI parity inventory — implementation snapshot

Baseline: `main@d368088dba5713b3b4b51b635f585585bd8baf9a`. Approved static baseline: `ui/mockups/index.html`. Never treat the static simulation as runtime proof.

| Workspace | Approved region | Production owner | API authority / gap |
|---|---|---|---|
| 01 Project & ChatGPT | Prompt builder, project profile, Story JSON import | `frontend/src/App.tsx`, `frontend/src/api/client.ts` | `/projects`, `/authoring-settings`, `/authoring-brief`, `/story/import`; versioned external-only brief now wired, not reviewed |
| 02 Story review G1 | Script, claims, evidence, human gate decision | `App.tsx`, `backend/app/api/server.py` | `/story`, `/story/sections/{id}` PATCH, `/claims/{id}/review`, `/gates/G1/decision`; bounded correction wired |
| 03 Voice Studio G2 | Section attempts, waveform/playback, selection/correction, final WAV/alignment | `frontend/src/workspaces/Voice/VoiceStudio.tsx` | `backend/app/api/voice.py`; owner logic retained, layout comparison NOT_COMPARABLE pending Chromium |
| 04 Historical Assets G3 | Requirements board, originals, managed/manual resolution, explicit rights/batch approval | `frontend/src/workspaces/Assets/AssetStudio.tsx` | `backend/app/api/assets.py`; existing review owner retained, layout NOT_COMPARABLE |
| 05 Motion Storyboard G4 | Scene list, real Player, timeline and inspector, typed compile | `frontend/src/workspaces/Storyboard/StoryboardStudio.tsx` | `backend/app/api/storyboard.py`, `backend/app/director/blueprint.py`; initial typed payload authoring and compile route implemented; native Windows verified integration NOT RUN |
| 06 Render & Delivery G5 | Render/QC, review media, exact export, credits | `frontend/src/workspaces/Delivery/DeliveryStudio.tsx` | `backend/app/api/delivery.py`; existing owner logic retained, layout NOT_COMPARABLE |

## Source-authority gap — initial G4 compile

`normalize_story(story,payloads_by_setup,...)` requires exactly one explicit template payload for every `visual_setups[]` element and validates against the frozen `VisualBlueprint.v1` template union. `StoryPackage.v1` supplies editorial direction/cues but **does not provide full discriminated template payloads**, and cannot authorize implicit dates, quotes, map routes or media. `template_payloads.require_payload` additionally enforces T04 route geometry, distinct T07 map states, and T10 editorial connector distinction. A production compile button must remain blocked until a reviewed authoring store, per-template input validation, current G1/G2/G3 identity checks, and a genuine `compile_from_store` bridge exist.

## Acceptance evidence still required

- Approved mock and running production app screenshots at both 1366×768 and 1920×1080 for all six workspaces; all 12 comparison pairs are **NOT RUN**, not PASS.
- Native Windows React build, Python tests and Playwright, managed job/rights cases, authentic Remotion Player and Node frame equivalence: **NOT RUN on this branch**.
- Full two-topic 5–10-minute live operator acceptance: **NOT RUN**.
- No fake preview, simulated MP4, synthetic approval or operator attestation is implied by the current changes.

This inventory intentionally does **not** sign off WP0–WP4 or any G01–G12 gate.
