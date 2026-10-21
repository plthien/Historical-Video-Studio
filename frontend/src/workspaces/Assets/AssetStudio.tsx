import {useCallback,useEffect,useRef,useState} from "react";
import {assetApi,type Requirement,type AssetCandidate,type AssetReview} from "../../api/assets";
import {api,type Gate} from "../../api/client";
import {ProviderSettings} from "../Settings/ProviderSettings";
type StagedReview = AssetReview & {project_id:string;source_story_sha256:string;source_requirement_sha256:string};
function draftMatches(d:StagedReview,c:AssetCandidate|undefined) {
  return Boolean(c && c.current_source && c.candidate_id===d.candidate_id &&
    c.original_sha256===d.original_sha256 &&
    c.source_story_sha256===d.source_story_sha256 &&
    c.source_requirement_sha256===d.source_requirement_sha256);
}
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
  const [staged,setStaged]=useState<StagedReview[]>([]);
  const stagedRef=useRef<StagedReview[]>([]);
  const selectedRef=useRef("");
  const projectRef=useRef(projectId);
  projectRef.current=projectId;
  const requestSeq=useRef(0);
  const reloadSeq=useRef(0);
  function saveStaged(next:StagedReview[]){
    stagedRef.current=next;setStaged(next);
  }
  const loadCandidates=useCallback(async(pid:string,rid:string)=>{
    const seq=++requestSeq.current;
    if(!rid){setCandidates([]);return;}
    const response=await assetApi.candidates(pid,rid);
    if(projectRef.current===pid && selectedRef.current===rid && requestSeq.current===seq)
      setCandidates(response.candidates);
  },[]);
  async function validated(drafts:StagedReview[],allowed:Requirement[]) {
    const eligible=new Set(allowed.map(r=>r.requirement_id));
    const rows=await Promise.all(drafts.map(async d=>{
      if(d.project_id!==projectId || !eligible.has(d.requirement_id))return null;
      const response=await assetApi.candidates(projectId,d.requirement_id);
      return response.candidates.find(c=>draftMatches(d,c))?d:null;
    }));
    return rows.filter((item):item is StagedReview=>item!==null);
  }
  const [preview,setPreview]=useState<Record<string,"loading"|"ok"|"error">>({});
  const [previewAttempt,setPreviewAttempt]=useState<Record<string,number>>({});
  const [prompt,setPrompt]=useState("");
  const [gate,setGate]=useState<Gate|null>(null);
  const reload=useCallback(async(rid?:string)=>{
    const pid=projectId,seq=++reloadSeq.current;
    const res=await assetApi.requirements(pid);
    if(projectRef.current!==pid || seq!==reloadSeq.current)return;
    setRequirements(res.requirements);setRevision(res.project_revision);
    const preferred=rid||selectedRef.current;
    const active=res.requirements.some(r=>r.requirement_id===preferred)
      ? preferred : (res.requirements[0]?.requirement_id||"");
    selectedRef.current=active;setSelected(active);
    await loadCandidates(pid,active);
    const snapshot=stagedRef.current;
    if(snapshot.length){
      try{
        const stillValid=await validated(snapshot,res.requirements);
        if(projectRef.current!==pid||seq!==reloadSeq.current)return;
        if(stagedRef.current===snapshot&&stillValid.length!==snapshot.length){
          saveStaged(stillValid);
          setProblem("Outdated staged review(s) removed after source verification. Check current originals before approval.");
        }
      }catch(e){
        if(projectRef.current===pid)setProblem("Could not verify staged sources: "+String(e));
      }
    }
    const board=await api.gates(pid);
    if(projectRef.current!==pid||seq!==reloadSeq.current)return;
    setGate(board.find(x=>x.gate_id==="G3")||null);
    await onRefresh();
  },[projectId,loadCandidates,onRefresh]);
  useEffect(()=>{
    ++reloadSeq.current;++requestSeq.current;
    saveStaged([]);selectedRef.current="";setSelected("");setCandidates([]);
    setChecks({});setReviewNotes({});setPreview({});setProblem("");setNotice("");
    void reload().catch(e=>{if(projectRef.current===projectId)setProblem(String(e));});
  },[projectId,reload]);
  async function action(label:string,call:()=>Promise<unknown>){
    if(pending)return;setPending(label);setProblem("");setNotice("");
    try{
      const result=await call();
      await reload();
      if(label==="Approve exact asset sources"){
        const rows=(result as {approved?:{requirement_id:string;approval_record_id:string}[]})?.approved||[];
        setNotice("Approved "+rows.length+" requirement(s): "+rows.map(r=>r.requirement_id+" / "+r.approval_record_id).join(", ")+
                  ". G3 still requires an independent operator decision.");
      }else setNotice(label+" completed. Updated backend state loaded.");
    }
    catch(e){
      setProblem(e instanceof Error?e.message:String(e));
      // Fetch changed revisions and prune stale drafts, without silently retrying the mutation.
      try{await reload();}catch{ /* Preserve the original actionable error. */ }
    }
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
  function selectedReview():AssetReview|null {
    const ids=Object.keys(checks).filter(k=>checks[k]);
    if(ids.length===0)return null;
    if(ids.length!==1)throw new Error("Select only one candidate per requirement.");
    const id=ids[0],c=candidates.find(x=>x.candidate_id===id);
    if(!c?.original_sha256||!c.current_source)throw new Error("Candidate needs verified original and current StoryPackage.");
    if(preview[id]!=="ok")throw new Error("Inspect the verified original preview before staging approval.");
    const rights=reviewNotes[id]?.rights?.trim()||"",history=reviewNotes[id]?.history?.trim()||"";
    if(!rights||!history)throw new Error("Provide rights and historical suitability notes.");
    return {requirement_id:selected,candidate_id:id,original_sha256:c.original_sha256,rights_status:"ELIGIBLE",
      rights_evidence_note:rights,historical_context_note:history};
  }
  function stage(){
    try{
      const item=selectedReview();
      if(!item)throw new Error("Select a verified candidate first.");
      const candidate=candidates.find(c=>c.candidate_id===item.candidate_id);
      if(!candidate?.source_story_sha256||!candidate.source_requirement_sha256)
        throw new Error("Source identity unavailable. Refresh candidates before staging.");
      const draft:StagedReview={...item,project_id:projectId,
        source_story_sha256:candidate.source_story_sha256,
        source_requirement_sha256:candidate.source_requirement_sha256};
      saveStaged([...stagedRef.current.filter(x=>x.requirement_id!==item.requirement_id),draft]);
      setChecks({});
      setNotice("Review staged; not approved until batch commit.");
      setProblem("");
    }catch(e){setProblem(e instanceof Error?e.message:String(e));}
  }
  async function batch(){
    const current=selectedReview();
    const draft=current?candidates.find(c=>c.candidate_id===current.candidate_id):null;
    if(current&&(!draft?.source_story_sha256||!draft.source_requirement_sha256))
      throw new Error("Refresh current candidate source before approval.");
    const included=current?[...stagedRef.current.filter(x=>x.requirement_id!==current.requirement_id),
      {...current,project_id:projectId,source_story_sha256:draft!.source_story_sha256!,
        source_requirement_sha256:draft!.source_requirement_sha256!}]:stagedRef.current;
    if(!included.length)throw new Error("Select or stage at least one candidate.");
    const latest=await assetApi.requirements(projectId);
    if(latest.project_revision!==revision)
      throw new Error("REVISION_CONFLICT: Project changed. Reviews will be revalidated; inspect and retry explicitly.");
    const valid=await validated(included,latest.requirements);
    if(valid.length!==included.length){
      // Prune only invalid entries; never approve an unexpectedly reduced batch.
      saveStaged(valid);setChecks({});
      throw new Error("ASSET_SOURCE_STALE: One or more originals changed. Valid drafts remain staged; review before retry.");
    }
    const result=await assetApi.batch(projectId,revision,valid.map(({project_id,source_story_sha256,source_requirement_sha256,...review})=>review));
    saveStaged([]);setChecks({});
    return result;
  }
  async function approveGate(){
    if(!gate?.candidate_sha256||!gate.dependency_fingerprint)return;
    await api.decide(projectId,"G3",{decision:"APPROVED",candidate_sha256:gate.candidate_sha256,
      dependency_fingerprint:gate.dependency_fingerprint,expected_revision:revision,
      affected_ids:requirements.map(r=>r.requirement_id),comment:requirements.length?"Reviewed exact source and rights evidence":"Explicit operator confirmation: StoryPackage requires no historical assets"},
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
        const rid=e.target.value;selectedRef.current=rid;setSelected(rid);
        setChecks({});setReviewNotes({});setPreview({});setCursor(null);setCandidates([]);
        void loadCandidates(projectId,rid).catch(e=>{if(selectedRef.current===rid)setProblem(String(e));});
      }}>
        {requirements.map(r=><option value={r.requirement_id} key={r.requirement_id}>{r.requirement_id} · {r.status} ({r.candidate_count})</option>)}
      </select>
      {!current?<p>No asset requirements in this StoryPackage. Review the empty list and explicitly approve G3 below; nothing is auto-approved.</p>:<>
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
        <p>Original SHA: {c.original_sha256||"NOT DOWNLOADED"} · Rights: {c.rights_status||"UNKNOWN"} · {c.current_source?"Current":"STALE"} {c.approved?"· G3 reviewed":"· Review needed"}</p>
        <p>Creator: {c.creator||"not provided"} · Date: {c.creation_date||"not provided"} · Period: {c.historical_exactness||"not provided"} · Region: {c.place||"not provided"}</p>
        <p>Rights statement: {c.rights_statement||"not provided"} · License: {c.rights_uri||"not provided"} · Historical context: {c.historical_context_note||"not provided"}</p>
        {c.source_page_url&&<p><a href={c.source_page_url} target="_blank" rel="noreferrer">Source metadata</a> (not original bytes)</p>}
        {c.original_sha256&&c.current_source&&
          <figure><img className="asset-original-preview"
            src={assetApi.previewUrl(projectId,selected,c.candidate_id)+"?attempt="+(previewAttempt[c.candidate_id]||0)}
            onLoad={()=>setPreview(old=>({...old,[c.candidate_id]:"ok"}))}
            onError={()=>setPreview(old=>({...old,[c.candidate_id]:"error"}))}
            alt={"Verified original candidate "+c.candidate_id}/>
          <figcaption>Stored original preview · exact SHA {c.original_sha256} · {c.mime_type||"image"} · {preview[c.candidate_id]==="ok"?"Image loaded; review rights separately":preview[c.candidate_id]==="error"?"PREVIEW FAILED — not visually inspected":"Checking preview"}</figcaption>
          {preview[c.candidate_id]==="error"&&<><p role="alert">Original image could not be loaded. Review disabled until a successful preview.</p>
            <button onClick={()=>{setPreview(old=>({...old,[c.candidate_id]:"loading"}));setPreviewAttempt(old=>({...old,[c.candidate_id]:(old[c.candidate_id]||0)+1}));}}>Retry original preview</button></>}
          </figure>}
        {c.provider==="europeana"&&!c.hydrated&&c.current_source&&
          <button disabled={!!pending} onClick={()=>void action("Hydrate Europeana record",
            ()=>assetApi.hydrate(projectId,revision,selected,c.candidate_id))}>
            Hydrate Europeana record
          </button>}
        {!c.original_sha256&&c.provider!=="glabs_webhook"&&c.provider!=="manual_upload"&&(c.provider!=="europeana"||c.hydrated)&&
          <button disabled={!!pending||!c.current_source} onClick={()=>void action("Download original",()=>assetApi.original(projectId,revision,selected,c.candidate_id))}>Verify original bytes</button>}
        <label><input type="checkbox" disabled={!c.original_sha256||!c.current_source||preview[c.candidate_id]!=="ok"||!!pending} checked={!!checks[c.candidate_id]}
          onChange={e=>setChecks(old=>({...old,[c.candidate_id]:e.target.checked}))}/> Select for independent rights review</label>
        {checks[c.candidate_id]&&<>
          <label>Rights/license evidence (required)</label><textarea value={reviewNotes[c.candidate_id]?.rights||""} onChange={e=>setReviewNotes(old=>({...old,[c.candidate_id]:{...old[c.candidate_id],rights:e.target.value,history:old[c.candidate_id]?.history||""}}))}/>
          <label>Period, geography, exactness evidence (required)</label><textarea value={reviewNotes[c.candidate_id]?.history||""} onChange={e=>setReviewNotes(old=>({...old,[c.candidate_id]:{...old[c.candidate_id],history:e.target.value,rights:old[c.candidate_id]?.rights||""}}))}/>
        </>}
      </article>)}
      <div className="buttonrow">
        <button disabled={!approved||!!pending} onClick={stage}>Stage selected for batch</button>
        <button disabled={(!approved&&!staged.length)||!!pending} onClick={()=>void action("Approve exact asset sources",batch)}>
          Approve {staged.length+(approved?1:0)} selected/staged source(s)
        </button>
      </div>
      {staged.length>0&&<div>
        <p role="status">{staged.length} staged; no approval recorded yet. Commit as one atomic batch.</p>
        <ul>{staged.map(d=><li key={d.requirement_id}>
          {d.requirement_id} · {d.candidate_id} · {d.original_sha256.slice(0,12)} · {d.rights_evidence_note}
          <button type="button" disabled={!!pending} aria-label={"Remove staged "+d.requirement_id}
            onClick={()=>saveStaged(stagedRef.current.filter(x=>x.requirement_id!==d.requirement_id))}>Remove</button>
        </li>)}</ul>
      </div>}
    </div>
    <div className="panel">
      <h4>G3 gate — {gate?.state||"DRAFT"}</h4>
      <p>{gate?.blockers.join(", ")||"All required approved sources available"}</p>
      {gate?.state==="STALE"&&<p>G3 approval is stale. Re-review and reapprove the exact current original(s); previous approval is never restored automatically.</p>}
      <button disabled={!!pending||gate?.state!=="READY_FOR_REVIEW"} onClick={()=>void action("Approve G3",approveGate)}>Approve complete G3 snapshot</button>
    </div>
    <ProviderSettings/>
  </div>;
}
