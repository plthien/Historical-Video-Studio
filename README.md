# Historical Video Studio

Historical Video Studio is a single-user, Windows-local application for producing English historical motion documentaries. The implemented flow imports one external ChatGPT `StoryPackage.v1`, preserves five explicit operator review gates, assembles and aligns narration, reviews immutable historical sources, compiles the shared Remotion composition, renders H.264/AAC video, performs FFprobe/frame/audio QC, and exports only an approved G5 result with attribution.

The application does not call an LLM at runtime, does not auto-approve G1–G5, and does not treat synthetic CI fixtures as historical-rights or human-review evidence.

## Windows prerequisites

- Windows 10 or 11.
- Python 3.12 available as `py -3.12`.
- Node.js 22 and npm 10 or 11.
- FFmpeg and FFprobe on `PATH`.
- Network access for the first pinned `pip`/`npm ci`; provider credentials are needed only for explicitly selected live provider operations.

Validate a checkout from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/verify-environment.ps1
```

## Start, stop and reopen

The launcher bootstraps `.venv`, installs the pinned renderer dependencies when missing, builds the frontend when needed, starts the real FastAPI backend on `127.0.0.1`, serves the built six-workspace UI from that same process, verifies API/UI health and opens the browser:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/start-studio.ps1
```

Press Ctrl+C in the launcher window to stop the complete owned process tree. Existing local data is reopened from:

- Database: `data/historical-studio.sqlite`
- Immutable media: `data/media/`
- Launcher logs: `data/logs/`

Select another persistent location with `-DataRoot D:\HistoricalStudioData`. Use `-Port` if port 8000 is occupied. Automation uses `-Smoke -NoBrowser -SkipBootstrap`; smoke mode verifies the real API and UI and then terminates cleanly.

The launcher never starts a new paid provider submission. Startup only follows the existing durable recovery rules: deterministic local assembly/render may resume, while uncertain external work remains resumable by its original provider task identity or blocked for review.

## Provider configuration

Configure G-Labs, Europeana and ElevenLabs through the local Settings/owner workflow or documented environment variables. Secrets are machine-local and are deliberately excluded from packages and backups. After restoring on another machine, re-enter credentials explicitly; the restored job status remains unchanged until reconciliation.

## Backup and restore

Create a coherent SQLite snapshot plus every registered immutable artifact:

```powershell
.venv\Scripts\python.exe -m backend.tools.backup_restore backup `
  --database data\historical-studio.sqlite --media-root data\media `
  --destination D:\HVS-Backups\studio-2026-10-27
```

Restore only into a new destination:

```powershell
.venv\Scripts\python.exe -m backend.tools.backup_restore restore `
  --source D:\HVS-Backups\studio-2026-10-27 `
  --destination D:\Restored-Historical-Studio
```

Backup uses SQLite's backup API, verifies `integrity_check`, records project revisions plus a SHA-256 inventory, and verifies every artifact byte. Restore rejects an existing destination, missing/tampered files, a damaged database or an incompatible manifest. It does not migrate an older application database and does not include provider credentials.

## Build the Windows package

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/package.ps1
```

The output under `release/windows/` is a ZIP with the PowerShell launcher, application source, built frontend, renderer/contract sources, exact lockfiles and `package-manifest.json`. It is not advertised as a standalone EXE: the Windows prerequisites above remain required. Development caches, databases, logs, `.env` files, provider secrets and synthetic evidence are excluded.

## Verification and acceptance truth

Contract and owner tests are native-Windows checks. A short synthetic render proves application wiring and real FFmpeg/Remotion behavior only. Full V1 live acceptance additionally requires two unrelated genuine 5–10 minute projects, legitimate source rights, real TTS/alignment/provider evidence where applicable, and explicit human G1–G5 decisions. Missing inputs are reported as `BLOCKED` or `NOT_RUN`, never converted into a synthetic pass.

See [AGENTS.md](AGENTS.md), [Coding Rules](docs/engineering/CODING_RULES.md), the [task matrix](docs/step01-02/IMPLEMENTATION_TASK_MATRIX.md), and the [implementation plan](docs/step01-02/05_IMPLEMENTATION_PLAN.md) for the binding scope and evidence rules.
