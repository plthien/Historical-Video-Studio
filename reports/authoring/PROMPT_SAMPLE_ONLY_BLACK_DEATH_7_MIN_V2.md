# Historical Video Studio - External ChatGPT authoring brief
Brief version: HVS-EXTERNAL-STORY-BRIEF.v2

## Operator inputs & production boundaries
Treat metadata as exact operator input; preserve editorial_goals verbatim unless it conflicts with accuracy or contract.
~~~json
{
  "audience": "Adults",
  "brief_version": "HVS-EXTERNAL-STORY-BRIEF.v2",
  "editorial_goals": "PROMPT_SAMPLE_ONLY. Prioritize historical maps, timeline, carefully qualified quantities, source traceability, and explicit reconstruction caveats.",
  "language": "en",
  "output": "16:9 1920x1080 30fps",
  "project_id": "proj_prompt_sample_black_death_v2",
  "runtime_minutes": 7,
  "style_id": "HistoryEditorialPaper.v1",
  "topic": "How the Black Death Spread Across Europe in Just Six Years (1347-1353)"
}
~~~
Draft a coherent, evidence-led historical film for this project, not disconnected facts or an encyclopedia entry.
The app makes no LLM/browsing request. Do not imply it or the operator verified your research.
Keep language=en, style_id=HistoryEditorialPaper.v1, 16:9 1920x1080 30fps; 5-10 minutes.
StoryPackage.v1 is the only output. Do not invent aligned word IDs/timestamps, approved assets, template payloads, map geometry, JSX, or render code; G2/G3/G4 own those.

## Historical research and uncertainty policy
Distinguish documented evidence, scholarly inference, and unsupported speculation. Browse only if you actually can; never pretend to have browsed.
Source leads are unreviewed, not verification/rights evidence. Use only checkable URLs genuinely observed or known; empty source_leads is truthful and requires operator attention. Never add arbitrary homepages.
Represent each material claim, event/date, quantity, and map/route assertion as a claim. Set all model-authored claims[].status to UNVERIFIED. Keep unresolved critical claims critical=true; qualify or omit weak assertions.
Quote named speakers only with source-attributable verbatim wording; otherwise paraphrase transparently. Never choose verbatim_verified without G1 source authority or present reconstruction as archival footage.
For quantities, state units, subject, period and denominator; report ranges/disagreement. Never invent mortality or spread-rate points.
Match map periods/geography to evidence; never infer historical boundaries from modern maps. Without route evidence, avoid literal T04/T07 or request a permitted non-literal illustration.
G1 claim and G3 rights review remain human. claim_review does not rewrite frozen claims[].status: UNVERIFIED remains ineligible for G4 verbatim_verified/documented causality unless an authorized, versioned G1 Story correction occurs. Never upcast it.

## Narration architecture & spoken pacing
Open with a concrete high-stakes question/conflict/paradox in the first 15-25 spoken seconds. Build an investigation arc: evidence -> implication -> next causal question, with fresh revelations and temporal/geographic bridges.
Escalate to human/social consequences; close with evidence-bounded synthesis that answers the opening. Prefer natural spoken English over lecture tone, padding, year lists, empty adjectives, fake cliffhangers, or inflated certainty.
At the V2 planning envelope of 150-170 spoken WPM, aim for approximately 1,050-1,190 spoken words for 7 minutes, then leave a modest margin for pauses, titles, difficult maps, quotations and audio gaps.
This is advisory; distribute by narrative purpose and never distort facts for a count. The approved G2 Final WAV/alignment, not words or target WPM, determine achieved duration.
For seven minutes, roughly 6-9 sections is useful, not required. Each needs a micro-question, forward motion, bridge, and visual reason; openings/conclusions may be shorter. Keep production notes/headings out of narration.
Operator goals outrank generic story heuristics when accuracy and contract remain intact.

