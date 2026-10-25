"""Windows-native independent verifier for actual Chromium motion output."""
import argparse,copy,hashlib,json,struct,tempfile
from pathlib import Path

def need(ok,msg):
    if not ok: raise ValueError("B2_MOTION_EVIDENCE_INVALID: "+msg)

def png(path,sha):
    need(isinstance(path,str) and bool(path),"missing PNG")
    f=Path(path)
    need(f.is_file(),"missing PNG bytes: "+str(f))
    with f.open("rb") as stream: head=stream.read(24)
    need(head[:16]==b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR","invalid PNG signature")
    need(struct.unpack(">II",head[16:24])==(1920,1080),"not a native 1920x1080 frame")
    need(isinstance(sha,str) and hashlib.sha256(f.read_bytes()).hexdigest()==sha,
         "PNG SHA256 mismatch: "+str(f))

def validate(registry,sem,phase):
    names=[p["preset_id"] for p in registry["presets"]]
    need(len(names)==len(set(names))==19,"registry contains duplicate/missing preset")
    need(sem.get("status")==phase.get("status")=="PASS","motion ledgers disagree or fail")
    need(sem.get("scope")==phase.get("scope")=="SYNTHETIC_CHROMIUM_MECHANICS_ONLY","wrong evidence scope")
    need(sem.get("registryCount")==phase.get("registryCount")==19,"registry count mismatch")
    need(phase.get("source_authorization_verified") is False,"synthetic approval spoof")
    rows=sem.get("rows")
    need(isinstance(rows,list) and [r.get("preset_id") for r in rows]==names,"19 ledger rows do not match registry")
    need(sem.get("semanticPassCount")==19,"semantic pass count mismatch")
    cases=phase.get("cases")
    need(isinstance(cases,list) and cases,"no executed phase records")
    for row in rows:
        name=row["preset_id"]
        need(row.get("status")=="PASS" and row.get("mechanics_verified") is True,name+": failed mechanics")
        need(row.get("source_authorization_verified") is False and
             row.get("production_rights_status")=="NOT_VERIFIED_BY_SYNTHETIC_TEST",
             name+": synthetic evidence cannot confer live approval")
        need(not row.get("failure_reasons"),name+": PASS has dangling failures")
        flags=row.get("mechanism_assertions",{})
        for flag in ("validChromiumFrames","distinctActualPixels","negativeWrongSpaceBlocked",
                     "prestartInvariant","eventSpecificROICausal","presetSpecificProof"):
            need(flags.get(flag) is True,name+": missing "+flag)
        evidence=row.get("evidence")
        need(isinstance(evidence,list) and evidence==[e for e in cases if e.get("preset")==name],
             name+": phase ledger diverges from semantic proof")
        frames=[e for e in evidence if isinstance(e.get("frame"),int) and "path" in e]
        need(len(frames)>=3 and row.get("actual_png_paths")==[f["path"] for f in frames],
             name+": missing frame series")
        for e in frames:
            png(e["path"],e.get("sha256"))
            need(isinstance(e.get("pixelHash"),str) and len(e["pixelHash"])==64,name+": missing pixel digest")
        need(any(e.get("negativeAssertion")=="wrong_transform_space" and e.get("typedRejection") is True
                 for e in evidence),name+": no wrong-space typed rejection")
        counter=[e for e in evidence if e.get("counterfactual")=="same_frame_event_removed"
                 and type(e.get("changedROIPixels")) is int and e["changedROIPixels"]>0]
        need(bool(counter),name+": no measured same-frame causal ROI")
        for e in counter:
            if "positivePath" in e or "controlPath" in e:
                png(e.get("positivePath"),e.get("positiveSha256"))
                png(e.get("controlPath"),e.get("controlSha256"))
                need(e["positiveSha256"]!=e["controlSha256"],name+": on/off frame identical")
        for e in evidence:
            if e.get("preStartApplicability")=="RENDERED_EVENT_ON_EQUALS_RECOMPILED_OFF":
                need(e.get("preStartPixelMatch") is True,name+": pre-event pixels not proven")
                png(e.get("baselinePath"),e.get("baselineSha256"))
                png(e.get("positivePath"),e.get("positiveSha256"))
                need(e["baselineSha256"]==e["positiveSha256"],
                     name+": pre-event compositor differs from recompiled control")
    # Two intentional non-preset records belong to this executed owner: the
    # source-preserving crop comparator and genuine FFprobe-checked H264 media.
    # Validate their bytes and reject arbitrary orphan diagnostics.
    auxiliary=[e for e in cases if "preset" not in e]
    crops=[e for e in auxiliary if e.get("kind")=="source_preserving_crop_pixels"]
    movies=[e for e in auxiliary if "mp4" in e]
    need(len(auxiliary)==2 and len(crops)==1 and len(movies)==1,
         "unknown/missing non-preset crop/H264 diagnostic")
    crop=crops[0]
    need(crop.get("source")=="SYNTHETIC_B1_COMPILED_NOT_REAL_RIGHTS" and
         isinstance(crop.get("originalSha256"),str) and len(crop["originalSha256"])==64,
         "crop provenance or original SHA missing")
    png(crop["before"]["path"],crop["before"]["sha256"])
    png(crop["after"]["path"],crop["after"]["sha256"])
    need(crop["before"]["sha256"]!=crop["after"]["sha256"] and
         crop.get("roi",{}).get("changedPixels",0)>0,
         "source-preserving crop does not change actual pixels")
    movie=movies[0]
    video=Path(movie["mp4"])
    need(movie.get("source")=="SYNTHETIC" and video.is_file() and
         hashlib.sha256(video.read_bytes()).hexdigest()==movie.get("sha256"),
         "H264 original bytes/SHA invalid")
    ffprobe=movie.get("ffprobe") or {}
    need(ffprobe.get("codec_name")=="h264" and
         (ffprobe.get("width"),ffprobe.get("height"))==(1920,1080) and
         ffprobe.get("r_frame_rate")=="30/1","native H264/FFprobe evidence invalid")
    need(set(e["preset"] for e in cases if "preset" in e)==set(names),
         "orphan/unknown preset evidence")

def mutations(reg,sem,phase):
    def reject(label,modify):
        a,b=copy.deepcopy(sem),copy.deepcopy(phase)
        modify(a,b)
        try: validate(reg,a,b)
        except ValueError: return
        raise AssertionError("B2_MOTION_MUTATION_NOT_REJECTED: "+label)
    reject("contradictory status",lambda a,b:b.update(status="FAIL"))
    reject("forged PASS row",lambda a,b:a["rows"][0].update(status="FAIL_CONFIRMED"))
    reject("missing registered preset",lambda a,b:a["rows"].pop())
    reject("missing wrong-space negative",lambda a,b:a["rows"][0].update(evidence=[
        e for e in a["rows"][0]["evidence"] if e.get("negativeAssertion")!="wrong_transform_space"]))
    reject("missing event-off ROI",lambda a,b:a["rows"][0].update(evidence=[
        e for e in a["rows"][0]["evidence"] if e.get("counterfactual")!="same_frame_event_removed"]))
    reject("tampered SHA",lambda a,b:a["rows"][0]["evidence"][0].update(sha256="0"*64))
    reject("missing PNG",lambda a,b:a["rows"][0]["evidence"][0].update(path="__missing_motion_fixture__.png"))
    reject("synthetic spoofed approval",lambda a,b:a["rows"][0].update(source_authorization_verified=True))
    prestart=next((e for row in sem["rows"] for e in row["evidence"]
                   if e.get("preStartApplicability")=="RENDERED_EVENT_ON_EQUALS_RECOMPILED_OFF"),None)
    need(prestart is not None,"no compiled pre-event PNG pair available for mutation testing")
    def corrupt_prestart(a,b):
        preset=next(row["preset_id"] for row in sem["rows"] if prestart in row["evidence"])
        for ledger in (a["rows"],):
            record=next(e for row in ledger if row["preset_id"]==preset
                        for e in row["evidence"] if e.get("preStartApplicability")=="RENDERED_EVENT_ON_EQUALS_RECOMPILED_OFF")
            record["baselineSha256"]="0"*64
        case=next(e for e in b["cases"] if e.get("preset")==preset and
                  e.get("preStartApplicability")=="RENDERED_EVENT_ON_EQUALS_RECOMPILED_OFF")
        case["baselineSha256"]="0"*64
    reject("forged compiled pre-event positive/control SHA",corrupt_prestart)
    # Prove altered PNG bytes are rejected even if both ledgers continue to
    # agree on the same original digest and same tampered file location.
    with tempfile.TemporaryDirectory() as directory:
        source=Path(sem["rows"][0]["evidence"][0]["path"])
        corrupt=Path(directory)/"tampered-motion.png"
        pixels=bytearray(source.read_bytes())
        pixels[-8] ^= 1
        corrupt.write_bytes(pixels)
        def tamper_bytes(a,b):
            a["rows"][0]["evidence"][0]["path"]=str(corrupt)
            a["rows"][0]["actual_png_paths"][0]=str(corrupt)
            b["cases"][0]["path"]=str(corrupt)
        reject("actual changed PNG bytes",tamper_bytes)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    reg=json.loads(Path("contracts/registries/motion-presets.v1.json").read_text(encoding="utf-8"))
    root=Path("renderer/.artifacts/renders")
    sem=json.loads((root/"b2-motion-19-presets.json").read_text(encoding="utf-8"))
    phase=json.loads((root/"b2-motion-phases.json").read_text(encoding="utf-8"))
    validate(reg,sem,phase)
    if args.self_test: mutations(reg,sem,phase)
    print("B2_MOTION_CROSS_LEDGER_PASS: 19/19 mechanics, real PNG SHA, ROI and negatives; mutations="+str(args.self_test))
if __name__=="__main__": main()
