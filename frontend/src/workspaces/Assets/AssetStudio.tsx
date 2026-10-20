import {useCallback,useEffect,useState} from "react";
import {assetApi,type Requirement,type AssetCandidate,type AssetReview} from "../../api/assets";
import {api,type Gate} from "../../api/client";
import {ProviderSettings} from "../Settings/ProviderSettings";
export function AssetStudio({projectId,onRefresh}:{projectId:string;onRefresh:()=>Promise<void>}) {
  const [requirements,setRequirements]=useState<Requirement[]>([]);
  const [revision,setRevision]=useState(0);
  const [selected,setSelected]=useState("");
  const [candidates,setCandidates]=useState<AssetCandidate[]>([]);
  const [mode,setMode]=useState<"MANUAL_UPLOAD"|"MANAGED_FALLBACK">("MANUAL_UPLOAD");
  const [reason,setReason]=useState("Exact historical source unavailable");
  const [query,setQuery]=useState("");
  const [provider,setProvider]=useState("wikimedia_commons");
  const [cursor,setCursor]=useState<string|null>(null);
  const [pending,setPending]=useState("");
  const [problem,setProblem]=useState("");
  const [notice,setNotice]=useState("");
  const [title,setTitle]=useState("");
  const [sourceNote,setSourceNote]=useState("");
  const [rightsNote,setRightsNote]=useState("");
  const [file,setFile]=useState<File|null>(null);
  const [reviewNotes,setReviewNotes]=useState<Record<string,{rights:string;history:string}>>({});
  const [checks,setChecks]=useState<Record<string,boolean>>({});
  const [prompt,setPrompt]=useState("");
  const [gate,setGate]=useState<Gate|null>(null);
  const reload=useCallback(async(rid?:string)=>{
    const res=await assetApi.requirements(projectId);setRequirements(res.requirements);setRevision(res.project_revision);
    const active=rid||selected||res.requirements[0]?.requirement_id||"";
    setSelected(active);
    if(active)setCandidates((await assetApi.candidates(projectId,active)).candidates);
    setGate((await api.gates(projectId)).find(x=>x.gate_id==="G3")||null);
    await onRefresh();
  },[projectId,selected,onRefresh]);
  useEffect(()=>{void reload().catch(e=>setProblem(String(e)));},[projectId]);
  async function action(label:string,call:()=>Promise<unknown>){
    if(pending)return;setPending(label);setProblem("");setNotice("");
    try{await call();await reload();setNotice(label+" completed. Updated backend state loaded.");}
    catch(e){setProblem(e instanceof Error?e.message:String(e));}
    finally{setPending("");}
  }
  const current=requirements.find(r=>r.requirement_id===selected);
  const approved=Object.values(checks).some(Boolean);
  async function upload(){
    if(!file)return;
    const bytes=new Uint8Array(await file.arrayBuffer());
    let binary=""; for(let i=0;i<bytes.length;i+=8192){binary+=String.fromCharCode(...bytes.subarray(i,i+8192));}
    await assetApi.upload(projectId,revision,selected,btoa(binary),title,sourceNote,rightsNote);
  }
  async function batch(){
    const ids=Object.keys(checks).filter(k=>checks[k]);
    const review:AssetReview[]=ids.map(id=>{
      const c=candidates.find(x=>x.candidate_id===id);
      if(!c?.original_sha256||!c.current_source)throw new Error("Candidate needs verified original and current StoryPackage.");
      return {requirement_id:selected,candidate_id:id,original_sha256:c.original_sha256,rights_status:"ELIGIBLE",
        rights_evidence_note:reviewNotes[id]?.rights||"",historical_context_note:reviewNotes[id]?.history||""};
    });
    if(review.length!==1)throw new Error("Select one candidate per requirement.");
    await assetApi.batch(projectId,revision,review);setChecks({});
  }
  async function approveGate(){
    if(!gate?.candidate_sha256||!gate.dependency_fingerprint)return;
    await api.decide(projectId,"G3",{decision:"APPROVED",candidate_sha256:gate.candidate_sha256,
      dependency_fingerprint:gate.dependency_fingerprint,expected_revision:revision,
      affected_ids:requirements.map(r=>r.requirement_id),comment:"Reviewed exact source and rights evidence"},
      crypto.randomUUID());
  }
  return <div className="asset-studio">
    <h3>Historical sources · G3</h3>
    <p>Candidates are unapproved until human source/rights review. Managed generation requires explicit authorization, and the resulting AI image requires a separate review.</p>
    {problem&&<p role="alert" className="notice error">{problem}</p>}
    {notice&&<p role="status" className="notice success">{notice}</p>}
    <div className="panel">
      <label htmlFor="asset-requirement">Asset requirement</label>
      <select id="asset-requirement" value={selected} disabled={!!pending} onChange={e=>{
        const rid=e.target.value;setSelected(rid);setChecks({});setCursor(null);
        void assetApi.candidates(projectId,rid).then(r=>setCandidates(r.candidates)).catch(e=>setProblem(String(e)));
      }}>
        {requirements.map(r=><option value={r.requirement_id} key={r.requirement_id}>{r.requirement_id} · {r.status} ({r.candidate_count})</option>)}
      </select>
      {!current?<p>Import a StoryPackage containing asset requirements first.</p>:<>
      <p>Resolution: <strong>{current.resolution_mode}</strong> · {current.status}</p>
      <label htmlFor="resolution-reason">Explicit missing-source reason</label>
      <textarea id="resolution-reason" value={reason} onChange={e=>setReason(e.target.value)}/>
      <label htmlFor="resolution-mode">Operator choice</label>
      <select id="resolution-mode" value={mode} onChange={e=>setMode(e.target.value as typeof mode)}>
        <option value="MANUAL_UPLOAD">Upload my original</option><option value="MANAGED_FALLBACK">Authorize managed G-Labs fallback</option>
      </select>
      <button disabled={!!pending||!reason.trim()} onClick={()=>void action("Save resolution",()=>assetApi.choose(projectId,selected,revision,mode,reason))}>
        {pending==="Save resolution"?"Saving…":"Save explicit choice"}</button>
      <hr/>
      <label htmlFor="source-query">Archive search</label>
      <input id="source-query" value={query} onChange={e=>{setQuery(e.target.value);setCursor(null);}}/>
      <select value={provider} onChange={e=>{setProvider(e.target.value);setCursor(null);}}>
        <option value="wikimedia_commons">Wikimedia</option><option value="loc">Library of Congress</option><option value="europeana">Europeana</option>
      </select>
      <button disabled={!!pending||!query.trim()} onClick={()=>void action("Archive search",async()=>{
        const r=await assetApi.search(projectId,revision,selected,provider,query,cursor);setCursor(r.next_cursor);
      })}>{pending==="Archive search"?"Searching…":"Search / next page"}</button>
      {current.resolution_mode==="MANUAL_UPLOAD"&&<div className="panel">
        <h4>Upload verified original</h4>
        <input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>setFile(e.target.files?.[0]||null)}/>
        <input placeholder="Title" value={title} onChange={e=>setTitle(e.target.value)}/>
        <textarea placeholder="Origin and historical context" value={sourceNote} onChange={e=>setSourceNote(e.target.value)}/>
        <textarea placeholder="Rights evidence" value={rightsNote} onChange={e=>setRightsNote(e.target.value)}/>
        <button disabled={!!pending||!file||!title||!sourceNote||!rightsNote} onClick={()=>void action("Manual upload",upload)}>Upload original candidate</button>
      </div>}
      {current.resolution_mode==="MANAGED_FALLBACK"&&<div className="panel">
        <h4>Managed fallback</h4>
        <p>Generating never approves G3. Provider cost may apply after a durable queued job is submitted.</p>
        <textarea placeholder="Exact image prompt" value={prompt} onChange={e=>setPrompt(e.target.value)}/>
        <button disabled={!!pending||!prompt.trim()} onClick={()=>void action("Queue generation",()=>assetApi.generate(projectId,revision,selected,"nano_banana_2",prompt))}>Queue candidate</button>
      </div>}
      </>}
    </div>
    <div className="panel">
      <h4>Candidate review</h4>
      {candidates.length===0?<p>No candidates yet.</p>:candidates.map(c=><article className="claim" key={c.candidate_id}>
        <strong>{c.title||c.candidate_id}</strong> · {c.provider} {c.asset_class||""}
        <p>Original SHA: {c.original_sha256||"NOT DOWNLOADED"} · Rights: {c.rights_status||"UNKNOWN"} · {c.current_source?"Current":"STALE"} {c.approved?"· G3 reviewed":""}</p>
        {!c.original_sha256&&c.provider!=="glabs_webhook"&&c.provider!=="manual_upload"&&
          <button disabled={!!pending||!c.current_source} onClick={()=>void action("Download original",()=>assetApi.original(projectId,revision,selected,c.candidate_id))}>Verify original bytes</button>}
        <label><input type="checkbox" disabled={!c.original_sha256||!c.current_source||!!pending} checked={!!checks[c.candidate_id]}
          onChange={e=>setChecks(old=>({...old,[c.candidate_id]:e.target.checked}))}/> Select for independent rights review</label>
        {checks[c.candidate_id]&&<>
          <label>Rights/license evidence (required)</label><textarea value={reviewNotes[c.candidate_id]?.rights||""} onChange={e=>setReviewNotes(old=>({...old,[c.candidate_id]:{...old[c.candidate_id],rights:e.target.value,history:old[c.candidate_id]?.history||""}}))}/>
          <label>Period, geography, exactness evidence (required)</label><textarea value={reviewNotes[c.candidate_id]?.history||""} onChange={e=>setReviewNotes(old=>({...old,[c.candidate_id]:{...old[c.candidate_id],history:e.target.value,rights:old[c.candidate_id]?.rights||""}}))}/>
        </>}
      </article>)}
      <button disabled={!approved||!!pending} onClick={()=>void action("Approve exact asset source",batch)}>Record selected rights/source approval</button>
    </div>
    <div className="panel">
      <h4>G3 gate — {gate?.state||"DRAFT"}</h4>
      <p>{gate?.blockers.join(", ")||"All required approved sources available"}</p>
      <button disabled={!!pending||gate?.state!=="READY_FOR_REVIEW"} onClick={()=>void action("Approve G3",approveGate)}>Approve complete G3 snapshot</button>
    </div>
    <ProviderSettings/>
  </div>;
}
