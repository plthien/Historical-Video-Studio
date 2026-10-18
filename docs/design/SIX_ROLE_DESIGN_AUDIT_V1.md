# SIX-ROLE DESIGN AUDIT V1.0
## Independent design review of `MASTER_DESIGN_SPECIFICATION_V1.md`

**Thời điểm:** 19/10/2026  
**Review scope:** Product & Architecture Specification + Visual System & Template Specification cho **ứng dụng mới**, không audit implementation cũ.  
**Inputs reviewed:** Master spec, video mẫu `1015.mp4` (FFprobe + 5s sampled contact sheets), user G-Labs webhook contract, Remotion/Motion Prompt/ElevenLabs/Commons primary docs.  
**Verdict:** **CONDITIONAL DESIGN PASS**; chưa có pilot chạy thật. Đây là **self-review có checklist và dấu vết sửa thiết kế**, không phải independent external expert assessment hoặc real acceptance test.

## 1. Executive verdict

**Kết quả thiết kế:** Có thể giao implement **M0 contracts + M1 end-to-end pilot** với giới hạn được nêu rõ. Không được khẳng định đã có sản phẩm chạy, auto-production PASS, quality parity PASS hoặc Forced Alignment tiếng Việt PASS.

**P0 external blockers trước khi tuyên bố hệ thống vận hành:**
- `P0-01`: Test ElevenLabs Forced Alignment với **ngôn ngữ production thực tế**, đặc biệt tiếng Việt (tài liệu liệt kê 29 ngôn ngữ, không thấy Vietnamese).
- `P0-02`: Test thực tế G-Labs MAX webhook trên máy Windows: health, image generate, poll, save, scoped cancel/quota failure.
- `P0-03`: Source/rights/period map cho tối thiểu hai pilot phải qua G3 user approval; không có ảnh/bản đồ thực tế nào đã được phê duyệt bởi đợt audit này.
- `P0-04`: Frame-based Remotion production pilot, browser/export parity, typography và 2 câu chuyện khác nhau chưa kiểm chứng.

## 2. Role audit — Director / Visual Storytelling

**Primary question:** Nếu lời kể giải thích sự kiện phức tạp, hệ thống có chọn **loại hình thị giác đúng** để giúp người xem hiểu nguyên nhân, thay vì chỉ thay ảnh và zoom?

| ID | Observation / defect risk | Sev | Repair / contract | Status |
|---|---|---|---|---|
| DIR-01 | ChatGPT cue list có thể buộc 1 beat → 1 image, video thành slideshow | High | §11 + §15: persistent setups, progressive layer reveals, semantic grouping | Spec repaired |
| DIR-02 | Motion nhanh/đẹp nhưng sai vai trò (ví dụ territory map cho câu nói về danh tính) | High | §11 semantic matching + §13 intent constraints | Spec repaired |
| DIR-03 | Không có build-up/aftermath và shot hold khiến người xem không kịp hiểu | High | §11 causal grammar + §14 hold policies, director pilot review | Needs pilot |
| DIR-04 | Cảnh mới quá giống nhau sau 10 phút dù đổi data | Medium | §13 template variants 2–3/layout, two-topic acceptance test | Needs pilot |
| DIR-05 | Bản đồ/ảnh không đúng ý nghĩa lịch sử | Critical | §9 map/source ownership + G1/G3/G4 approval | Requires human evidence |

**Director verdict:** **Conditional PASS**. Cần xem đủ pilot tại 0%, 25%, 50%, 75%, 100% và đoạn continuous playback (không chỉ contact sheets). Đánh giá: hiểu được ai/ở đâu/cái gì thay đổi, layer continuity, exposition vs emotional emphasis, không lặp motif sai ngữ cảnh.

## 3. Role audit — Video Editor

**Primary question:** Voice, timing, transitions và re-edit có tạo video liên tục hay khiến cảnh nối bị cắt, trùng, chậm?

| ID | Observation / defect risk | Sev | Repair / contract | Status |
|---|---|---|---|---|
| EDT-01 | Sửa một đoạn TTS làm trượt toàn bộ timeline | Critical | §2.5 + §8 final WAV SHA and word map revision; replay downstream compile | Spec repaired |
| EDT-02 | Chuyển cảnh overlap làm mất câu hoặc ảnh đang nhắc tới | High | §15 compiler transition accounting + §16 shared composition | Needs playback |
| EDT-03 | Scene quá ngắn khiến title vừa hiện đã mất | High | §11 readability, §14 entrance/hold timing, §15 validator | Needs golden fixtures |
| EDT-04 | Sửa crop/photo một scene phải regenerate voice/asset cả video | High | §2.5 selective dependency invalidation | Spec repaired |
| EDT-05 | BGM/SFX che tiếng narration; tiếng đầu/đuôi bị cắt | High | §8 Audio QC, §16 QC; missing explicit BGM mix limit default | Open M1 decision |

