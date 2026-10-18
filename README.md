# Historical Video Studio

**Status:** Design only — new Windows-local project. No runtime implementation has been committed.

Historical Video Studio is designed to produce source-aware, motion-graphics historical videos from a manually imported **external ChatGPT JSON package**, with reusable Remotion scene templates, audio synchronization, and human approval gates. It is a **clean new build** and does not carry over the old Historical-Motion-Graphics-Studio runtime.

## Design documents

- [Master Design Specification V1.0](docs/design/MASTER_DESIGN_SPECIFICATION_V1.md) — product architecture, data boundaries, storyboard and motion design, gates, test plan.
- [Six-role Design Audit V1.0](docs/design/SIX_ROLE_DESIGN_AUDIT_V1.md) — director, editor, motion designer, architect, QA, operator audit.
- [Design package notes](docs/design/README_DELIVERABLES.md) — original package index.
- [Design decisions (19 Oct 2026)](docs/design/DESIGN_DECISIONS_2026-10-19.md) — latest confirmed scope/acceptance adjustments.

## Frozen product direction

- **External ChatGPT only:** JSON export/import, no LLM API; no Codex/Claude Code during video production.
- **Voice:** Kokoro and ElevenLabs TTS adapters; ElevenLabs Forced Alignment over approved final WAV.
- **Historical archival assets:** provenance/rights checks and user approval; when exact assets are missing, **user chooses** manual upload or managed fallback, and must review the fallback before using it.
- **Image generation:** G-Labs local webhook, implemented from the user-supplied integration contract.
- **Video:** Remotion shared composition for preview and MP4, reusable scene templates and constrained motion presets.
- **Human review:** G1 Story, G2 Voice, G3 Assets, G4 Storyboard, G5 Final Video.
- **Initial production language:** English (Vietnamese alignment is not a V1 blocking requirement).

This repository currently contains **documentation only**. Master-spec acceptance is conditional pending a functional pilot; design decisions are not evidence of live integrations or an exported video.
