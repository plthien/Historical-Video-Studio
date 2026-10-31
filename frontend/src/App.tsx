import {useCallback, useEffect, useRef, useState} from "react";
import {api, ApiError, type Gate, type GateDecision, type GateId, type JobInfo, type ProjectInfo, type StoryPayload, type StoryView} from "./api/client";
import {workspaces} from "./routes/workspaces";
import {VoiceStudio} from "./workspaces/Voice/VoiceStudio";
import {AssetStudio} from "./workspaces/Assets/AssetStudio";
import {StoryboardStudio} from "./workspaces/Storyboard/StoryboardStudio";
import {DeliveryStudio} from "./workspaces/Delivery/DeliveryStudio";
import {ProjectWorkspace} from "./workspaces/Project/ProjectWorkspace";

type Notice = {kind: "success" | "error"; message: string};
const idKey = () => crypto.randomUUID();
function problemMessage(error: unknown) {
  if (error instanceof ApiError) {
    return `${error.problem.code}: ${error.problem.message} — ${error.problem.remediation}`;
  }
  return error instanceof Error ? error.message : "An unexpected local error occurred.";
}
function NoticeView({notice}: {notice: Notice | null}) {
  return notice ? <p role={notice.kind === "error" ? "alert" : "status"} className={`notice ${notice.kind}`}>{notice.message}</p> : null;
}
function GateBoard({gates}: {gates: Gate[]}) {
  return <div className="gateboard" aria-label="Five review gates">{gates.map(g =>
    <section className="gate" data-state={g.state} key={g.gate_id}>
      <strong>{g.gate_id}</strong> <span>{g.state}</span>
      {g.blockers.length > 0 && <small>{g.blockers.slice(0, 2).join("; ")}{g.blockers.length > 2 ? ` +${g.blockers.length-2} more` : ""}</small>}
    </section>)}</div>;
}
export function App() {
  const [workspace, setWorkspace] = useState<string>(() => workspaces.some(w=>w.id===location.hash.slice(1))?location.hash.slice(1):"project");
  const [recent,setRecent] = useState<{project_id:string;title:string;project_revision:number}[]>([]);
  const [recentStatus,setRecentStatus] = useState<"loading"|"ready"|"error">("loading");
  const [sectionEdit,setSectionEdit] = useState<string|null>(null);
  const [sectionNarration,setSectionNarration] = useState("");
  const [sectionReason,setSectionReason] = useState("");
  useEffect(()=>{location.hash=workspace;},[workspace]);
  const reloadRecents=useCallback(async()=>{
    setRecentStatus("loading");
    try {const items=await api.listProjects();setRecent(items);setRecentStatus("ready");}
    catch {setRecentStatus("error");}
  },[]);
  useEffect(()=>{void reloadRecents();},[reloadRecents]);

  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [storyView, setStoryView] = useState<StoryView | null>(null);
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [decisionComment, setDecisionComment] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [buildInfo,setBuildInfo]=useState<{source_commit:string;bundle_sha256:string}|null>(null);
  useEffect(()=>{void fetch("/build-info.json").then(r=>r.json()).then((x:unknown)=>{
    if(x&&typeof x==="object"&&"source_commit" in x&&"bundle_sha256" in x)
      setBuildInfo(x as {source_commit:string;bundle_sha256:string});
  }).catch(()=>{});},[]);

  const activeProjectId = useRef<string | null>(null);
  const refreshGeneration = useRef(0);

  const refresh = useCallback(async (projectId: string, switchProject = false) => {
    // A late response from an old workspace must never switch the active
    // project after Create/Open selected a different SQLite project.
    const prior = activeProjectId.current;
    if (!switchProject && prior !== null && prior !== projectId) return;
    if (switchProject) {
      activeProjectId.current = projectId;
      setSectionEdit(null);setNotes({});setUrls({});setDecisionComment("");
    }
    const generation = ++refreshGeneration.current;
    try {
      const [current, story, taskList] = await Promise.all([
        api.project(projectId),
        api.story(projectId).catch((e: unknown) => {
          if (e instanceof ApiError && (e.status === 424 || e.status === 404)) return null;
          throw e;
        }), api.jobs(projectId)
      ]);
      if (generation !== refreshGeneration.current || activeProjectId.current !== projectId) return;
      setProject(current);
      setStoryView(story);
      setJobs(taskList);
      if (switchProject) sessionStorage.setItem("hvs.activeProjectId",projectId);
    } catch (error) {
      if (switchProject && generation === refreshGeneration.current)
        activeProjectId.current = prior;
      throw error;
    }
  }, []);

  useEffect(()=>{
    const stored=sessionStorage.getItem("hvs.activeProjectId");
    if(stored){void refresh(stored,true).catch(()=>sessionStorage.removeItem("hvs.activeProjectId"));}
  },[refresh]);

  async function execute(label: string, action: () => Promise<void>) {
    if (pending) return;
    setPending(label);
    setNotice(null);
    try {
      await action();
      setNotice({kind: "success", message: `${label} completed and confirmed by the local backend.`});
    } catch (err) {
      setNotice({kind: "error", message: problemMessage(err)});
      if (err instanceof ApiError && err.status === 409 && project) {
        try { await refresh(project.project_id); } catch { /* Keep the original conflict visible. */ }
      }
    } finally {
      setPending(null);
    }
  }

  async function createProject(name:string){
    const created=await api.createProject(name);
    await refresh(created.project_id,true);
    await reloadRecents();
    setWorkspace("project");
  }
  async function openProject(id:string){await refresh(id,true);setWorkspace("project");}
  async function reviewClaim(claimId: string, status: "REVIEWED" | "VERIFIED") {
    if (!project) return;
    await execute(`Claim ${claimId} review`, async () => {
      const saved = storyView?.claim_reviews.find(r => r.claim_id === claimId);
      const rawSourceUrl = urls[claimId] ?? saved?.source_url ?? "";
      const sourceUrl = rawSourceUrl.trim() || null;
      await api.reviewClaim(project.project_id, claimId, project.project_revision, status,
                            notes[claimId] ?? saved?.evidence_note ?? "", idKey(),
                            sourceUrl);
      await refresh(project.project_id);
    });
  }
  async function decide(gate: Gate, decision: GateDecision["decision"]) {
    if (!project || !gate.candidate_sha256 || !gate.dependency_fingerprint) return;
    const candidateSha = gate.candidate_sha256;
    const fingerprint = gate.dependency_fingerprint;
    await execute(`G1 ${decision.toLowerCase()}`, async () => {
      await api.decide(project.project_id, "G1", {
        decision, candidate_sha256: candidateSha,
        dependency_fingerprint: fingerprint,
        expected_revision: project.project_revision, comment: decisionComment,
        affected_ids: []
      }, idKey());
      await refresh(project.project_id);
    });
  }
  async function cancelJob(jobId: string) {
    if (!project) return;
    await execute(`Cancel request ${jobId}`, async () => {
      const job=jobs.find(x=>x.job_id===jobId);
      if(job?.kind==="glabs_image")await api.cancelManaged(project.project_id,jobId,idKey());
      else await api.cancelJob(jobId,idKey());
      await refresh(project.project_id);
    });
  }
  async function retryJob(jobId:string){
    if(!project)return;
    await execute(`Retry managed task ${jobId}`,async()=>{
      await api.retryManaged(project.project_id,jobId,idKey());
      await refresh(project.project_id);
    });
  }
  const active = workspaces.find(w => w.id === workspace) ?? workspaces[0];
  const g1 = project?.gates.find(g => g.gate_id === "G1");
  const nextGate = project?.gates.find(g=>g.state!=="APPROVED");
  const g2=project?.gates.find(g=>g.gate_id==="G2");
  const g3=project?.gates.find(g=>g.gate_id==="G3");
  const chooseParallel = g2?.state==="APPROVED"?"assets":
    g3?.state==="APPROVED"?"voice":
    (g2?.blockers.length&&!g3?.blockers.length)?"assets":
    (g3?.blockers.length&&!g2?.blockers.length)?"voice":"voice";
  const nextWorkspace = !storyView?"project":nextGate?.gate_id==="G1"?"story":
    nextGate?.gate_id==="G2"||nextGate?.gate_id==="G3"?chooseParallel:
    nextGate?.gate_id==="G4"?"storyboard":"delivery";
  async function correctSection(sectionId:string){
    if(!project)return;
    await execute("Correct Story section",async()=>{
      await api.patchSection(project.project_id,sectionId,project.project_revision,sectionNarration,sectionReason,idKey());
      setSectionEdit(null);
      await refresh(project.project_id);
    });
  }
  return <div className="shell">
    <aside className="sidebar">
      <h1>HISTORICAL <span>VIDEO</span></h1>
      <p className="sub">STUDIO · WINDOWS LOCAL</p>
      <nav aria-label="Workspaces">{workspaces.map(w =>
        <button key={w.id} type="button" aria-current={workspace === w.id ? "page" : undefined}
          aria-label={w.title} data-testid={`workspace-${w.id}`}
          className={workspace === w.id ? "nav-active" : ""} onClick={() => {setWorkspace(w.id); setNotice(null);}}>
          <b>{String(workspaces.indexOf(w)+1).padStart(2,"0")}</b><span>{w.title}</span>
        </button>)}</nav>
    </aside>
    <main><div className="content-container">
      <header className="topline">
        <div>
          <small className="eyebrow">{project?"LOCAL PRODUCTION · ENGLISH FIRST":"WINDOWS LOCAL · YOUR WORKSPACE"}</small>
          <h2>{project?(storyView?.story.project.title||recent.find(x=>x.project_id===project.project_id)?.title||"Selected project"):"Projects"}</h2>
          {project&&<><strong>{project.project_id} · Revision {project.project_revision}</strong>
            <p>Current stage: {nextGate?.gate_id??"All gates approved"} · {nextGate?.state??"APPROVED"}</p></>}
        </div>
        <div className="header-actions">
          {project&&<button type="button" className="primary" disabled={!!pending}
            onClick={()=>{setWorkspace(nextWorkspace);setNotice(nextGate?.blockers.length?
              {kind:"error",message:nextGate.blockers.join("; ")}:null);}}>
            {nextGate?.state==="STALE"?"Repair":nextGate?.state==="BLOCKED"?"Review blockers":"Next valid action"} · {nextGate?.gate_id??"Delivery"}
          </button>}
          {project&&<button type="button" disabled={!!pending}
            onClick={()=>void execute("Refresh",()=>refresh(project.project_id))}>
            {pending==="Refresh"?"Refreshing…":"Refresh project"}</button>}
          {project&&<button className="quiet" type="button" onClick={()=>{
            activeProjectId.current=null;++refreshGeneration.current;sessionStorage.removeItem("hvs.activeProjectId");setProject(null);setStoryView(null);setJobs([]);setWorkspace("project");
            void reloadRecents();
          }}>All projects</button>}
        </div>
      </header>
      {project&&<p className="workflow-hint">Five explicit approvals: G1 Story → G2 Voice / G3 Assets → G4 Storyboard → G5 Delivery</p>}
      {project && <GateBoard gates={project.gates}/>}
      <NoticeView notice={notice}/>
      <section className="content" aria-label={active.title}>
        <h2>{active.title}</h2>
        {!active.enabled ? <div className="unavailable" role="note">
          <strong>Not available in A1</strong>
          <p>This workspace requires the {active.owner} owner implementation. No provider, approved media, alignment, render, or export result is simulated.</p>
        </div> : workspace === "delivery" && project ?
          <DeliveryStudio project={project} onRefresh={() => refresh(project.project_id)}/> : workspace === "storyboard" && project ?
          <StoryboardStudio projectId={project.project_id} onRefresh={() => refresh(project.project_id)}/> : workspace === "assets" && project ?
          <AssetStudio projectId={project.project_id} projectRevision={project.project_revision} onRefresh={() => refresh(project.project_id)}/> : workspace === "voice" && project ?
          <VoiceStudio project={project} story={storyView} onRefresh={() => refresh(project.project_id)}/> : workspace === "project" ?
          <ProjectWorkspace project={project} story={storyView} recent={recent}
            recentStatus={recentStatus} onRetryRecents={reloadRecents}
            onCreate={createProject} onOpen={openProject}
            onImported={async()=>{if(project){await refresh(project.project_id);setWorkspace("story");}}}
            onRefresh={async()=>{if(project)await refresh(project.project_id);}}/>
           : <div className="story-workspace">
            {!project && <p>Create a project first using the Project & ChatGPT Import workspace.</p>}
            {project && !storyView && <p>No StoryPackage imported yet. Import a JSON file in the Project workspace.</p>}
            {storyView && <StoryReview story={storyView.story} revision={storyView.project_revision}
              reviewed={storyView.claim_reviews} notes={notes} urls={urls} pending={pending}
              onNote={(claim, value) => setNotes(current => ({...current, [claim]: value}))}
              onUrl={(claim, value) => setUrls(current => ({...current, [claim]: value}))}
              onReview={reviewClaim}/>}
            {storyView&&<div className="panel">
              <h3>Bounded narration correction</h3>
              {storyView.story.sections.map(section=><article key={section.section_id} className="claim">
                <strong>{section.section_id}</strong>
                <button onClick={()=>{setSectionEdit(section.section_id);setSectionNarration(section.narration);setSectionReason("");}}>Edit narration</button>
                {sectionEdit===section.section_id&&<>
                  <label htmlFor="section-narration">Narration</label>
                  <textarea id="section-narration" rows={5} value={sectionNarration} onChange={e=>setSectionNarration(e.target.value)}/>
                  <label htmlFor="section-reason">Correction reason</label>
                  <input id="section-reason" value={sectionReason} onChange={e=>setSectionReason(e.target.value)}/>
                  <p>Revision impact: re-review G1, G2, G4 and G5. G3 assets retain independent approval unless asset requirements change.</p>
                  <div className="buttonrow">
                    <button disabled={!!pending||!sectionReason.trim()||sectionNarration===section.narration} onClick={()=>void correctSection(section.section_id)}>Confirm correction</button>
                    <button onClick={()=>setSectionEdit(null)}>Cancel</button>
                  </div>
                </>}
              </article>)}
            </div>}
            {g1 && <div className="panel">
              <h3>G1 review decision</h3>
              <p>Current status: <strong>{g1.state}</strong>. {g1.blockers.length ? g1.blockers.join(", ") : "All required claim reviews completed."}</p>
              <label htmlFor="decision-comment">Operator decision comment</label>
              <textarea id="decision-comment" value={decisionComment} onChange={e => setDecisionComment(e.target.value)} rows={2}/>
              <div className="buttonrow">{(["APPROVED","CHANGES_REQUESTED","REJECTED"] as const).map(d =>
                <button key={d} disabled={!!pending || g1.state !== "READY_FOR_REVIEW"}
                  onClick={() => void decide(g1, d)}>{d === "APPROVED" ? "Approve G1" : d === "REJECTED" ? "Reject G1" : "Request changes"}</button>)}</div>
            </div>}
          </div>}
      </section>
      {project && <details className="content jobs-drawer"><summary>Project jobs · {jobs.length}</summary>
        <h2>Project jobs</h2><p>Only real persisted jobs appear here. RUNNING cancellation is a request until confirmed.</p>
        <button disabled={!!pending} onClick={() => void execute("Refresh jobs", () => refresh(project.project_id))}>Refresh jobs</button>
        {jobs.length === 0 ? <p>No jobs have been submitted by an implemented workflow.</p> :
          <ul>{jobs.map(job => <li key={job.job_id}>
            <strong>{job.job_id}</strong> — {job.kind}: {job.state}
            {job.error_code && <span> · {job.error_code}</span>}
            {job.progress&&<span> · progress {job.progress.completed}/{job.progress.total} frames</span>}
            {job.cancel_requested===1&&<small>Cancellation requested; confirmation is pending.</small>}
            {job.remediation&&<small>{job.remediation}</small>}
            {["QUEUED","RUNNING","FAILED_RETRYABLE","BLOCKED_REVIEW"].includes(job.state) &&
              <button disabled={!!pending} onClick={() => void cancelJob(job.job_id)}>
                {job.cancel_requested ? "Reconcile cancellation with provider" : "Request cancellation"}</button>}
            {job.retry_action==="managed_resume"&&
              <button disabled={!!pending} onClick={()=>void retryJob(job.job_id)}>Retry / resume original task</button>}
            {job.retry_action==="render_retry"&&
              <button disabled={!!pending} onClick={()=>setWorkspace("delivery")}>Open Final Video retry</button>}
            {job.retry_action==="voice_alignment_retry"&&
              <button disabled={!!pending} onClick={()=>setWorkspace("voice")}>Open Voice alignment retry</button>}
            {job.output_available&&
              <button disabled={!!pending} onClick={()=>setWorkspace("delivery")}>Open reviewed output</button>}
            {job.kind==="glabs_image"&&job.state==="BLOCKED_REVIEW"&&
              <small>Restore original webhook credentials, then reconcile cancellation. No automatic paid resubmission.</small>}
          </li>)}</ul>}
      </details>}
      <footer className="provenance-line build-footer" aria-label="build-identity">
        {buildInfo?
          `UI source ${buildInfo.source_commit.slice(0,12)} · bundle ${buildInfo.bundle_sha256.slice(0,12)} · PR13 V2`:
          "Development build · production SHA manifest not loaded"}
      </footer>
    </div></main>
  </div>;
}