## Visual storytelling & continuity
Plan the full duration. For seven minutes, 20-30 distinct setups is an editorial starting point, never an import/compiler minimum; adapt proportionally without quota scenes or text-card fatigue.
Every visual_setups[] item MUST include preferred_template as T01-T10 although schema-optional. Never use null, omit it, or invent T11. Match intent/composition_intent/camera_intent to its capability.
A setup is one composition; visual_beats are purposeful changes; reveal_plan schedules them. Include a meaningful beat/reveal and vary maps, timelines, sources, locations and justified reconstruction.
Use declared asset_slots/on_screen_text only. Resolve focus_ref, staging ref/after_ref, relationships, continuity carry_refs and reveal references locally. Make every beat_id globally unique and stable.
Continuity is deliberate camera/graphic evolution, not cloned assets. Reuse must name a previous different setup_id for an editorial reason. Image identity/rights await G3.
HISTORICAL_MAP needs start_year <= end_year, honest exactness/map_reconstruction_policy, known genuine leads, and correct historical_map_requirement_id links. A template never verifies geography.

## T01-T10 capabilities and dependencies
Choose only evidence-supported templates; using all ten is not required.
- T01: period map plus headline/callout. Caution: map year and G3 source must support geography.
- T02: sourced portrait plus identity/date. Caution: label authentic versus reconstructed.
- T03: rights-reviewed archival image/collage. Caution: never fake archival media.
- T04: map plus evidence-backed ordered route. Caution: never invent vectors or documented routes.
- T05: dated chronology. Caution: events/dates need attributable support.
- T06: historical document/excerpt. Caution: verbatim_verified requires G1 source authority.
- T07: two-period map comparison. Caution: justify both years and sources.
- T08: numerical fact/metric explanation. Caution: needs reviewed values, units, subject, period and denominator.
- T09: documentary headline plus evidence. Caution: avoid narration dumps/static-card repetition.
- T10: map-contextual consequence/causal callouts. Caution: an editorial causal connector is not a geographic route.

## Cue, IDs and semantic invariants
Use unique IDs per section/claim/requirement/setup domain and globally unique beat IDs. Every claim, requirement, slot, text, setup, relationship, staging, continuity/reuse and focus reference must resolve.
A cue is {section_id, phrase, occurrence}: section_id equals beat section_ref and belongs to setup section_refs. Choose a distinctive 3-8 word phrase wholly in that narration section.
Occurrence is the zero-based index across exact normalized word-token matches in that section: 0 first, 1 second. Never use zero for a later repeat or borrow another section's match.
Across authored setups/beats, cue ranges must be chronological and non-overlapping. Each reveal_plan cue resolves to its intended beat/section.
This narration self-check is pre-alignment only. Real G2 normalization/tokenization and WAV timing may still produce CUE_MISSING, CUE_AMBIGUOUS, CUE_OCCURRENCE_INVALID, CUE_SECTION_MISMATCH, CUE_OVERLAP, or CUE_RANGE_INVALID. Never manufacture WordTimingMap data or timestamps in StoryPackage JSON.

## Silent preflight & exact output format
Check silently; do not emit this checklist or an extra object:
A. Shape: exact schema keys/consts, mandatory fields, no additional properties/comments, finite numbers, valid supplied URIs, exact project ID/style/language, valid JSON.
B. References: unique IDs and globally unique beats; all claim, requirement, slot, text, setup, focus, relationship, staging, continuity and reuse references resolve; preferred_template is present despite being schema-optional.
C. Timeline: each phrase exists in its own section at the stated zero-based occurrence; beat/section equality; ordered non-overlapping spans and plausible visual coverage.
D. History: every model-authored status UNVERIFIED; critical uncertainty explicit; no fabricated source, licence, quote, quantity, route, geometry or modern boundary; map period/geography matches known leads.
E. Narration: coherent hook, causal arc, escalation, synthesis, natural English, approximate planning budget, varied evidence-led visuals, no repetitive production prose.
F. Readiness: this is schema/semantic preflight only, never G1 APPROVED, G2 aligned, G3 rights-approved, G4 map-ingested, or G4 PASS.
Return ONLY one complete StoryPackage.v1 JSON object: no prose, markdown fence, comments, wrapper, research audit, or second artifact.