**Editor verdict:** **Conditional PASS**. **Required M1 repair detail:** document BGM/SFX ducking/loudness and tail behavior in audio contract before implementing soundtrack. V1 can render **voice-only**, and MAY add licensed BGM later; do not block voice-only pilot because BGM rule not decided.

## 4. Role audit — Motion Designer

**Primary question:** Có thể đạt visual grammar của mẫu bằng các thành phần deterministic chất lượng cao không?

| ID | Observation / defect risk | Sev | Repair / contract | Status |
|---|---|---|---|---|
| MOT-01 | Motion Prompt 120 samples bị hiểu sai thành 120 Remotion production components | High | §1/§4/§14 clarify port-not-package and MIT attribution | Spec repaired |
| MOT-02 | Khung chữ nhỏ/thừa text, font fallback đặc biệt dấu tiếng Việt | High | §12 font/palette/safe area + §15 measured text; sample long-label test | Needs pilot |
| MOT-03 | Cutout halo/mất tóc hoặc “giấy” texture flicker do random | High | §9 variant QC + §11 deterministic frame, §13 photo-card treatment fallback | Needs implementation |
| MOT-04 | Motion camera/route overlay đi khác world transform | High | §9.6 map geometry/date validation; §14 preset constraints | Needs unit visuals |
| MOT-05 | Dolly-in trên một ảnh 2D bị marketing như hiệu ứng camera 3D vật lý | Medium | §14 labels explicitly `simulated 2D camera push` | Spec repaired |
| MOT-06 | Chỉ có 1 layout mỗi template gây lặp motif | High | §13 requires 2–3 layout variants + two topics | Needs implementation |

**Motion Design verdict:** **Conditional PASS**. Không hứa đạt giống mẫu chỉ bằng ghi preset ID. Required deliverable: frame sheets for each template's entrance/hold/exit, boundaries, first/last-frame parity, multiple text lengths, verified font/glyph coverage.

## 5. Role audit — Software Architect

**Primary question:** Có đảm bảo không vendor lock-in TTS, giữ trạng thái/revision đáng tin cậy, và không cho model JSON thực thi code?

| ID | Observation / defect risk | Sev | Repair / contract | Status |
|---|---|---|---|---|
| ARC-01 | ElevenLabs TTS adapter kiêm forced alignment, khiến Kokoro phụ thuộc chéo | Critical | §8 separates `TTSAdapter` and `AlignmentAdapter` | Spec repaired |
| ARC-02 | Imported ChatGPT JSON chứa JSX/JS/URL/path và trực tiếp điều khiển renderer | Critical | §6 strict schemas, safe registry IDs, no executable payload | Spec repaired |
| ARC-03 | Provider webhook results only live as transient URL/task id | High | §5 durable provider ledger, §9.7 download file/hash local | Spec repaired |
| ARC-04 | Approve stale revision, job cũ publish sau restart | Critical | §2.5 + §5 immutable approvals, leases, SHA/publish fencing | Needs tests |
| ARC-05 | Renderer Player và MP4 dùng hai implementations dẫn tới visual drift | High | §4 and §16 single Remotion composition + parity | Spec repaired |
| ARC-06 | Pipeline thay đổi là đòi rewrite kiến trúc cũ | High | §1 clean new-build explicit no legacy migration | Spec repaired |
| ARC-07 | Một lượt ChatGPT import nhưng chưa có **machine-validated complete JSON Schema** | High | §6 defines object inventory and import rules; M0 must freeze actual schema and fixtures | **Open M0**, not allowed to skip |

**Architecture verdict:** **PASS for architectural direction, CONDITIONAL for engineering kickoff.** No source-code generator at render time. Critical remaining technical dependency: actual versioned JSON schema, typed DTO generation, error catalog, job/approval transition tables.

## 6. Role audit — QA Engineer

**Primary question:** Có phát hiện được sự không đúng lịch sử, sai bản quyền, lỗi timing, provider failure và silent fallback hay không?

| ID | Observation / defect risk | Sev | Repair / contract | Status |
|---|---|---|---|---|
| QA-01 | Official FA language list lacks Vietnamese but sample contains Vietnamese text | Critical | §8.4 `BLOCKED_LANGUAGE_SUPPORT`, real test required | **External P0 open** |
| QA-02 | Người dùng bấm Managed Fallback = hệ thống auto coi đã approve ảnh | Critical | §2.4 separate candidate generation authorization from G3 asset approval | Spec repaired |
| QA-03 | Archival photo có rights nhưng không chắc đúng sự kiện | Critical | §9 evidence and rights separate; G3 human | Spec repaired |
| QA-04 | Một map năm 1914 được render từ hiện tại vì chỉ có geodata mới | Critical | §9.6 era geometry validation and human review | Spec repaired |
| QA-05 | Same JSON compiler produces non-deterministic frames | High | §15 canonical hash and Appx N18; no randomness | Needs golden test |
| QA-06 | Render thành công nhưng blank frames/hidden text/missing audio | High | §16 QC + Appx negative tests, inspect sample MP4 | Needs pilot |
| QA-07 | G-Labs 429, cancel and session loss lead to infinite retry/cost | High | §5 + §9.7 capped backoff, cancel per task | Needs live test |
| QA-08 | Weakness: QC cannot algorithmically certify historical truth | High | §9 source evidence + G1/G3 and G5 review gates | Risk acknowledged |

