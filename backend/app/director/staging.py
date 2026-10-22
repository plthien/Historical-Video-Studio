"""B1-03: deterministic local focus/staging window summary (no keyframes or pixels)."""
from __future__ import annotations
from backend.app.contracts import ContractViolation

def group_staging(windows:list[dict],audio_total_samples:int,sample_rate:int) -> list[dict]:
    if sample_rate<=0 or audio_total_samples<=0:
        raise ContractViolation("ALIGNMENT_TIME_INVALID","audio","Load approved WAV samples.")
    total_frames=(audio_total_samples*30+sample_rate-1)//sample_rate
    if not windows:
        raise ContractViolation("FRAME_INTERVAL_INVALID","audio","At least one authored visual beat must cover approved audio.")
    previous=0
    for w in windows:
        if w["start_frame"]!=previous or w["end_frame"]<=w["start_frame"]:
            raise ContractViolation("FRAME_INTERVAL_INVALID",w["beat_id"],
                                    "Authored visual windows must be contiguous, positive and start at frame zero.")
        previous=w["end_frame"]
    if previous!=total_frames:
        raise ContractViolation("FRAME_INTERVAL_INVALID","audio",
                                "Final visual frame must equal ceil of approved WAV samples.")
    by_setup={}
    closed=set()
    current=None
    for w in windows:
        if w["setup_id"]!=current:
            if w["setup_id"] in closed:
                raise ContractViolation("CUE_RANGE_INVALID",w["setup_id"],
                                        "One setup must own a contiguous scene interval.")
            if current is not None:
                closed.add(current)
            current=w["setup_id"]
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
                                          "end_frame":r["end_frame"],
                                          "cue_start_frame":r["cue_start_frame"],
                                          "cue_end_frame":r["cue_end_frame"],
                                          "pre_cue_hold_frames":max(0,r["cue_start_frame"]-r["start_frame"])} for r in rows]})
    return scenes
