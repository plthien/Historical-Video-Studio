import {useCallback, useRef, useState} from "react";
import {api, ApiError, type Gate, type GateDecision, type GateId, type JobInfo, type ProjectInfo, type StoryPayload, type StoryView} from "./api/client";
import {workspaces} from "./routes/workspaces";
import {VoiceStudio} from "./workspaces/Voice/VoiceStudio";
import {AssetStudio} from "./workspaces/Assets/AssetStudio";
import {StoryboardStudio} from "./workspaces/Storyboard/StoryboardStudio";
import {DeliveryStudio} from "./workspaces/Delivery/DeliveryStudio";

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
    <section className="gate" key={g.gate_id}>
      <strong>{g.gate_id}</strong> <span>{g.state}</span>
      {g.blockers.length > 0 && <small>{g.blockers.slice(0, 2).join("; ")}{g.blockers.length > 2 ? ` +${g.blockers.length-2} more` : ""}</small>}
    </section>)}</div>;
}
export function App() {
  const [workspace, setWorkspace] = useState<string>("project");
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [storyView, setStoryView] = useState<StoryView | null>(null);
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [title, setTitle] = useState("Historical documentary");
  const [existingId, setExistingId] = useState("");
  const [storyText, setStoryText] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [decisionComment, setDecisionComment] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const activeProjectId = useRef<string | null>(null);
  const refreshGeneration = useRef(0);

  const refresh = useCallback(async (projectId: string, switchProject = false) => {
    // A late response from an old workspace must never switch the active
    // project after Create/Open selected a different SQLite project.
    const prior = activeProjectId.current;
    if (!switchProject && prior !== null && prior !== projectId) return;
    if (switchProject) activeProjectId.current = projectId;
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
    } catch (error) {
      if (switchProject && generation === refreshGeneration.current)
        activeProjectId.current = prior;
      throw error;
    }
  }, []);

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

  async function createProject() {
    await execute("Project creation", async () => {
      const created = await api.createProject(title);
      setStoryView(null); setStoryText("");
      await refresh(created.project_id, true);
      setWorkspace("project");
    });
  }
  async function importJson() {
    if (!project) return;
    await execute("Story import", async () => {
      const payload: unknown = JSON.parse(storyText);
      await api.importStory(project.project_id, payload, project.project_revision, idKey());
      await refresh(project.project_id);
      setWorkspace("story");
    });
  }
  async function reviewClaim(claimId: string, status: "REVIEWED" | "VERIFIED") {
    if (!project) return;
    await execute(`Claim ${claimId} review`, async () => {
      const saved = storyView?.claim_reviews.find(r => r.claim_id === claimId);
      await api.reviewClaim(project.project_id, claimId, project.project_revision, status,
                            notes[claimId] ?? saved?.evidence_note ?? "", idKey(),
                            urls[claimId] ?? saved?.source_url ?? null);
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
  return <div className="shell">
    <aside className="sidebar">
      <h1>Historical Video Studio</h1>
      <p className="sub">Windows Local · A2 Voice</p>
      <nav aria-label="Workspaces">{workspaces.map(w =>
        <button key={w.id} type="button" aria-current={workspace === w.id ? "page" : undefined}
          className={workspace === w.id ? "nav-active" : ""} onClick={() => {setWorkspace(w.id); setNotice(null);}}>
          <span>{w.title}</span><small>{w.enabled ? "Available" : `Requires ${w.owner}`}</small>
        </button>)}</nav>
    </aside>
    <main>
      <header className="topline">
        <div><strong>{project ? project.project_id : "No project selected"}</strong>
          <p>Revision: {project ? project.project_revision : "—"}</p></div>
        <button type="button" disabled={!project || !!pending} onClick={() => project && void execute("Refresh", () => refresh(project.project_id))}>
          {pending === "Refresh" ? "Refreshing…" : "Refresh project"}</button>
      </header>
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
          <div className="stack">
            <label htmlFor="new-title">Project title</label>
            <input id="new-title" value={title} onChange={e => setTitle(e.target.value)} disabled={!!pending}/>
            <button disabled={!!pending || title.trim().length < 4} onClick={() => void createProject()}>
              {pending === "Project creation" ? "Creating…" : "Create project"}</button>
            <div className="panel">
              <h3>Open an existing local project</h3>
              <label htmlFor="existing-id">Project ID</label>
              <input id="existing-id" value={existingId} onChange={e => setExistingId(e.target.value)}
                placeholder="proj_..." disabled={!!pending}/>
              <button disabled={!!pending || !existingId.trim()} onClick={() => void execute("Open project", async () => {
                await refresh(existingId.trim(), true);
              })}>Open existing project</button>
            </div>
            {project && <div className="panel">
              <h3>Import external ChatGPT StoryPackage JSON</h3>
              <p>Set <code>project.project_id</code> in your StoryPackage to <code>{project.project_id}</code>. The import is a draft, not G1 approval.</p>
              <label htmlFor="story-file">Load JSON file</label>
              <input type="file" id="story-file" accept=".json,application/json" onChange={async e => {
                const file = e.currentTarget.files?.[0];
                if (file) setStoryText(await file.text());
              }}/>
              <label htmlFor="story-json">StoryPackage JSON</label>
              <textarea id="story-json" rows={10} value={storyText} onChange={e => setStoryText(e.target.value)} placeholder="Paste complete StoryPackage.v1 JSON" disabled={!!pending}/>
              <button disabled={!!pending || !storyText.trim()} onClick={() => void importJson()}>
                {pending === "Story import" ? "Validating and importing…" : "Import and validate story"}</button>
            </div>}
          </div> : <div className="stack">
            {!project && <p>Create a project first using the Project & ChatGPT Import workspace.</p>}
            {project && !storyView && <p>No StoryPackage imported yet. Import a JSON file in the Project workspace.</p>}
            {storyView && <StoryReview story={storyView.story} revision={storyView.project_revision}
              reviewed={storyView.claim_reviews} notes={notes} urls={urls} pending={pending}
              onNote={(claim, value) => setNotes(current => ({...current, [claim]: value}))}
              onUrl={(claim, value) => setUrls(current => ({...current, [claim]: value}))}
              onReview={reviewClaim}/>}
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
      {project && <section className="content">
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
      </section>}
    </main>
  </div>;
}

function StoryReview({story, reviewed, notes, urls, pending, onNote, onUrl, onReview}: {
  story: StoryPayload; revision: number;
  reviewed: StoryView["claim_reviews"]; notes: Record<string,string>; urls: Record<string,string>;
  pending: string | null; onNote: (id:string, value:string)=>void;
  onUrl: (id:string,value:string)=>void; onReview: (id:string,status:"REVIEWED"|"VERIFIED")=>Promise<void>;
}) {
  return <div className="panel">
    <h3>Imported sections ({story.sections.length})</h3>
    <details><summary>Read sections</summary>{story.sections.map(s =>
      <article key={s.section_id}><strong>{s.section_id}</strong><p>{s.narration}</p></article>)}</details>
    <h3>Historical claims ({story.claims.length})</h3>
    {story.claims.map(c => {const saved = reviewed.find(r => r.claim_id === c.claim_id);
      return <article key={c.claim_id} className="claim">
        <strong>{c.claim_id} {c.critical && "· Critical"}</strong>
        <p>{c.text}</p>
        <small>Story source status: {c.status} · Human review: {saved?.status ?? "PENDING"}</small>
        {c.source_leads.map(lead => <p key={lead.url}><a href={lead.url} target="_blank" rel="noreferrer">{lead.title || lead.url}</a></p>)}
        <label htmlFor={`note-${c.claim_id}`}>Evidence review note</label>
        <textarea id={`note-${c.claim_id}`} rows={2} value={notes[c.claim_id] ?? saved?.evidence_note ?? ""}
          onChange={e => onNote(c.claim_id, e.target.value)} />
        <label htmlFor={`url-${c.claim_id}`}>Additional source URL (optional)</label>
        <input id={`url-${c.claim_id}`} value={urls[c.claim_id] ?? saved?.source_url ?? ""}
          onChange={e => onUrl(c.claim_id, e.target.value)} />
        <div className="buttonrow"><button disabled={!!pending || !(notes[c.claim_id] ?? saved?.evidence_note ?? "").trim()}
          onClick={() => void onReview(c.claim_id,"REVIEWED")}>Record reviewed</button>
        <button disabled={!!pending || !(notes[c.claim_id] ?? saved?.evidence_note ?? "").trim()}
          onClick={() => void onReview(c.claim_id,"VERIFIED")}>Record verified</button></div>
      </article>;})}
  </div>;
}