**QA verdict:** **Conditional PASS**, *not production verified*. Run full negative test matrix (N01–N24), integration tests on Windows, plus audio/provider language matrix. Document gate pass requires actual evidence and exact source SHA.

## 7. Role audit — Operator / User Experience

**Primary question:** Dù chạy local một người, 5 gate có rõ ràng, nhanh và không phiền không? Khi lỗi, operator có biết làm gì tiếp không?

| ID | Observation / defect risk | Sev | Repair / contract | Status |
|---|---|---|---|---|
| OPS-01 | 5 gate thành quá nhiều Approve từng asset/beat | High | §3 and §10 batch review, exception queue, 5 phase-level approvals only | Spec repaired |
| OPS-02 | Unknown source asset khiến tool tự tạo ảnh rồi giấu fallback | Critical | §2.4 two explicit options, G3 after preview | Spec repaired |
| OPS-03 | Async Click UI không phản hồi vài giây; operator spam jobs | High | §3 immediate processing indicator, §5 idempotent jobs and per-task cancel | Spec repaired |
| OPS-04 | G-Labs chạy nhưng bị hết quota hoặc server tắt | High | §5 + §9.7 health, status, error/next action, bounded retries | Needs live test |
| OPS-05 | Raw JSON too technical, operator phải sửa file | High | §3 bounded visual editor and targeted repair prompt | Needs UX prototype |
| OPS-06 | License/source requirements khó xử lý với 30 ảnh/video | High | §10 source inspector, batch with exceptions; template credit export | Needs workload test |
| OPS-07 | Windows 1-click startup vs node/python setup | High | §1 product goal and §16 render; one-click package M4 | Open implementation |

**Operator verdict:** **Conditional PASS**. M0 UI prototype acceptance: operator should complete G1→G5 with mouse/keyboard and no JSON manual edit, terminal, or provider task-ID copying. For blocked jobs, the UI must present concrete recovery buttons.

## 8. Six-role cross-cutting resolution board

| ID | Severity | Decided behavior | Master reference | Follow-up acceptance |
|---|---|---|---|---|
| X01 | P0 | No unsupported-language word timings | §8.4 / §19 R01 | English/vi real ElevenLabs FA test |
| X02 | P0 | No silent or unapproved archival fallback | §2.4 / §10 | Gate3 dual-option behavioral E2E |
| X03 | P0 | No auto-certification historical truth/rights | §6 + §9 | Source evidence manual approve pilot |
| X04 | P1 | Same components work for two different topics | §13/§17 | A/B pilots no per-video JS edits |
| X05 | P1 | Preserve unchanged upstream on local visual edit | §2.5/§16 | selective invalidation test N17 |
| X06 | P1 | Render reproducible and editor looks like MP4 | §15/§16 | golden frames/player parity |
| X07 | P1 | Provider request/cancel consistent on Windows | §5/§9 | real task targeted cancel test |
| X08 | P1 | Visual pacing and restrained motion, not motion-for-motion's-sake | §11/§14 | editorial playback review |

## 9. Scope gaps not “fixed” by mere prose

The specification alone **does not** contain final JSON Schema files, wireframes with executable controls, implementation code, actual archived photo license reviews, local G-Labs auth access, or live ElevenLabs/Kokoro clips. Those belong to M0–M4 delivery and cannot be claimed PASS today.

The **design quality** is sufficient for controlled M0. Before implementation M1, M0 must add:
- Machine-readable `StoryPackage`, `VisualBlueprint`, `AssetRequirement`, `CompiledTimeline`, `ApprovalRecord` schemas + positive/negative examples.
- Actor/state/event transitions including stale approval/CAS behavior.
- UI wireflow for all five gates plus missing-archive modal with two options.
- Template cards with three visual states (entry/hold/exit) for the pilot five.
- Provider test scripts that **check**, not assume, language/limits and image webhook account capabilities.

## 10. Recommendation

**Next action:** Approve architecture as **Design V1 Candidate**, then commission **M0 Contract & UX Freeze** as separate, bounded implementation/design artifact. Do **not** start full automatic long-form production or promise fully autonomous facts/licensing. M1 proves a 60–90s end-to-end pilot with real audio, actual rights-cleared archives and five templates. M2 proves opt-in G-Labs fallback; M3 adds editor/template breadth; M4 stress-tests full 4–6 minute video.

**Final audit status:** **CONDITIONAL DESIGN PASS / IMPLEMENTATION NOT STARTED.**