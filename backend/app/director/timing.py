"""B1-03: exact authored phrase occurrence → immutable alignment sample/frame cues."""
from __future__ import annotations
import re
from backend.app.contracts import ContractViolation,validate_document
from backend.app.voice.word_map import normalized

def _tokens(phrase):
    return [normalized(w) for w in phrase.split()]

def resolve_cue(cue:dict,word_map:dict,beat_id:str) -> dict:
    section=cue["section_id"]
    phrase=_tokens(cue["phrase"])
    if not phrase or not all(phrase):
        raise ContractViolation("CUE_MISSING",beat_id,"Author a nonempty spoken phrase exactly present in its section.")
    words=[w for w in word_map["words"] if w["section_id"]==section]
    matches=[words[i:i+len(phrase)] for i in range(len(words)-len(phrase)+1)
             if [normalized(w["text"]) for w in words[i:i+len(phrase)]]==phrase]
    occ=cue.get("occurrence")
    if not matches:
        raise ContractViolation("CUE_MISSING",beat_id,
                                f"Phrase {cue['phrase']!r} absent in section {section} aligned words.")
    if type(occ)!=int or occ<0:
        raise ContractViolation("CUE_AMBIGUOUS",beat_id,
                                "Set an explicit zero-based phrase occurrence; never silently choose the first match.")
    if occ>=len(matches):
        raise ContractViolation("CUE_OCCURRENCE_INVALID",beat_id,
                                f"Occurrence {occ} unavailable for {cue['phrase']!r} in {section}.")
    selected=matches[occ]
    return {"beat_id":beat_id,"section_id":section,
            "word_ids":[w["word_id"] for w in selected],
            "start_sample":selected[0]["start_sample"],
            "end_sample":selected[-1]["end_sample"],
            "occurrence":occ,"phrase":cue["phrase"]}

def sample_to_frames(start_sample:int,end_sample:int,sample_rate:int):
    if sample_rate<=0 or not 0<=start_sample<end_sample:
        raise ContractViolation("FRAME_INTERVAL_INVALID","samples",
                                "Need positive, ordered samples and a positive real WAV sample rate.")
    a=start_sample*30//sample_rate
    b=(end_sample*30+sample_rate-1)//sample_rate
    if b<=a:b=a+1
    return a,b

def bind_beats(blueprint:dict,word_map:dict, *,
               audio_sha256:str,transcript_sha256:str,audio_total_samples:int) -> list[dict]:
    validate_document("WordTimingMap.v1",word_map)
    if (blueprint["project_id"]!=word_map["project_id"] or
            word_map["audio_sha256"]!=audio_sha256 or word_map["transcript_sha256"]!=transcript_sha256):
        raise ContractViolation("ALIGNMENT_SOURCE_STALE",blueprint["project_id"],
                                "Use the exact approved final WAV/transcript and current ElevenLabs WordTimingMap.")
    sr=word_map["sample_rate"]
    if type(audio_total_samples)!=int or audio_total_samples<=0:
        raise ContractViolation("ALIGNMENT_TIME_INVALID","audio",
                                "Read real final WAV sample count; do not calculate duration from WPM.")
    previous=0
    sections={}
    for w in word_map["words"]:
        if not previous<=w["start_sample"]<w["end_sample"]<=audio_total_samples:
            raise ContractViolation("ALIGNMENT_TIME_INVALID",w["word_id"],
                                    "Aligned word samples overlap, reverse or exceed final WAV.")
        previous=w["end_sample"]
        sections.setdefault(w["section_id"],[]).append(w)
    output=[]
    all_beats=set()
    for plan in blueprint["setup_plans"]:
        beats=plan["editorial_direction"]["visual_beats"]
        resolved=[]
        for b in beats:
            bid=b["beat_id"]
            if bid in all_beats:
                raise ContractViolation("BEAT_DUPLICATE",bid,"Each authored beat ID must be globally unique.")
            all_beats.add(bid)
            if b["section_ref"]!=b["cue"]["section_id"] or b["section_ref"] not in plan["section_refs"]:
                raise ContractViolation("CUE_SECTION_MISMATCH",bid,"Cue section must be the beat's authored section.")
            item=resolve_cue(b["cue"],word_map,bid)
            item.update({"setup_id":plan["setup_id"],"focus_ref":b["focus_ref"],
                         "staging":b["staging"],"continuity":b["continuity"]})
            resolved.append(item)
        for i,item in enumerate(resolved):
            if i and item["start_sample"]<resolved[i-1]["end_sample"]:
                raise ContractViolation("CUE_OVERLAP",item["beat_id"],"Authored cues cannot reverse or overlap.")
            next_start=resolved[i+1]["start_sample"] if i+1<len(resolved) else audio_total_samples
            if next_start<=item["start_sample"] or next_start>audio_total_samples:
                raise ContractViolation("CUE_RANGE_INVALID",item["beat_id"],
                                        "Next beat must follow the cue within approved audio bounds.")
            # Store exact cue frames and staging window separately; no accumulated durations.
            cue_a,cue_b=sample_to_frames(item["start_sample"],item["end_sample"],sr)
            win_a=item["start_sample"]*30//sr
            win_b=(next_start*30+sr-1)//sr
            if win_b<=win_a:win_b=win_a+1
            output.append({**item,"cue_start_frame":cue_a,"cue_end_frame":cue_b,
                           "start_frame":win_a,"end_frame":win_b,
                           "duration_frames":win_b-win_a,"fps":30,
                           "audio_sha256":audio_sha256,"transcript_sha256":transcript_sha256})
    return output
