import {useCallback,useEffect,useState} from "react";
import {ApiError} from "../../api/client";
import {storyboardApi,type BlueprintAuthoring} from "../../api/storyboard";

const errorText=(err:unknown)=>err instanceof ApiError?
  `${err.problem.code}: ${err.problem.message} — ${err.problem.remediation}`:
  err instanceof Error?err.message:String(err);

export function BlueprintAuthoring({projectId,onBuilt}:{
  projectId:string;onBuilt:()=>Promise<void>;
}){
  const [data,setData]=useState<BlueprintAuthoring|null>(null);
  const [selected,setSelected]=useState("");
  const [drafts,setDrafts]=useState<Record<string,string>>({});
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const reload=useCallback(async()=>{
    const current=await storyboardApi.blueprint(projectId);
    setData(current);
    setSelected(previous=>current.setups.some(x=>x.setup_id===previous)?previous:current.setups[0]?.setup_id??"");
    setDrafts(previous=>{
      const next={...previous};
      for(const setup of current.setups)
        if(!(setup.setup_id in next))next[setup.setup_id]=JSON.stringify(
          setup.payload??{template_id:setup.template_id},null,2);
      return next;
    });
  },[projectId]);
  useEffect(()=>{setDrafts({});setData(null);setError("");void reload().catch(e=>setError(errorText(e)));},[reload]);
  const setup=data?.setups.find(x=>x.setup_id===selected);
  async function run(label:string,fn:()=>Promise<void>){
    if(busy)return;
    setBusy(label);setError("");setNotice("");
    try{await fn();setNotice(label+" completed; server source identities verified.");}
    catch(e){setError(errorText(e));}
    finally{setBusy("");}
  }
  function save(){
    if(!data||!setup)return;
    void run("Save reviewed payload",async()=>{
      const parsed:unknown=JSON.parse(drafts[setup.setup_id]);
      if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))
        throw Error("Supply one template payload JSON object.");
      await storyboardApi.savePayload(projectId,setup.setup_id,data.project_revision,
        data.story_sha256,parsed as Record<string,unknown>,crypto.randomUUID());
      await reload();
    });
  }
  function compile(){
    if(!data)return;
    void run("Compile real G4 draft",async()=>{
      await storyboardApi.compile(projectId,data.project_revision,data.story_sha256,crypto.randomUUID());
      await onBuilt();
      await reload();
    });
  }
  return <section className="panel blueprint-authoring" aria-label="typed-blueprint-authoring">
    <h3>Initial G4 storyboard · authored setup payloads</h3>
    <p>The StoryPackage does not contain every T01–T10 template field. Add each explicitly reviewed payload below; this is not a second ChatGPT pass or a source-code editor. Saving does not approve G4.</p>
    {error&&<p role="alert" className="notice error">{error}</p>}
    {notice&&<p role="status" className="notice success">{notice}</p>}
    {!data?<p>Loading authoritative StoryPackage setups…</p>:
      <>
        <p>Story SHA: <code>{data.story_sha256.slice(0,16)}</code> · {data.setups.filter(x=>x.payload).length}/{data.setups.length} saved · registry {data.registry_version}</p>
        <label htmlFor="blueprint-setup">Visual setup and pinned template</label>
        <select id="blueprint-setup" disabled={!!busy} value={selected} onChange={e=>setSelected(e.target.value)}>
          {data.setups.map(item=><option key={item.setup_id} value={item.setup_id}>
            {item.setup_id} · {item.template_id} · {item.payload?"Authored":"Requires authoring"}
          </option>)}
        </select>
        {setup&&<>
          <p>Allowed source refs: sections {setup.section_refs.join(", ")||"none"};
            claims {setup.claim_refs.join(", ")||"none"}; requirements {setup.requirement_refs.join(", ")||"none"}.
          </p>
          <details><summary>Read immutable Story setup direction</summary>
            <pre className="blueprint-schema">{JSON.stringify(setup.direction,null,2)}</pre>
          </details>
          <details><summary>Template schema · required fields and typed enum constraints</summary>
            <pre className="blueprint-schema">{JSON.stringify(setup.schema,null,2)}</pre>
          </details>
          <label htmlFor="blueprint-payload">Operator-reviewed {setup.template_id} payload JSON</label>
          <textarea id="blueprint-payload" spellCheck={false} rows={14} value={drafts[setup.setup_id]??""}
            onChange={e=>setDrafts(current=>({...current,[setup.setup_id]:e.target.value}))}/>
          <div className="buttonrow">
            <button disabled={!!busy||!drafts[setup.setup_id]?.trim()} onClick={save}>Validate and save setup</button>
            <button disabled={!!busy} onClick={()=>void run("Reload current G4 source",reload)}>Reload authoring</button>
          </div>
        </>}
        <div className="buttonrow">
          <button disabled={!!busy||!data.ready} onClick={compile}>
            Compile storyboard from approved G1/G2/G3 and verified alignment
          </button>
        </div>
        {!data.ready&&<p>Compile blocked until every required setup has a validated explicit payload.</p>}
        <p>Native Windows GDI font, rights-reviewed original media, word map, period maps and gate approvals are verified again by the compiler. Compile never approves G4 automatically.</p>
      </>}
  </section>;
}
