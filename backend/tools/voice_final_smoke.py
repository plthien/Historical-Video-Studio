"""Controlled A2-03/04 smoke: real SQLite/FFmpeg, provider audio/timing ONLY as test fixtures."""
import io
import json
import math
import os
import struct
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

from backend.app.jobs.queue import JobQueue
from backend.app.projects.gates import GateService
from backend.app.projects.models import StoryCandidate
from backend.app.projects.storage import ProjectStore
from backend.app.voice.attempts import VoiceService
from backend.app.voice import attempts
from backend.app.voice.workflow import FinalVoiceWorkflow
from backend.app.voice.correction import inspect_wav

ROOT=Path(__file__).resolve().parents[2]


def wav_fixture(seconds:float) -> bytes:
    buf=io.BytesIO()
    with wave.open(buf,"wb") as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(24000)
        out.writeframes(b"".join(struct.pack("<h",int(2900*math.sin(2*math.pi*230*i/24000)))
                                 for i in range(round(seconds*24000))))
    return buf.getvalue()


def setup(directory:Path, narrations:tuple[str,str]|None=None):
    story=json.loads((ROOT/"contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text("utf-8"))
    story["sections"]=story["sections"][:2]
    story["visual_setups"]=story["visual_setups"][:4]
    first, second = narrations or ("History offers a curious puzzle about this place.",
                                    "The next chapter explains what the people decided.")
    story["sections"][0]["narration"]=first
    story["sections"][1]["narration"]=second
    for c in story["claims"]:c["critical"]=False
    store=ProjectStore(directory/"state.sqlite",directory/"media")
    project=story["project"]["project_id"]
    store.create_project(project,"A2 local fixture, not historic approval")
    store.import_story(StoryCandidate.parse(story),0)
    gates=GateService(store)
    first=gates.board(project)[0]
    gates.decide(project,"G1",{"decision":"APPROVED",
                 "candidate_sha256":first["candidate_sha256"],
                 "dependency_fingerprint":first["dependency_fingerprint"],
                 "expected_revision":1})
    queue=JobQueue(store);voice=VoiceService(store,gates,queue)
    final=FinalVoiceWorkflow(store,gates,queue)
    for section,duration in zip(story["sections"],(2.5,3.5)):
        with patch.object(attempts,"_provider_identity",return_value={"model_id":"fixture_only"}):
            voice.enqueue(project,section["section_id"],"kokoro_local","am_adam",1.0,
                          "controlled TTS-boundary fixture",store.revision(project),
                          "offline-"+section["section_id"]+"-voice-request")
            job=voice.process_one(lambda *_:wav_fixture(duration))
        assert job["state"]=="SUCCEEDED",job
    assert gates.board(project)[1]["state"]=="READY_FOR_REVIEW"
    return store,gates,voice,final,project,story


def approval(store,gates,project):
    gate=gates.board(project)[1]
    return gates.decide(project,"G2",{"decision":"APPROVED",
        "candidate_sha256":gate["candidate_sha256"],
        "dependency_fingerprint":gate["dependency_fingerprint"],
        "expected_revision":store.revision(project)})


def mock_alignment(final_audio:dict,transcript:str)->dict:
    words=[]
    for part,offset in zip(transcript.split("\n"),final_audio["section_offsets"]):
        tokens=part.split()
        span=offset["end_sample"]-offset["start_sample"]
        for i,word in enumerate(tokens):
            start=offset["start_sample"]+round(span*(i+0.04)/len(tokens))
            end=offset["start_sample"]+round(span*(i+0.74)/len(tokens))
            words.append({"text":word,"start":start/final_audio["sample_rate"],
                          "end":end/final_audio["sample_rate"],"loss":0.1})
    return {"words":words,"characters":[]}


def run(case:str, mode:str):
    if case=="alignment-elevenlabs" and mode=="live":
        project=os.getenv("HVS_LIVE_PROJECT_ID")
        if not os.getenv("HVS_ELEVENLABS_API_KEY") or not project:
            raise SystemExit("LIVE BLOCKED: require HVS_LIVE_PROJECT_ID with real approved WAV plus ElevenLabs credentials")
        store=ProjectStore(Path(os.getenv("HVS_DB","data/historical-studio.sqlite")),
                           Path(os.getenv("HVS_MEDIA","data/media")))
        final=FinalVoiceWorkflow(store,GateService(store),JobQueue(store))
        job=final.process_one()
        status=final.status(project)
        if not job or job["state"]!="SUCCEEDED" or not status["g4_ready_dependency"]:
            raise SystemExit("LIVE_FAIL: No provider-verified current word map")
        print("alignment-elevenlabs: LIVE_PASS",job["job_id"])
        return
    if mode!="local" or case=="alignment-elevenlabs":
        raise SystemExit("Use --mode local for synthetic A2 smoke or --mode live on existing real WAV")
    with tempfile.TemporaryDirectory() as folder:
        store,gates,voice,workflow,project,story=setup(Path(folder))
        result=approval(store,gates,project)
        assert result["job_id"]
        assembled=workflow.process_one()
        assert assembled["state"]=="SUCCEEDED",assembled
        status=workflow.status(project);audio=status["final_audio"]
        assert audio and audio["section_offsets"][0]["end_sample"]==audio["section_offsets"][1]["start_sample"]
        assert inspect_wav(store.get_artifact(audio["audio_sha256"]))["sample_count"]==audio["duration_samples"]
        if case=="final-wav":
            assert status["g4_ready_dependency"] is False
            print("final-wav: LOCAL_PASS exact immutable samples/offsets, synthetic TTS audio boundary")
            return
        blocked=workflow.process_one(lambda *_:{"words":[]})
        assert blocked["state"]=="FAILED_TERMINAL"
        assert not workflow.status(project)["g4_ready_dependency"]
        workflow.retry_alignment(project,store.revision(project),audio["audio_sha256"],
                                 audio["transcript_sha256"],"retry-after-malformed-mock")
        done=workflow.process_one(lambda wav,text:mock_alignment(audio,text))
        assert done["state"]=="SUCCEEDED",done
        status=workflow.status(project)
        assert status["g4_ready_dependency"] and len(status["word_map"]["words"])>1
        assert FinalVoiceWorkflow(ProjectStore(store.database,store.artifacts.root),
                   GateService(store),JobQueue(store)).status(project)["g4_ready_dependency"]
        if case=="voice-ui":
            from fastapi.testclient import TestClient
            from backend.app.api.server import create_app
            with TestClient(create_app(store.database,store.artifacts.root)) as client:
                response=client.get("/api/v1/projects/"+project+"/voice/alignment")
                assert response.status_code==200 and response.json()["g4_ready_dependency"]
                wav=client.get("/api/v1/projects/"+project+"/voice/audio/"+audio["audio_sha256"])
                assert wav.status_code==200 and inspect_wav(wav.content)["sample_count"]==audio["duration_samples"]
        print(case+": LOCAL_PASS; SQLite/FFmpeg genuine, TTS/alignment controlled MOCK BOUNDARY only")
