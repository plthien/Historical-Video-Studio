import {useCallback,useEffect,useState} from "react";
import {ApiError} from "../../api/client";
import {storyboardApi,type BlueprintAuthoring,type BlueprintSetup} from "../../api/storyboard";
import {MapAuthoring} from "./MapAuthoring";

type Schema={type?:string;const?:unknown;enum?:unknown[];anyOf?:Schema[];properties?:Record<string,Schema>;
  items?:Schema;required?:string[];minimum?:number;maximum?:number;minLength?:number;description?:string};
const errorText=(e:unknown)=>e instanceof ApiError?
  `${e.problem.code}: ${e.problem.entity_id??"/"} · ${e.problem.message} — ${e.problem.remediation}`:
  e instanceof Error?e.message:"Local authoring failed";
const obj=(value:unknown):Record<string,unknown>=>value&&typeof value==="object"&&!Array.isArray(value)?
  value as Record<string,unknown>:{};
function emptyValue(schema:Schema):unknown{
  if(schema.const!==undefined)return schema.const;
  if(schema.anyOf){return schema.anyOf.some(x=>x.type==="null")?null:emptyValue(schema.anyOf[0]);}
  if(schema.type==="object")return {};
  if(schema.type==="array")return [];
  if(schema.type==="boolean")return false;
  if(schema.type==="integer"||schema.type==="number")return null;
  return "";
}
function sourceHint(name:string,setup:BlueprintSetup){
  const key=name.toLowerCase();
  if(key.includes("claim"))return setup.claim_refs.length?`G1 claim refs: ${setup.claim_refs.join(", ")}`:"No claim refs provided by this setup";
  if(key.includes("slot"))return "Use an exact asset slot ID from the frozen Story setup; G3 review remains mandatory.";
  if(key.includes("requirement"))return setup.requirement_refs.length?`G1 asset requirements: ${setup.requirement_refs.join(", ")}`:"No G1 asset requirements in this setup";
  if(key.includes("geometry")||key.includes("feature")||key.includes("coordinate"))return "Enter only source-reviewed G3 historical map identifiers; never invent a geometry.";
  if(key.includes("year")||key.includes("date"))return "Use the exact documented historical year/date from approved G1 evidence.";
  if(key.includes("quote")||key.includes("text"))return "Select an actual immutable Story on-screen text ID, not a new fabricated quotation.";
  return "";
}
function Field({name,path,schema,value,required,setup,onChange}:{
  name:string;path:string;schema:Schema;value:unknown;required:boolean;setup:BlueprintSetup;onChange:(v:unknown)=>void;
}){
  const relevant=schema.anyOf?.find(x=>x.type!=="null");
  const nullable=schema.anyOf?.some(x=>x.type==="null");
  const effective=relevant??schema;
  const inputId="typed-"+path.replace(/[^a-zA-Z0-9]/g,"-");
  if(schema.const!==undefined)return <div className="field-group" role="group">
    <strong>{name}</strong><p className="provenance-line">Fixed template discriminator: {String(schema.const)}</p>
  </div>;
  if(effective.type==="object"){
    const current=obj(value);
    return <fieldset className="field-group">
      <legend>{name} {required?"*":""}</legend>
      <div className="field-grid">{Object.entries(effective.properties??{}).map(([k,sub])=>
        <Field key={k} name={k.replaceAll("_"," ")} path={path+"."+k}
          schema={sub} value={current[k]} required={effective.required?.includes(k)??false}
          setup={setup} onChange={next=>onChange({...current,[k]:next})}/>
      )}</div>
    </fieldset>;
  }
  if(effective.type==="array"){
    const rows=Array.isArray(value)?value:[];
    return <fieldset className="field-group span-all">
      <legend>{name} {required?"*":""} · {rows.length} entries</legend>
      <p className="provenance-line">{sourceHint(name,setup)}</p>
      {rows.map((row,i)=><div key={i} className="panel">
        <div className="buttonrow"><strong>Entry {i+1}</strong>
          <button className="quiet" onClick={()=>onChange(rows.filter((_,j)=>j!==i))}>Remove</button></div>
        <Field name={`Entry ${i+1}`} path={path+"."+i} schema={effective.items??{}}
          value={row} required={true} setup={setup}
          onChange={next=>onChange(rows.map((old,j)=>j===i?next:old))}/>
      </div>)}
      <button type="button" onClick={()=>onChange([...rows,emptyValue(effective.items??{})])}>Add entry</button>
    </fieldset>;
  }
  if(effective.type==="boolean")return <div className="field-group">
    <label htmlFor={inputId}>{name}{required?" *":""}</label>
    <input id={inputId} type="checkbox" checked={Boolean(value)} onChange={e=>onChange(e.target.checked)}/>
  </div>;
  const isNumber=effective.type==="integer"||effective.type==="number";
  const strings=(effective.enum??[]).filter((x):x is string=>typeof x==="string");
  const hint=sourceHint(name,setup);
  return <div className="field-group">
    <label htmlFor={inputId}>{name}{required?" *":""}</label>
    {nullable&&<label><input type="checkbox" checked={value==null} onChange={e=>onChange(e.target.checked?null:emptyValue(effective))}/> Not applicable / null</label>}
    {strings.length?<select id={inputId} value={typeof value==="string"?value:""}
      onChange={e=>onChange(e.target.value)} disabled={nullable&&value===null}>
      <option value="">Choose an authorized value</option>
      {strings.map(x=><option value={x} key={x}>{x.replaceAll("_"," ")}</option>)}
    </select>:<input id={inputId} type={isNumber?"number":"text"} value={value??""}
      min={effective.minimum} max={effective.maximum} minLength={effective.minLength}
      step={effective.type==="integer"?1:undefined} disabled={nullable&&value===null}
      onChange={e=>onChange(isNumber?(e.target.value===""?null:Number(e.target.value)):e.target.value)}/>}
    {hint&&<p className="provenance-line">{hint}</p>}
  </div>;
}
export function BlueprintAuthoring({projectId,onBuilt}:{
  projectId:string;onBuilt:()=>Promise<void>;
}){
  const [data,setData]=useState<BlueprintAuthoring|null>(null);
  const [selected,setSelected]=useState("");
  const [drafts,setDrafts]=useState<Record<string,Record<string,unknown>>>({});
  const [raw,setRaw]=useState("");
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
        if(!(setup.setup_id in next))next[setup.setup_id]=setup.payload??{template_id:setup.template_id};
      return next;
    });
  },[projectId]);
  useEffect(()=>{setDrafts({});setData(null);setError("");setNotice("");void reload().catch(e=>setError(errorText(e)));},[reload]);
  const setup=data?.setups.find(x=>x.setup_id===selected);
  const payload=setup?drafts[setup.setup_id]??{template_id:setup.template_id}:{};
  useEffect(()=>{setRaw(JSON.stringify(payload,null,2));},[selected]);
  async function run(label:string,fn:()=>Promise<void>){
    if(busy)return;setBusy(label);setError("");setNotice("");
    try{await fn();setNotice(label+" completed against the exact persisted source.");}
    catch(e){setError(errorText(e));}
    finally{setBusy("");}
  }
  function save(){
    if(!data||!setup)return;
    void run("Save typed setup",async()=>{
      await storyboardApi.savePayload(projectId,setup.setup_id,data.project_revision,
        data.story_sha256,payload,crypto.randomUUID());
      setDrafts(previous=>({...previous,[setup.setup_id]:payload}));
      await reload();
    });
  }
  function compile(){
    if(!data)return;
    void run("Compile real G4 draft",async()=>{
      await storyboardApi.compile(projectId,data.project_revision,data.story_sha256,crypto.randomUUID());
      await onBuilt();await reload();
    });
  }
  return <section className="blueprint-authoring" aria-label="typed-blueprint-authoring">
    <div className="panel">
      <h3>Prepare storyboard · typed G1-directed visual setups</h3>
      <p>Supply historically verified fields for each T01–T10 setup. Every required field is editable using bounded controls; advanced JSON is optional inspection only. This is not a G4 approval.</p>
      {error&&<p role="alert" className="notice error">{error}</p>}
      {notice&&<p role="status" className="notice success">{notice}</p>}
      {!data?<p>Loading immutable G1 visual setups…</p>:<>
        <p className="provenance-line">Story SHA {data.story_sha256.slice(0,18)} · {data.setups.filter(x=>x.payload).length}/{data.setups.length} saved · {data.registry_version}</p>
        <label htmlFor="blueprint-setup">Select exact setup and template</label>
        <select id="blueprint-setup" disabled={!!busy} value={selected} onChange={e=>setSelected(e.target.value)}>
          {data.setups.map(item=><option key={item.setup_id} value={item.setup_id}>
            {item.setup_id} · {item.template_id} · {item.payload?"Saved":"Needs fields"}
          </option>)}
        </select>
        {setup&&<>
          <p className="provenance-line">Source section IDs: {setup.section_refs.join(", ")||"none"} ·
            Claim IDs: {setup.claim_refs.join(", ")||"none"} · G3 requirement IDs: {setup.requirement_refs.join(", ")||"none"}
          </p>
          <div className="field-grid">
            {Object.entries((setup.schema.properties??{}) as Record<string,Schema>).map(([k,schema])=>
              <Field key={k} name={k.replaceAll("_"," ")} path={k}
                schema={schema} value={payload[k]} required={setup.schema.required?.includes(k)??false}
                setup={setup} onChange={value=>setDrafts(x=>({...x,[setup.setup_id]:{...payload,[k]:value}}))}/>
            )}
          </div>
          <details><summary>Inspect locked G1 direction and advanced JSON (optional)</summary>
            <pre className="blueprint-schema">{JSON.stringify(setup.direction,null,2)}</pre>
            <label htmlFor="advanced-payload">Advanced payload JSON · strictly validated on server</label>
            <textarea id="advanced-payload" rows={12} spellCheck={false}
              value={raw} onChange={e=>setRaw(e.target.value)}/>
            <button onClick={()=>{
              try{const parsed:unknown=JSON.parse(raw);
                if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))throw Error("Payload must be an object");
                setDrafts(x=>({...x,[setup.setup_id]:parsed as Record<string,unknown>}));
                setError("");}catch(e){setError(errorText(e));}
              }}>Apply advanced JSON to typed fields</button>
          </details>
          <div className="buttonrow">
            <button className="primary" disabled={!!busy} onClick={save}>Validate & save this setup</button>
            <button disabled={!!busy} onClick={()=>void run("Reload source",reload)}>Reload authoritative source</button>
          </div>
        </>}
        <MapAuthoring projectId={projectId} onRevision={async()=>{await reload();await onBuilt();}}/>
        <button disabled={!!busy||!data.ready} onClick={compile}>
          Compile from current G1/G2/G3 and verified alignment
        </button>
        {!data.ready&&<p>Compile blocked: at least one setup is not yet validated/saved.</p>}
      </>}
    </div>
  </section>;
}