function StoryReview({story, reviewed, notes, urls, pending, onNote, onUrl, onReview}: {
  story: StoryPayload; revision: number;
  reviewed: StoryView["claim_reviews"]; notes: Record<string,string>; urls: Record<string,string>;
  pending: string | null; onNote:(id:string,value:string)=>void;
  onUrl:(id:string,value:string)=>void; onReview:(id:string,status:"REVIEWED"|"VERIFIED")=>Promise<void>;
}){
  const [selected,setSelected]=useState("");
  const active=story.sections.find(s=>s.section_id===selected)??story.sections[0];
  const critical=story.claims.filter(c=>c.critical);
  const complete=critical.filter(c=>reviewed.some(r=>r.claim_id===c.claim_id&&
    ["REVIEWED","VERIFIED"].includes(r.status))).length;
  return <div className="story-review-layout" aria-label="story-review-layout">
    <aside className="panel story-script-nav">
      <small className="eyebrow">FROZEN STORY REVISION</small><h3>Script sections</h3>
      <p className="provenance-line">{story.sections.length} sections</p>
      {story.sections.map(s=><button key={s.section_id} type="button"
        className={active?.section_id===s.section_id?"primary":"quiet"}
        aria-current={active?.section_id===s.section_id?"true":undefined}
        onClick={()=>setSelected(s.section_id)}>{s.section_id}</button>)}
    </aside>
    <section className="panel story-reading">
      <small className="eyebrow">NARRATION · SOURCE LOCKED</small>
      <h3>{active?.section_id??"No script section"}</h3>
      {active&&<article className="story-narration">{active.narration}</article>}
      <p className="provenance-line">Claim references: {active?.claim_refs.join(", ")||"none"}.
        Use the bounded correction editor below to create a new immutable revision.</p>
    </section>
    <aside className="panel story-claims">
      <small className="eyebrow">HUMAN RESEARCH APPROVAL · G1</small>
      <h3>Historical claims ({story.claims.length})</h3>
      <p className="provenance-line">Critical human reviews: {complete}/{critical.length}. Imported AI source status is not a human approval.</p>
      <div className="section-scroll">{story.claims.map(c=>{
        const saved=reviewed.find(r=>r.claim_id===c.claim_id);
        return <article key={c.claim_id} className="claim">
          <strong>{c.critical?"CRITICAL · ":""}{c.claim_id}</strong>
          <p>{c.text}</p>
          <p className="provenance-line">Imported: {c.status} · Human: {saved?.status??"PENDING"}</p>
          {c.source_leads.map(lead=><p key={lead.url}><a href={lead.url} target="_blank" rel="noreferrer">{lead.title||lead.url}</a></p>)}
          <label htmlFor={`note-${c.claim_id}`}>Human evidence review note</label>
          <textarea id={`note-${c.claim_id}`} rows={2} value={notes[c.claim_id]??saved?.evidence_note??""}
            onChange={e=>onNote(c.claim_id,e.target.value)}/>
          <label htmlFor={`url-${c.claim_id}`}>Additional source URL (optional)</label>
          <input id={`url-${c.claim_id}`} value={urls[c.claim_id]??saved?.source_url??""}
            onChange={e=>onUrl(c.claim_id,e.target.value)}/>
          <div className="buttonrow">
            <button disabled={!!pending||!(notes[c.claim_id]??saved?.evidence_note??"").trim()}
              onClick={()=>void onReview(c.claim_id,"REVIEWED")}>Record reviewed</button>
            <button disabled={!!pending||!(notes[c.claim_id]??saved?.evidence_note??"").trim()}
              onClick={()=>void onReview(c.claim_id,"VERIFIED")}>Record verified</button>
          </div>
        </article>;
      })}</div>
    </aside>
  </div>;
}