## APPENDIX - Exact StoryPackage.v1 canonical JSON Schema
Canonical on-disk schema, copied unchanged as a JSON value:
~~~json
{
  "$id": "https://historical-video-studio.local/contracts/StoryPackage.v1.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "additionalProperties": false,
  "description": "One external ChatGPT JSON contains script + sourcing leads + structured editorial direction for deterministic Storyboard Compiler. Direction contains no executable code or invented word timings.",
  "properties": {
    "asset_requirements": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "asset_class": {
            "enum": [
              "ARCHIVAL_PHOTO",
              "HISTORICAL_DOCUMENT",
              "HISTORICAL_ARTWORK",
              "HISTORICAL_MAP",
              "MODERN_RECONSTRUCTION",
              "AI_ILLUSTRATION"
            ],
            "type": "string"
          },
          "end_year": {
            "type": "integer"
          },
          "exactness": {
            "enum": [
              "event_exact",
              "subject_exact",
              "context_related",
              "illustrative"
            ],
            "type": "string"
          },
          "map_reconstruction_policy": {
            "enum": [
              "exact_period_map",
              "verified_schematic",
              "not_applicable"
            ],
            "type": "string"
          },
          "required": {
            "type": "boolean"
          },
          "requirement_id": {
            "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
            "type": "string"
          },
          "source_leads": {
            "items": {
              "additionalProperties": false,
              "properties": {
                "title": {
                  "type": "string"
                },
                "url": {
                  "format": "uri",
                  "pattern": "^https?://",
                  "type": "string"
                }
              },
              "required": [
                "url"
              ],
              "type": "object"
            },
            "minItems": 0,
            "type": "array"
          },
          "start_year": {
            "type": "integer"
          },
          "subject": {
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "requirement_id",
          "subject",
          "asset_class",
          "exactness",
          "required",
          "start_year",
          "end_year",
          "map_reconstruction_policy"
        ],
        "type": "object"
      },
      "minItems": 0,
      "type": "array"
    },
    "authoring_source": {
      "const": "external_chatgpt"
    },
    "claims": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "claim_id": {
            "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
            "type": "string"
          },
          "critical": {
            "type": "boolean"
          },
          "source_leads": {
            "items": {
              "additionalProperties": false,
              "properties": {
                "title": {
                  "type": "string"
                },
                "url": {
                  "format": "uri",
                  "pattern": "^https?://",
                  "type": "string"
                }
              },
              "required": [
                "url"
              ],
              "type": "object"
            },
            "minItems": 0,
            "type": "array"
          },
          "status": {
            "enum": [
              "UNVERIFIED",
              "REVIEWED",
              "VERIFIED"
            ],
            "type": "string"
          },
          "text": {
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "claim_id",
          "text",
          "source_leads",
          "critical",
          "status"
        ],
        "type": "object"
      },
      "minItems": 0,
      "type": "array"
    },
    "project": {
      "additionalProperties": false,
      "properties": {
        "language": {
          "const": "en"
        },
        "project_id": {
          "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
          "type": "string"
        },
        "style_id": {
          "const": "HistoryEditorialPaper.v1"
        },
        "title": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "project_id",
        "title",
        "language",
        "style_id"
      ],
      "type": "object"
    },
    "schema_version": {
      "const": "StoryPackage.v1"
    },
    "sections": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "asset_requirement_refs": {
            "items": {
              "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
              "type": "string"
            },
            "minItems": 0,
            "type": "array"
          },
          "claim_refs": {
            "items": {
              "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
              "type": "string"
            },
            "minItems": 0,
            "type": "array"
          },
          "narration": {
            "minLength": 10,
            "type": "string"
          },
          "section_id": {
            "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
            "type": "string"
          }
        },
        "required": [
          "section_id",
          "narration",
          "claim_refs",
          "asset_requirement_refs"
        ],
        "type": "object"
      },
      "minItems": 1,
      "type": "array"
    },
    "visual_setups": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "claim_refs": {
            "items": {
              "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
              "type": "string"
            },
            "minItems": 0,
            "type": "array"
          },
          "direction": {
            "additionalProperties": false,
            "properties": {
              "asset_slots": {
                "items": {
                  "additionalProperties": false,
                  "properties": {
                    "mandatory": {
                      "type": "boolean"
                    },
                    "requirement_id": {
                      "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                      "type": "string"
                    },
                    "semantic_role": {
                      "maxLength": 120,
                      "minLength": 1,
                      "type": "string"
                    },
                    "slot_id": {
                      "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                      "type": "string"
                    },
                    "usage": {
                      "enum": [
                        "foreground",
                        "background",
                        "context",
                        "evidence"
                      ],
                      "type": "string"
                    }
                  },
                  "required": [
                    "slot_id",
                    "requirement_id",
                    "semantic_role",
                    "usage",
                    "mandatory"
                  ],
                  "type": "object"
                },
                "minItems": 0,
                "type": "array"
              },
              "camera_intent": {
                "enum": [
                  "static",
                  "pan",
                  "push_in",
                  "pull_out",
                  "track_route",
                  "compare_locked"
                ],
                "type": "string"
              },
              "composition_intent": {
                "enum": [
                  "left_subject",
                  "right_subject",
                  "center_hero",
                  "split_evidence",
                  "map_full",
                  "collage",
                  "chronology"
                ],
                "type": "string"
              },
              "duration_policy": {
                "enum": [
                  "voice_locked",
                  "multi_section_hold"
                ],
                "type": "string"
              },
              "emotional_tone": {
                "enum": [
                  "neutral",
                  "serious",
                  "tense",
                  "reflective",
                  "reveal"
                ],
                "type": "string"
              },
              "historical_map_requirement_id": {
                "anyOf": [
                  {
                    "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "layout_variant_hint": {
                "enum": [
                  "A",
                  "B",
                  "C",
                  "AUTO"
                ],
                "type": "string"
              },
              "on_screen_text": {
                "items": {
                  "additionalProperties": false,
                  "properties": {
                    "claim_ref": {
                      "anyOf": [
                        {
                          "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ]
                    },
                    "max_lines": {
                      "maximum": 5,
                      "minimum": 1,
                      "type": "integer"
                    },
                    "role": {
                      "enum": [
                        "headline",
                        "date",
                        "quote",
                        "caption",
                        "source",
                        "map_label"
                      ],
                      "type": "string"
                    },
                    "text": {
                      "maxLength": 260,
                      "minLength": 1,
                      "type": "string"
                    },
                    "text_id": {
                      "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                      "type": "string"
                    }
                  },
                  "required": [
                    "text",
                    "role",
                    "claim_ref",
                    "text_id"
                  ],
                  "type": "object"
                },
                "minItems": 0,
                "type": "array"
              },
              "reuse_setup_id": {
                "anyOf": [
                  {
                    "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "reveal_plan": {
                "items": {
                  "additionalProperties": false,
                  "properties": {
                    "action": {
                      "enum": [
                        "establish",
                        "introduce",
                        "highlight",
                        "compare",
                        "move",
                        "hold",
                        "conclude"
                      ],
                      "type": "string"
                    },
                    "beat_id": {
                      "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                      "type": "string"
                    },
                    "cue": {
                      "additionalProperties": false,
                      "properties": {
                        "occurrence": {
                          "maximum": 100,
                          "minimum": 0,
                          "type": "integer"
                        },
                        "phrase": {
                          "maxLength": 200,
                          "minLength": 1,
                          "type": "string"
                        },
                        "section_id": {
                          "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                          "type": "string"
                        }
                      },
                      "required": [
                        "section_id",
                        "phrase",
                        "occurrence"
                      ],
                      "type": "object"
                    },
                    "priority": {
                      "maximum": 5,
                      "minimum": 1,
                      "type": "integer"
                    },
                    "target_role": {
                      "enum": [
                        "map",
                        "territory",
                        "route",
                        "portrait",
                        "archival_photo",
                        "document",
                        "headline",
                        "date",
                        "text",
                        "callout",
                        "camera"
                      ],
                      "type": "string"
                    }
                  },
                  "required": [
                    "beat_id",
                    "action",
                    "target_role",
                    "cue",
                    "priority"
                  ],
                  "type": "object"
                },
                "minItems": 1,
                "type": "array"
              },
              "transition_intent": {
                "enum": [
                  "hard_cut",
                  "cross_dissolve",
                  "mask_reveal",
                  "match_cut"
                ],
                "type": "string"
              },
              "viewer_takeaway": {
                "maxLength": 450,
                "minLength": 1,
                "type": "string"
              },
              "visual_beats": {
                "items": {
                  "additionalProperties": false,
                  "properties": {
                    "action": {
                      "enum": [
                        "establish",
                        "introduce",
                        "compare",
                        "trace",
                        "annotate",
                        "reveal",
                        "reframe",
                        "hold",
                        "consequence"
                      ],
                      "type": "string"
                    },
                    "beat_id": {
                      "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                      "type": "string"
                    },
                    "continuity": {
                      "additionalProperties": false,
                      "properties": {
                        "carry_refs": {
                          "items": {
                            "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                            "type": "string"
                          },
                          "minItems": 0,
                          "type": "array"
                        },
                        "entry": {
                          "enum": [
                            "new_setup",
                            "carry_forward",
                            "reveal_from_prior"
                          ],
                          "type": "string"
                        },
                        "exit": {
                          "enum": [
                            "hard_cut",
                            "match_focus",
                            "same_canvas",
                            "dissolve"
                          ],
                          "type": "string"
                        },
                        "group_id": {
                          "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                          "type": "string"
                        },
                        "reason": {
                          "maxLength": 350,
                          "minLength": 1,
                          "type": "string"
                        }
                      },
                      "required": [
                        "group_id",
                        "carry_refs",
                        "entry",
                        "exit",
                        "reason"
                      ],
                      "type": "object"
                    },
                    "cue": {
                      "additionalProperties": false,
                      "properties": {
                        "occurrence": {
                          "maximum": 100,
                          "minimum": 0,
                          "type": "integer"
                        },
                        "phrase": {
                          "maxLength": 200,
                          "minLength": 1,
                          "type": "string"
                        },
                        "section_id": {
                          "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                          "type": "string"
                        }
                      },
                      "required": [
                        "section_id",
                        "phrase",
                        "occurrence"
                      ],
                      "type": "object"
                    },
                    "focus_move": {
                      "enum": [
                        "none",
                        "subject_to_subject",
                        "detail_to_overview",
                        "overview_to_detail",
                        "follow_path",
                        "static"
                      ],
                      "type": "string"
                    },
                    "focus_ref": {
                      "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                      "type": "string"
                    },
                    "hold_policy": {
                      "enum": [
                        "readable",
                        "narration_aligned",
                        "editorial_pause"
                      ],
                      "type": "string"
                    },
                    "relationships": {
                      "items": {
                        "additionalProperties": false,
                        "properties": {
                          "from_ref": {
                            "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                            "type": "string"
                          },
                          "relation": {
                            "enum": [
                              "left_of",
                              "right_of",
                              "foreground_of",
                              "background_of",
                              "inside",
                              "overlaps",
                              "points_to",
                              "follows",
                              "compares_to",
                              "same_subject_as"
                            ],
                            "type": "string"
                          },
                          "to_ref": {
                            "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                            "type": "string"
                          }
                        },
                        "required": [
                          "from_ref",
                          "to_ref",
                          "relation"
                        ],
                        "type": "object"
                      },
                      "minItems": 0,
                      "type": "array"
                    },
                    "section_ref": {
                      "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                      "type": "string"
                    },
                    "shot_goal": {
                      "maxLength": 350,
                      "minLength": 1,
                      "type": "string"
                    },
                    "source_claim_refs": {
                      "items": {
                        "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                        "type": "string"
                      },
                      "minItems": 0,
                      "type": "array"
                    },
                    "staging": {
                      "items": {
                        "additionalProperties": false,
                        "properties": {
                          "after_ref": {
                            "anyOf": [
                              {
                                "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                                "type": "string"
                              },
                              {
                                "type": "null"
                              }
                            ]
                          },
                          "motion_hint": {
                            "enum": [
                              "none",
                              "subtle_push",
                              "parallax",
                              "stagger",
                              "line_draw",
                              "wipe",
                              "cut",
                              "track",
                              "zoom"
                            ],
                            "type": "string"
                          },
                          "operation": {
                            "enum": [
                              "enter",
                              "hold",
                              "highlight",
                              "exit",
                              "reposition",
                              "focus",
                              "draw_path",
                              "reveal_mask"
                            ],
                            "type": "string"
                          },
                          "priority": {
                            "maximum": 20,
                            "minimum": 1,
                            "type": "integer"
                          },
                          "ref": {
                            "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
                            "type": "string"
                          }
                        },
                        "required": [
                          "ref",
                          "operation",
                          "after_ref",
                          "motion_hint",
                          "priority"
                        ],
                        "type": "object"
                      },
                      "minItems": 1,
                      "type": "array"
                    }
                  },
                  "required": [
                    "beat_id",
                    "section_ref",
                    "cue",
                    "action",
                    "focus_ref",
                    "shot_goal",
                    "source_claim_refs",
                    "relationships",
                    "staging",
                    "focus_move",
                    "hold_policy",
                    "continuity"
                  ],
                  "type": "object"
                },
                "minItems": 1,
                "type": "array"
              },
              "visual_purpose": {
                "maxLength": 450,
                "minLength": 1,
                "type": "string"
              }
            },
            "required": [
              "visual_purpose",
              "viewer_takeaway",
              "on_screen_text",
              "reveal_plan",
              "asset_slots",
              "camera_intent",
              "composition_intent",
              "emotional_tone",
              "layout_variant_hint",
              "duration_policy",
              "transition_intent",
              "historical_map_requirement_id",
              "visual_beats",
              "reuse_setup_id"
            ],
            "type": "object"
          },
          "intent": {
            "enum": [
              "geography",
              "person",
              "evidence",
              "route",
              "chronology",
              "number",
              "quote",
              "consequence"
            ],
            "type": "string"
          },
          "preferred_template": {
            "enum": [
              "T01",
              "T02",
              "T03",
              "T04",
              "T05",
              "T06",
              "T07",
              "T08",
              "T09",
              "T10"
            ],
            "type": "string"
          },
          "requirement_refs": {
            "items": {
              "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
              "type": "string"
            },
            "minItems": 0,
            "type": "array"
          },
          "section_refs": {
            "items": {
              "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
              "type": "string"
            },
            "minItems": 1,
            "type": "array"
          },
          "setup_id": {
            "pattern": "^[A-Za-z][A-Za-z0-9_-]{2,63}$",
            "type": "string"
          }
        },
        "required": [
          "setup_id",
          "section_refs",
          "intent",
          "requirement_refs",
          "claim_refs",
          "direction"
        ],
        "type": "object"
      },
      "minItems": 1,
      "type": "array"
    }
  },
  "required": [
    "schema_version",
    "project",
    "sections",
    "claims",
    "asset_requirements",
    "visual_setups",
    "authoring_source"
  ],
  "title": "StoryPackage.v1",
  "type": "object"
}
~~~