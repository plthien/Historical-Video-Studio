# PR13 V3 visual review ledger

All files are real Chromium captures. Downstream media is controlled and labelled synthetic; it is not live historical-rights acceptance. Geometry tests asserted a 238 +/- 2 px sidebar, at least 16 px right clearance, no document horizontal overflow, and no browser page errors.

| State | 1366x768 | 1920x1080 | Independent review |
|---|---|---|---|
| Project A | `screenshots/projects-A-1366.png` | `screenshots/projects-A-1920.png` | PASS: true New/Recent cards, no fake gates. The initially wrapped `Open` label at 1366 was fixed and recaptured. |
| Project B | `screenshots/projects-B-1366.png` | `screenshots/projects-B-1920.png` | PASS: Configure/Brief/Import hierarchy is clear; V2 label, selectable prompt and actions are visible without horizontal clipping. |
| Story G1 | `screenshots/story-G1-1366.png` | `screenshots/story-G1-1920.png` | PASS: section rail, narration, claims and human-review controls are readable; blocked critical claims are truthful. |
| Voice G2 | `screenshots/pr13-g2-populated-selected-audio-1366.png` | `screenshots/pr13-g2-populated-selected-audio-1920.png` | PASS: selected section, playable generated WAV, attempt identity and final alignment panel are visible; no fake successful alignment. |
| Assets G3 | `screenshots/pr13-g3-populated-approved-original-candidate-1366.png` | `screenshots/pr13-g3-populated-approved-original-candidate-1920.png` | PASS: manual original, exact SHA, synthetic context, rights-review state and independent selection are visible. Candidate card was explicitly scrolled into view before recapture. |
| Storyboard G4 | `screenshots/pr13-g4-populated-real-player-1366.png` | `screenshots/pr13-g4-populated-real-player-1920.png` | PASS: genuine compiled scenes, read-only Remotion Player, seek, scene rail and inspector; draft authority is clearly separated from approval/render. |
| Delivery G5 | `screenshots/pr13-g5-populated-actual-video-1366.png` | `screenshots/pr13-g5-populated-actual-video-1920.png` | PASS: real 120-frame encoded MP4, QC PASS, G4/G5 authority and immutable export. Capture waits for loaded data and seeks to a rendered frame. |

The 1366 captures intentionally show less vertical content; all affected pages scroll normally. No control is horizontally unreachable, no Player is stretched outside its 16:9 region, and the 1920 captures confirm the full multi-column hierarchy.
