# External Story Brief V2

`HVS-EXTERNAL-STORY-BRIEF.v2` is a deterministic, project-bound prompt for manual use with external ChatGPT. The app does not call an LLM, browse, research, or approve the returned content. The only import artifact remains the frozen `StoryPackage.v1` JSON object.

## Authority and precedence

Canonical schemas, semantic validators, G1-G5 gate rules, the layout registry, approved source records, and real G2 alignment outrank prompt advice. Operator settings outrank generic storytelling advice where they do not conflict with history or contracts. V2 word, section, and setup ranges are planning guidance, not new import gates.

All externally drafted claims remain `UNVERIFIED`. Source leads are unreviewed leads, and an empty lead list is preferable to a fabricated URL. G1 reviews claims; G3 approves media identity and rights; G4 owns typed payloads and historical geometry. A persisted `claim_review` does not rewrite the frozen StoryPackage claim status, so `verbatim_verified` and documented-causality modes still require an explicitly authorized, versioned G1 Story correction when the frozen claim remains `UNVERIFIED`.

## Template mapping

The prompt checks its guide against `contracts/registries/layouts.v1.json` each time it builds:

| Template | Intended authored setup | Principal review risk |
|---|---|---|
| T01 | Period map and callout | Period/source support |
| T02 | Sourced portrait and identity | Authentic versus reconstructed |
| T03 | Archival image or collage | Media identity and rights |
| T04 | Evidence-backed route | Invented vectors/routes |
| T05 | Dated chronology | Unsupported event/date |
| T06 | Document or excerpt | Unverified verbatim quote |
| T07 | Two-period map comparison | Independently supported years/sources |
| T08 | Quantitative explanation | Units, subject, period, denominator |
| T09 | Documentary headline/evidence | Static-card or narration overload |
| T10 | Contextual consequences/causality | Editorial connector confused with route |

Every authored setup must include `preferred_template: "T01"` through `"T10"` even though that field remains schema-optional. This is a prompt/G4 readiness rule, not a frozen-schema change.

## Preflight meaning

The external model is asked to check output shape, reference integrity, cue occurrence/order, source uncertainty, and narration quality silently. This is text-only preflight. It is not G1 approval, G2 timing, G3 rights approval, map ingestion, or G4 compilation. Actual normalized words may still produce a `CUE_*` error after Final WAV alignment.

For each cue, `occurrence` is the zero-based match index of the normalized token sequence within its own narration section. Beat section and cue section must agree; authored cue spans must progress globally without overlap. The model must never invent a `WordTimingMap` or timestamps.

## Operator review rubric

For a real external draft, assess the opening question, causal progression, natural spoken prose, evidence-bounded synthesis, qualified quantities and quotations, source-lead traceability, period-map caveats, visual rhythm, and whether the full film develops rather than repeats. Then import the one JSON object and perform G1-G5 normally. A prompt sample is not a generated StoryPackage and does not demonstrate external-model quality.

## Known limits

- Estimated 150-170 WPM cannot predict the approved voice duration; Final WAV controls time.
- The prompt cannot verify a source, licence, historical boundary, route, quote, or statistic.
- Schema-valid JSON can still fail semantic or aligned timing checks.
- External-model quality requires a real external run and human assessment; automated tests prove only deterministic prompt and existing validator behavior.
