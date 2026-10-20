import {useCallback,useEffect,useState} from "react";
import {api,ApiError,type ProjectInfo,type StoryView} from "../../api/client";
import {voiceApi,type AlignmentStatus,type SectionHistory,type VoiceAttempt} from "../../api/voice";

type Params={provider:"kokoro_local"|"elevenlabs_tts";voice:string;speed:string;wpm:string};
const defaultParams=():Params=>({provider:"kokoro_local",voice:"",speed:"",wpm:""});
const errText=(e:unknown)=>e instanceof ApiError?e.problem.code+": "+e.problem.remediation:
  e instanceof Error?e.message:"Unknown audio error";
export function VoiceStudio({project,story,onRefresh}:{
  project:ProjectInfo;story:StoryView|null;onRefresh:()=>Promise<void>;
}){
  const [hist,setHist]=useState<Record<string,SectionHistory>>({});
  const [settings,setSettings]=useState<Record<string,Params>>({});
  const [status,setStatus]=useState<AlignmentStatus|null>(null);
  const [busy,setBusy]=useState<string|null>(null);
  const [job,setJob]=useState<string|null>(null);
  const [jobKind,setJobKind]=useState<"assembly"|"alignment"|"synthesis"|null>(null);
  const [notice,setNotice]=useState<string|null>(null);
  const [error,setError]=useState<string|null>(null);
  const sections=story?.story.sections??[];
  const g1=project.gates.find(g=>g.gate_id==="G1");
  const g2=project.gates.find(g=>g.gate_id==="G2");
  const read=useCallback(async()=>{
    const rows=await Promise.all(sections.map(async s=>
      [s.section_id,await voiceApi.attempts(project.project_id,s.section_id)] as const));
    const alignment=await voiceApi.status(project.project_id);
    setHist(Object.fromEntries(rows));setStatus(alignment);
  },[project.project_id,story?.candidate_sha256]);
  useEffect(()=>{void read().catch(e=>setError(errText(e)));},[read,project.project_revision]);
  useEffect(()=>{
    if(!job)return;
    let closed=false;
    async function poll(){
      try{
        const current=await voiceApi.job(job!);
        if(closed||current.state==="QUEUED"||current.state==="RUNNING")return;
        if(current.state==="SUCCEEDED"&&jobKind==="assembly"){
          const next=await voiceApi.status(project.project_id);
          const align=next.alignment_job;
          if(align&&(align.state==="QUEUED"||align.state==="RUNNING")){
            setJobKind("alignment");setJob(align.job_id);setBusy("Aligning final WAV…");
            await read();await onRefresh();return;
          }
          if(align&&align.state!=="SUCCEEDED")setError(align.error_code||align.state);
        }else if(current.state!=="SUCCEEDED")setError(current.error_code||current.state);
        else setNotice("Operation succeeded; durable media status refreshed.");
        setJob(null);setJobKind(null);setBusy(null);
        await read();await onRefresh();
      }catch(e){if(!closed){setJob(null);setBusy(null);setError(errText(e));}}
    }
    void poll();const interval=setInterval(()=>void poll(),1250);
    return ()=>{closed=true;clearInterval(interval);};
  },[job,jobKind,read,onRefresh,project.project_id]);
  function update(id:string,values:Partial<Params>){
    setSettings(old=>({...old,[id]:{...(old[id]||defaultParams()),...values}}));
  }
  async function run(label:string,perform:()=>Promise<string|void>){
    if(busy)return;
    setBusy(label);setError(null);setNotice(null);
    let queued=false;
    try{
      const id=await perform();
      if(id){
        const kind=label.startsWith("Approving")?"assembly":
                   label.startsWith("Aligning")?"alignment":"synthesis";
        setJobKind(kind);setJob(id);queued=true;
        if(kind==="assembly")setBusy("Assembling final WAV…");
      }
      else setNotice(label+" completed and persisted.");
      await read();await onRefresh();
    }catch(e){setError(errText(e));
      if(e instanceof ApiError&&e.status===409)await onRefresh().catch(()=>{});
    }finally{if(!queued)setBusy(null);}
  }
  function regenerate(id:string){
    const p=settings[id]||defaultParams();
    if(!p.voice.trim()||!p.speed.trim()||!Number.isFinite(Number(p.speed))){
      setError("Voice ID and explicit speed are required.");return;
    }
    void run("Regenerating "+id+"…",async()=>{
      const response=await voiceApi.regenerate(project.project_id,id,{
        expected_revision:project.project_revision,provider_id:p.provider,voice_id:p.voice,
        speed:Number(p.speed),reason:"Operator section regeneration"},crypto.randomUUID());
      return response.job_id;
    });
  }
  function correction(id:string,a:VoiceAttempt){
    const target=settings[id]?.wpm||"";
    if(!target.trim()||!Number.isFinite(Number(target))){setError("Enter a target WPM.");return;}
    void run("Correcting "+id+"…",async()=>{
      await voiceApi.correct(project.project_id,id,{expected_revision:project.project_revision,
        attempt_id:a.attempt_id,method:"ffmpeg_tempo",target_wpm:Number(target)},crypto.randomUUID());
    });
  }
  function restore(id:string,a:VoiceAttempt){
    void run("Restoring "+id+"…",async()=>{
      await voiceApi.restore(project.project_id,id,{expected_revision:project.project_revision,
        attempt_id:a.attempt_id,expected_audio_sha256:a.audio_sha256,
        reason:"Operator selected exact compatible previous attempt"},crypto.randomUUID());
    });
  }
  function approve(){
    if(!g2?.candidate_sha256||!g2.dependency_fingerprint)return;
    void run("Approving selection…",async()=>{
      const result=await api.decide(project.project_id,"G2",{decision:"APPROVED",
        candidate_sha256:g2.candidate_sha256!,dependency_fingerprint:g2.dependency_fingerprint!,
        expected_revision:project.project_revision,comment:"Operator approves voice selection",
        affected_ids:[]},crypto.randomUUID());
      return result.job_id;
    });
  }
  function retry(){
    if(!status?.final_audio)return;
    void run("Aligning final WAV…",async()=>{
      const final=status.final_audio!;
      const result=await voiceApi.retry(project.project_id,{
        expected_revision:project.project_revision,audio_sha256:final.audio_sha256,
        transcript_sha256:final.transcript_sha256},crypto.randomUUID());
      return result.job_id;
    });
  }
  return <div className="voice-studio">
    <p>G1: <strong>{g1?.state||"DRAFT"}</strong> · G2: <strong>{g2?.state||"DRAFT"}</strong></p>
    {busy&&<p role="status" aria-live="polite">{busy}</p>}
    {error&&<p className="notice error" role="alert">{error}</p>}
    {notice&&<p className="notice success" role="status">{notice}</p>}
    {!story&&<p>Import a StoryPackage first.</p>}
    {sections.map(section=>{
      const p=settings[section.section_id]||defaultParams();
      const data=hist[section.section_id];
      const selected=data?.attempts.find(a=>a.selected);
      const words=section.narration.trim().split(/\s+/).length;
      return <article key={section.section_id} className="panel" aria-label={"Voice section "+section.section_id}>
        <h3>{section.section_id}</h3><p>{section.narration}</p>
        <p>{selected?"Selected "+selected.voice_id+" · "+selected.duration_seconds.toFixed(2)+"s · "+
          Math.round(words*60/selected.duration_seconds)+" WPM · "+selected.sample_rate+" Hz · "+
          (selected.compatible_source?"Current":"Historical incompatible"):"No selected audio"}</p>
        {selected&&<audio controls preload="none" src={voiceApi.audio(project.project_id,selected.audio_sha256)}/>}
        <div className="voice-fields">
          <label>Provider <select value={p.provider} disabled={!!busy} onChange={e=>update(section.section_id,{provider:e.target.value as Params["provider"]})}>
            <option value="kokoro_local">Kokoro</option><option value="elevenlabs_tts">ElevenLabs</option></select></label>
          <label>Voice ID <input aria-label={"Voice ID "+section.section_id} value={p.voice}
            onChange={e=>update(section.section_id,{voice:e.target.value})} disabled={!!busy}/></label>
          <label>Speed <input aria-label={"Speed "+section.section_id} value={p.speed}
            placeholder="Explicit synthesis speed" onChange={e=>update(section.section_id,{speed:e.target.value})} disabled={!!busy}/></label>
          <button disabled={!!busy||g1?.state!=="APPROVED"} onClick={()=>regenerate(section.section_id)}>Regenerate</button>
          <label>Target WPM <input aria-label={"Target WPM "+section.section_id} value={p.wpm}
            placeholder="Explicit correction WPM" disabled={!!busy}
            onChange={e=>update(section.section_id,{wpm:e.target.value})}/></label>
          <button disabled={!!busy||!selected?.compatible_source||g1?.state!=="APPROVED"}
            onClick={()=>selected&&correction(section.section_id,selected)}>Correction (FFmpeg)</button>
        </div>
        <details><summary>Attempt history ({data?.attempts.length||0})</summary>
          {data?.attempts.map(a=><div className="voice-attempt" key={a.attempt_id}>
            <p>{a.attempt_id} · {a.kind} · {a.voice_id} · {a.duration_seconds.toFixed(2)}s ·
              {a.compatible_source?"Current source":"Historical/stale"}</p>
            <audio controls preload="none" src={voiceApi.audio(project.project_id,a.audio_sha256)}/>
            {!a.selected&&<button disabled={!!busy||!a.compatible_source||g1?.state!=="APPROVED"}
              onClick={()=>restore(section.section_id,a)}>Restore previous</button>}
          </div>)}
        </details>
      </article>;
    })}
    {story&&<section className="panel" aria-label="G2 final voice approval">
      <h3>Final selection &amp; ElevenLabs forced alignment</h3>
      <p>G2: {g2?.state} · {g2?.blockers.join("; ")||"No blockers"}</p>
      <button disabled={!!busy||g2?.state!=="READY_FOR_REVIEW"} onClick={approve}>Approve G2</button>
      <p>Assembly: <strong>{status?.assembly_job?.state||"NOT_STARTED"}</strong> {status?.assembly_job?.error_code}</p>
      <p>Alignment: <strong>{status?.alignment_job?.state||"NOT_STARTED"}</strong> {status?.alignment_job?.error_code}</p>
      {status?.final_audio&&<><p>Final WAV: {status.final_audio.duration_samples} samples at {status.final_audio.sample_rate} Hz</p>
        <audio controls preload="none" src={voiceApi.audio(project.project_id,status.final_audio.audio_sha256)}/></>}
      {status?.word_map&&<p>WordTimingMap: {status.word_map.words.length} provider-derived words, {status.word_map.anomalies.length} anomalies</p>}
      <p>G4 dependency: {status?.g4_ready_dependency?"READY":"BLOCKED — valid forced alignment required"}</p>
      {status?.final_audio&&status.alignment_job&&["FAILED_TERMINAL","FAILED_RETRYABLE","BLOCKED_REVIEW"].includes(status.alignment_job.state)&&
        <button disabled={!!busy} onClick={retry}>Retry forced alignment (technical only)</button>}
    </section>}
  </div>;
}
