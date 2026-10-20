"""Normalize provider-derived seconds into verified immutable native samples."""
from __future__ import annotations
import math
import re
from backend.app.contracts import ContractViolation, validate_document

_PUNCT = re.compile(r"[^\w]+", re.UNICODE)


def normalized(value: str) -> str:
    return _PUNCT.sub("", value).casefold()


def word_map(project: str, final: dict, transcript: str, response: dict) -> dict:
    tokens = [(t, o["section_id"]) for o, part in zip(
        final["section_offsets"], transcript.split("\n"))
        for t in part.split()]
    raw = response.get("words")
    if not isinstance(raw, list) or len(raw) != len(tokens) or not raw:
        raise ContractViolation("ALIGNMENT_TRANSCRIPT_MISMATCH", project,
                                "Provider word count does not match the exact final transcript.")
    sample_rate, duration = final["sample_rate"], final["duration_samples"]
    outputs = []
    previous_end = 0
    for i, (item, (expected_text, _section)) in enumerate(zip(raw, tokens)):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ContractViolation("ALIGNMENT_RESPONSE_INVALID", project, "Invalid word entry.")
        if not normalized(item["text"]) or normalized(item["text"]) != normalized(expected_text):
            raise ContractViolation("ALIGNMENT_TRANSCRIPT_MISMATCH", project,
                                    "Provider word sequence differs from canonical transcript.")
        start, end = item.get("start"), item.get("end")
        if (type(start) not in (float, int) or type(end) not in (float, int) or
                not math.isfinite(start) or not math.isfinite(end)):
            raise ContractViolation("ALIGNMENT_TIME_INVALID", project, "Word timestamps must be finite seconds.")
        a, b = round(start * sample_rate), round(end * sample_rate)
        if not (0 <= previous_end <= a < b <= duration):
            raise ContractViolation("ALIGNMENT_TIME_INVALID", project,
                                    "Word samples overlap, reverse or exceed final WAV.")
        offsets = [o for o in final["section_offsets"]
                   if o["start_sample"] <= a < b <= o["end_sample"]]
        if len(offsets) != 1 or offsets[0]["section_id"] != _section:
            raise ContractViolation("ALIGNMENT_SECTION_MISMATCH", project,
                                    "Word timing crosses section boundaries.")
        loss = item.get("loss")
        if loss is not None and (type(loss) not in (float, int) or
                                 not math.isfinite(loss) or loss < 0):
            raise ContractViolation("ALIGNMENT_RESPONSE_INVALID", project, "Invalid loss value.")
        outputs.append({"word_id": f"word_{i+1:06d}", "section_id": _section, "text": expected_text,
                        "start_sample": a, "end_sample": b, "loss": loss})
        previous_end = b
    result = {"schema_version": "WordTimingMap.v1", "project_id": project,
              "provider_id": "elevenlabs_forced_alignment",
              "audio_sha256": final["audio_sha256"],
              "transcript_sha256": final["transcript_sha256"],
              "sample_rate": sample_rate, "words": outputs, "anomalies": []}
    validate_document("WordTimingMap.v1", result)
    return result
