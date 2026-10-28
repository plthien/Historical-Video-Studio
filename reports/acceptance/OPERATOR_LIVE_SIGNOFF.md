# Full V1 live signoff checklist

1. Start the real local application with `scripts/windows/start-studio.ps1` and select a persistent data root.
2. Import two unrelated, operator-owned external StoryPackages. Review and explicitly decide G1 for each.
3. Configure the intended TTS provider and ElevenLabs locally without adding secrets to git. Approve G2, then verify the exact final WAV and forced-alignment word map.
4. Resolve every G3 requirement with legitimate originals. Inspect provenance, period suitability and rights; distinguish AI illustrations and explicitly approve G3.
5. Inspect the shared Remotion storyboard and approve G4. Render each project, confirm real FFprobe/frame/audio QC, review the complete audiovisual result and credits, then explicitly approve G5 and export.
6. Back up and restore the studio into a fresh destination. Reopen both projects and verify gate heads, sources, WAVs, renders, QC reports, credits and export SHA values.
7. Set `HVS_DB`, `HVS_MEDIA`, two comma-separated `HVS_LIVE_PROJECT_IDS`, `HVS_LIVE_OPERATOR_ATTESTATION=EXPLICIT_G1_G2_G3_G4_G5` and `HVS_LIVE_RIGHTS_ATTESTATION=VERIFIED_ORIGINAL_RIGHTS`.
8. Run `.venv\Scripts\python.exe -m backend.tools.smoke --case full-flow-two-topics --mode live`. Attach the two MP4s, JSON/log evidence and eight-role actual-media review outside git; do not commit large media or credentials.

The live command only verifies existing operator-owned outputs. It does not call paid providers, create approvals or generate replacement media.
