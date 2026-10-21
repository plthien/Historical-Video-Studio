"""B1-03: deterministic local focus/staging window summary (no keyframes or pixels)."""
from __future__ import annotations
from backend.app.contracts import ContractViolation

def group_staging(windows:list[dict],audio_total_samples:int,sample_rate:int) -> list[dict]:
    if sample_rate<=0 or audio_total_samples<=0:
        raise ContractViolation("ALIGNMENT_TIME_INVALID","audio","Load approved WAV samples.")
    by_setup={}
    for w in windows:
        by_setup.setdefault(w["setup_id"],[]).append(w)
    scenes=[]
    for setup_id,rows in by_setup.items():
        if any(a["start_sample"]>b["start_sample"] for a,b in zip(rows,rows[1:])):
            raise ContractViolation("CUE_RANGE_INVALID",setup_id,"Visual beats must follow authored time order.")
        for row in rows:
            if row["start_frame"]<0 or row["end_frame"]<=row["start_frame"]:
                raise ContractViolation("FRAME_INTERVAL_INVALID",row["beat_id"],"Positive half-open frame window required.")
        scenes.append({"setup_id":setup_id,"start_frame":min(r["start_frame"] for r in rows),
                       "end_frame":max(r["end_frame"] for r in rows),
                       "focus_sequence":[{"beat_id":r["beat_id"],"focus_ref":r["focus_ref"],
                                          "word_ids":r["word_ids"],"start_frame":r["start_frame"],
                                          "end_frame":r["end_frame"]} for r in rows]})
    return scenes
