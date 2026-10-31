import {useEffect,useMemo,useRef,useState} from "react";
import {api,ApiError,type AuthoringBriefInput,type ProjectInfo,type StoryView} from "../../api/client";

type SavedProject={project_id:string;title:string;project_revision:number};
type Settings=AuthoringBriefInput;
const initial:Settings={topic:"",audience:"General adults",runtime_minutes:7,editorial_goals:"Clear evidence-led historical storytelling"};
const formatError=(e:unknown)=>{
  if(e instanceof ApiError)return `${e.problem.code} · ${e.problem.entity_id??"/"} — ${e.problem.message}. ${e.problem.remediation}`;
  if(e instanceof SyntaxError)return "JSON_SYNTAX_INVALID · / — "+e.message+"; correct the file or pasted JSON before importing.";
  return e instanceof Error?e.message:String(e);
};
export function ProjectWorkspace({project,story,recent,recentStatus,onRetryRecents,onCreate,onOpen,onImported,onRefresh}:{
  project:ProjectInfo|null;story:StoryView|null;recent:SavedProject[];
  recentStatus:"loading"|"ready"|"error";onRetryRecents:()=>Promise<void>;
  onCreate:(title:string)=>Promise<void>;onOpen:(id:string)=>Promise<void>;
  onImported:()=>Promise<void>;onRefresh:()=>Promise<void>;
}){
  const [title,setTitle]=useState("");
  const [filter,setFilter]=useState("");
  const [lookup,setLookup]=useState("");
  const [settings,setSettings]=useState<Settings>(initial);
  const [saved,setSaved]=useState<Settings|null>(null);
  const [step,setStep]=useState<0|1|2>(0);
  const [brief,setBrief]=useState("");
  const [briefSignature,setBriefSignature]=useState("");
  const [briefVersion,setBriefVersion]=useState("");
  const [storyText,setStoryText]=useState("");
  const [job,setJob]=useState("");
  const [notice,setNotice]=useState("");
  const [error,setError]=useState("");
  const [importIssue,setImportIssue]=useState<{code:string;path:string;remediation:string}|null>(null);
  const jsonArea=useRef<HTMLTextAreaElement|null>(null);
  const [clipboardDenied,setClipboardDenied]=useState(false);
  const [lastImport,setLastImport]=useState<{candidate_sha256:string;project_revision:number}|null>(null);
  const epoch=useRef(0);
  const projectId=project?.project_id??"";
  const signature=(value:Settings)=>JSON.stringify([projectId,value.topic,value.audience,value.runtime_minutes,value.editorial_goals]);
  const unsaved=!saved||signature(settings)!==signature(saved);
  const outdated=!!brief&&(unsaved||briefSignature!==signature(saved??settings));
  const filtered=useMemo(()=>recent.filter(x=>x.title.toLowerCase().includes(filter.toLowerCase())||
    x.project_id.toLowerCase().includes(filter.toLowerCase())),[recent,filter]);
  useEffect(()=>{
    const generation=++epoch.current;
    setSettings(initial);setSaved(null);setBrief("");setBriefSignature("");
    setStoryText("");setLastImport(null);setImportIssue(null);setError("");setNotice("");setStep(story?2:0);
    if(!projectId)return;
    void api.authoringSettings(projectId).then(result=>{
      if(epoch.current!==generation)return;
      if(result.settings){setSettings(result.settings);setSaved(result.settings);}
    }).catch(err=>{if(epoch.current===generation)setError(formatError(err));});
  },[projectId]);
  async function run(name:string,action:()=>Promise<void>){
    if(job)return;
    setJob(name);setNotice("");setError("");
    if(name==="Importing StoryPackage")setImportIssue(null);
    try{await action();}
    catch(e){
      setError(formatError(e));
      if(name==="Importing StoryPackage"&&e instanceof ApiError){
        setImportIssue({code:e.problem.code,path:e.problem.entity_id??"/",
          remediation:e.problem.remediation});
      }
    }
    finally{setJob("");}
  }
  async function create(){
    await run("Creating project",async()=>{await onCreate(title);setNotice("Project created. Configure and save its authoring settings.");});
  }
  async function open(id:string){
    await run("Opening project",async()=>{await onOpen(id);setNotice("Selected persisted project.");});
  }
  async function save(){
    if(!project||settings.runtime_minutes<5||settings.runtime_minutes>10||!settings.topic.trim()||!settings.audience.trim())return;
    await run("Saving settings",async()=>{
      await api.saveAuthoringSettings(projectId,settings,project.project_revision,crypto.randomUUID());
      // Authoritative readback, not a client-side optimistic 'saved' badge.
      const persisted=await api.authoringSettings(projectId);
      if(!persisted.settings||signature(persisted.settings)!==signature(settings))
        throw Error("AUTHORING_SETTINGS_READBACK_MISMATCH · Refetch the persisted project settings before building a prompt.");
      setSaved({...persisted.settings});await onRefresh();setStep(1);
      setNotice("Settings verified from the saved project. Continue to ChatGPT Brief.");
    });
  }
  async function build(){
    if(!saved||!project||unsaved)return;
    await run("Building brief",async()=>{
      const response=await api.buildBrief(projectId,saved);
      setBrief(response.content);setBriefVersion(response.brief_version);
      setBriefSignature(signature(saved));setClipboardDenied(false);
      setNotice("Versioned brief prepared for this exact saved project.");
    });
  }
  async function copy(){
    if(outdated||!brief)return;
    try{await navigator.clipboard.writeText(brief);setNotice("Current project brief copied.");setClipboardDenied(false);}
    catch{setClipboardDenied(true);setNotice("Clipboard denied. Select the preview text and copy with keyboard.");}
  }
  function download(){
    if(outdated||!brief)return;
    const url=URL.createObjectURL(new Blob([brief],{type:"text/markdown;charset=utf-8"}));
    const link=document.createElement("a");link.href=url;link.download=projectId+"_story_authoring_brief.md";
    link.click();URL.revokeObjectURL(url);
  }
  function focusInvalidJsonField(){
    if(!importIssue)return;
    const tokens=importIssue.path.match(/[A-Za-z_][A-Za-z_0-9]*/g)??[];
    const candidate=tokens.at(-1);
    const textarea=jsonArea.current;
    if(!candidate||!textarea)return;
    const quoted='"'+candidate+'"';
    const index=storyText.indexOf(quoted);
    if(index<0)return;
    textarea.focus();
    textarea.setSelectionRange(index,index+quoted.length);
    textarea.scrollIntoView({block:"center",behavior:"smooth"});
  }
  async function importStory(){
    if(!project)return;
    await run("Importing StoryPackage",async()=>{
      const parsed:unknown=JSON.parse(storyText);
      if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))throw Error("JSON_ROOT_INVALID · / — StoryPackage must be one object.");
      const source=parsed as {project?:{project_id?:string}};
      if(source.project?.project_id!==projectId)throw Error("STORY_PROJECT_MISMATCH · /project/project_id — must equal "+projectId);
      const result=await api.importStory(projectId,parsed,project.project_revision,crypto.randomUUID());
      setLastImport(result);setNotice("StoryPackage stored as candidate; human G1 approval is still required.");
      await onImported();
    });
  }
  if(!project){
    return <section className="projects-landing" aria-label="project-home">
      <p className="page-intro">Create a Windows-local historical film project or continue an existing one. Only your saved projects appear here.</p>
      {error&&<p role="alert" className="notice error">{error}</p>}
      <div className="project-home">
        <section className="panel" aria-label="new-project">
          <small className="eyebrow">START NEW PRODUCTION</small>
          <h3>New Project</h3>
          <p>Give the film a clear working title. Configure its audience and story brief after creation.</p>
          <label htmlFor="new-title">Project title</label>
          <input id="new-title" value={title} onChange={e=>setTitle(e.target.value)} maxLength={220} placeholder="e.g. The Roads That Changed an Empire" disabled={!!job}/>
          <p className="provenance-line">English · HistoryEditorialPaper.v1 · 16:9 · 1920 × 1080 · 30 fps</p>
          <button className="primary" disabled={!!job||title.trim().length<4} onClick={()=>void create()}>
            {job==="Creating project"?"Creating…":"Create project"}
          </button>
        </section>
        <section className="panel" aria-label="recent-projects">
          <small className="eyebrow">CONTINUE WORK</small><h3>Recent Projects</h3>
          <label htmlFor="project-filter">Search your saved projects</label>
          <input id="project-filter" value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter title or ID"/>
          <div className="project-list">
            {recentStatus==="loading"?<p role="status">Loading saved projects from SQLite…</p>:
             recentStatus==="error"?<div role="alert" className="notice error">
               <p>Could not load saved projects from the local backend. This does not mean the database is empty.</p>
               <button disabled={!!job} onClick={()=>void onRetryRecents()}>Retry saved projects</button>
             </div>:
             filtered.length?filtered.map(item=>
               <div className="project-list-item" key={item.project_id}>
                 <div><strong>{item.title}</strong><small>{item.project_id} · Revision {item.project_revision}</small></div>
                 <button disabled={!!job} onClick={()=>void open(item.project_id)}>Open</button>
               </div>):<p>{recent.length?"No matching project.":"No saved projects yet. Create one to begin."}</p>}
          </div>
          <details><summary>Open by exact Project ID</summary>
            <label htmlFor="project-lookup">Project ID</label>
            <input id="project-lookup" value={lookup} onChange={e=>setLookup(e.target.value)} placeholder="proj_..."/>
            <button disabled={!!job||!lookup.trim()} onClick={()=>void open(lookup.trim())}>Open ID</button>
          </details>
        </section>
      </div>
    </section>;
  }
  return <section className="project-selected" aria-label="project-workflow">
    <div className="flow-steps" role="group" aria-label="Production authoring steps">
      {(["Configure","ChatGPT Brief","Import JSON"] as const).map((label,index)=>
        <button key={label} aria-current={step===index?"step":undefined}
          onClick={()=>setStep(index as 0|1|2)} disabled={!!job}>
          <small>0{index+1}</small>{label}
        </button>)}
    </div>
    {error&&<p role="alert" className="notice error">{error}</p>}
    {notice&&<p role="status" className="notice success">{notice}</p>}
    <div className="project-workflow">
      <section className="panel" aria-label="active-project-task">
      {step===0&&<>
        <small className="eyebrow">01 · CONFIGURE</small><h3>Shape the historical story</h3>
        <p>These authoring preferences are saved to your selected project. Output format is fixed for V1.</p>
        <label htmlFor="brief-topic">Topic / creative objective</label>
        <input id="brief-topic" value={settings.topic} onChange={e=>setSettings(v=>({...v,topic:e.target.value}))}/>
        <label htmlFor="brief-audience">Audience</label>
        <input id="brief-audience" value={settings.audience} onChange={e=>setSettings(v=>({...v,audience:e.target.value}))}/>
        <label htmlFor="brief-minutes">Runtime · 5–10 minutes</label>
        <input id="brief-minutes" type="number" min="5" max="10" value={settings.runtime_minutes}
          onChange={e=>setSettings(v=>({...v,runtime_minutes:Number(e.target.value)}))}/>
        <label htmlFor="brief-goals">Editorial direction and constraints</label>
        <textarea id="brief-goals" rows={4} value={settings.editorial_goals} onChange={e=>setSettings(v=>({...v,editorial_goals:e.target.value}))}/>
        <p className="provenance-line">{unsaved?"UNSAVED CHANGES — Save before building a current prompt.":"SAVED — Current project authoring profile."}</p>
        <button className="primary" disabled={!!job||!unsaved||!settings.topic.trim()||!settings.audience.trim()||settings.runtime_minutes<5||settings.runtime_minutes>10} onClick={()=>void save()}>
          {job==="Saving settings"?"Saving…":"Save settings & continue"}
        </button>
        {!unsaved&&<button className="quiet" onClick={()=>setStep(1)}>Continue to brief</button>}
      </>}
      {step===1&&<>
        <small className="eyebrow">02 · EXTERNAL CHATGPT</small><h3>Build your authoring brief</h3>
        <p>No LLM API is called. Copy the complete versioned brief into external ChatGPT and import the resulting StoryPackage JSON here.</p>
        {!saved?<p>First save valid settings in Configure.</p>:<p className="provenance-line">Saved topic: {saved.topic} · {saved.runtime_minutes} min · bound to {projectId}</p>}
        <button className="primary" disabled={!!job||unsaved||!saved} onClick={()=>void build()}>
          {job==="Building brief"?"Building…":"Build versioned brief"}
        </button>
        {outdated&&<p role="alert" className="notice error">OUTDATED BRIEF — settings changed. Save and rebuild before Copy/Download.</p>}
        {brief&&<>
          <p className="provenance-line">{briefVersion} · {outdated?"OUTDATED":"CURRENT"}</p>
          <label htmlFor="brief-preview">Complete external prompt (selectable)</label>
          <textarea id="brief-preview" readOnly rows={11} value={brief} onFocus={e=>e.currentTarget.select()}/>
          <div className="buttonrow">
            <button disabled={outdated||!!job} onClick={()=>void copy()}>Copy brief</button>
            <button disabled={outdated||!!job} onClick={download}>Download .md</button>
            <button className="primary" disabled={outdated||!!job} onClick={()=>setStep(2)}>Continue to import</button>
          </div>
          {clipboardDenied&&<p role="status">Clipboard permission denied; select all text above and use Ctrl+C.</p>}
        </>}
      </>}
      {step===2&&<>
        <small className="eyebrow">03 · VALIDATE AND IMPORT</small><h3>Import StoryPackage.v1</h3>
        <p>External JSON is validated against canonical schema, cross-references and this exact project ID. Import is a draft, never G1 approval.</p>
        <label htmlFor="story-file">Load JSON file</label>
        <input type="file" id="story-file" accept=".json,application/json" disabled={!!job}
          onChange={async e=>{const file=e.currentTarget.files?.[0];if(file)setStoryText(await file.text());}}/>
        <label htmlFor="story-json">Or paste full StoryPackage JSON</label>
        <textarea id="story-json" ref={jsonArea} spellCheck={false} rows={12} value={storyText}
          onChange={e=>{setStoryText(e.target.value);setImportIssue(null);}}
          placeholder="Paste a complete StoryPackage.v1 object…"/>
        {importIssue&&<section className="notice error" role="alert" aria-label="import-validation-path">
          <strong>{importIssue.code}</strong>
          <p>Source path or entity: <code>{importIssue.path}</code></p>
          <p>{importIssue.remediation}</p>
          <button type="button" onClick={focusInvalidJsonField}>
            Find first matching JSON key (verify occurrence)
          </button>
        </section>}
        <button className="primary" disabled={!!job||!storyText.trim()} onClick={()=>void importStory()}>
          {job==="Importing StoryPackage"?"Validating…":"Validate & import StoryPackage"}
        </button>
        {(lastImport||story)&&<div className="notice success" role="status">
          <strong>Persisted candidate · NOT G1 APPROVED</strong>
          <p className="provenance-line">SHA {(lastImport?.candidate_sha256??story?.candidate_sha256)?.slice(0,24)} · Revision {lastImport?.project_revision??story?.project_revision}</p>
        </div>}
      </>}
      </section>
      <aside className="panel flow-context" aria-label="project-context">
        <small className="eyebrow">ACTIVE LOCAL PROJECT</small>
        <h3>{story?.story.project.title||recent.find(x=>x.project_id===projectId)?.title||"Historical production"}</h3>
        <p className="provenance-line">ID {projectId} · Revision {project.project_revision}</p>
        <h4>Production profile</h4>
        <p>English · HistoryEditorialPaper.v1<br/>1920×1080 · 16:9 · 30 fps</p>
        <h4>Next step</h4>
        <p>{step===0?"Save your topic and authoring requirements.":step===1?"Build and copy the current external ChatGPT prompt.":"Import JSON, inspect claims and approve G1 separately."}</p>
        <h4>True gate status</h4>
        {project.gates.map(g=><p key={g.gate_id}><strong>{g.gate_id} · {g.state}</strong>{g.blockers.length?" — "+g.blockers[0]:""}</p>)}
        {story&&<p className="provenance-line">Story candidate {story.candidate_sha256.slice(0,18)}…</p>}
      </aside>
    </div>
  </section>;
}
