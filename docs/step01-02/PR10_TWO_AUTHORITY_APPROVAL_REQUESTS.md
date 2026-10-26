# PR #10 — Two narrowly scoped G1/G3 authority requests (NOT APPROVED)

This is a decision packet, not an amendment to frozen G1/G2/G3 contracts. **No migration, approval record, historical value, or asset choice set is created by this PR.** Motion, camera, word and transition work proceeds independently.

## Decision 1 — May G1 authorize intermediate historical numbers?

**Current blocker:** `number-count` has one `source_claim_id` and scalar `end_value`, but no immutable G1-approved series. `intermediate_truthful: true` is not evidentiary authority. Production remains `RENDER_NUMBER_SERIES_UNVERIFIED`. Synthetic Remotion counting now has its own explicit test-only sequence; that test does not grant G1 approval.

**Smallest proposed additive G1 record, owner approval required:**
```json
{
  "schema_version": "ApprovedNumericSeries.v1",
  "project_id": "same canonical G1 project",
  "source_claim_id": "existing frozen G1 claim",
  "series_id": "stable new series ID",
  "values": [
    {"frame_offset": 0, "value": "decimal as string", "source_evidence_sha256": "64 lowercase hex"},
    {"frame_offset": 15, "value": "decimal as string", "source_evidence_sha256": "64 lowercase hex"}
  ],
  "unit": "explicit physical/chronological unit",
  "precision": 0,
  "display_interpolation": "STEP_VERIFIED_VALUES_ONLY",
  "original_story_sha256": "64 lowercase hex",
  "operator_approval_id": "new immutable G1 owner review event",
  "approved_series_sha256": "SHA256 of canonical record"
}
```
The authorized endpoint must equal the frozen claim text and `number-count.end_value`; each distinct displayed value must have actual G1-reviewed evidence. STEP mode MUST NOT create values between reviewed entries. If continuous interpolation is required, the G1 owner must separately approve the mathematical interpolation semantics and evidence. No implicit interpolation is permitted.

**Schema/API change on explicit approval:** add an *optional* G1 series review operation and immutable series head keyed by `(project_id, source_claim_id, series_id)`; add an optional B2 event reference `approved_numeric_series_id` in the registered `number-count` params and enforce source SHA + approval-head equality in `compile_event` and `HistoryComposition`. Existing G1 story/word map is unchanged. Missing optional reference preserves fail-closed behavior; no bulk migration.

**Required acceptance:** real owner approval, exact text/units/precision/endpoints, exact event frame mapping, G1 SHA staleness, negative wrong claim/unknown intermediate/changed evidence/order/precision, Chromium distinct intermediate frames, exact final display, no upstream G2/G3 mutation.

**Owner decision required:** APPROVE or REJECT this G1 additive series authority. PR #10 does not self-approve it.

## Decision 2 — May G3 authorize a concurrent same-slot choice set?

**Current blocker:** `asset_approval_heads` stores one current head for each `(project_id,requirement_id)`. Older `asset_approval_events` are historical and **not** additional currently approved choices. G4 still rejects changed `approved_asset_id`.

**Smallest proposed additive G3 storage (explicit owner approval required):**
```sql
CREATE TABLE asset_current_choice_set_heads (
 project_id TEXT NOT NULL,
 requirement_id TEXT NOT NULL,
 choice_set_id TEXT NOT NULL,
 choice_set_sha256 TEXT NOT NULL,
 operator_approval_id TEXT NOT NULL,
 PRIMARY KEY(project_id, requirement_id)
);
CREATE TABLE asset_current_choice_set_items (
 choice_set_id TEXT NOT NULL,
 candidate_id TEXT NOT NULL,
 candidate_sha256 TEXT NOT NULL,
 original_sha256 TEXT NOT NULL,
 rights_evidence_sha256 TEXT NOT NULL,
 approval_record_id TEXT NOT NULL,
 requirement_sha256 TEXT NOT NULL,
 PRIMARY KEY(choice_set_id, candidate_id)
);
```
This table must remain empty until an explicit G3 operator action creates a reviewed, immutable **CURRENT** choice-set snapshot. The action validates the *current* G1 requirement hash, media original bytes and approved rights for each item; older events never automatically become eligible.

**Schema/API change on explicit approval:** add G3 `POST /assets/requirements/{requirement_id}/choice-sets/approve` with expected_revision, candidate IDs + source/rights verification and explicit operator reason; expose only the current set on existing read API, with snapshot SHA. G4 `LayerEdit.approved_asset_id` accepts a new choice only when in the same current set/requirement/slot with matched original SHA/rights; stale snapshots return 409 or 424, illegal candidates return 422. Preserve per-G4 CAS/idempotency, selected-setup recompilation, G1/G2/G3 approval-head immutability and only G4/G5 staleness. Existing single-head behavior remains default; no inferred migration.

**Required acceptance:** two synthetic candidates approved through the real G3 operator transaction (not inserted directly in SQLite), G4 choose A/B and render distinct same-slot pixels with legitimate byte SHA, SQLite cold reopen, positive immutable rights, negative historical/revoked/cross-project/wrong-slot/wrong-source/stale-SHA/forged candidates, no unexpected G1/G2/G3 mutation.

**Owner decision required:** APPROVE or REJECT the additive concurrent G3 choice-set approval workflow. PR #10 does not self-approve it.
