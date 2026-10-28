import {useEffect,useState} from "react";
import {storyboardApi,type MapAuthoringView,type ReviewedMapInput} from "../../api/storyboard";
import {ApiError} from "../../api/client";

function problem(e:unknown){return e instanceof ApiError?`${e.problem.code}: ${e.problem.message} · ${e.problem.remediation}`:e instanceof Error?e.message:String(e);}
export function MapAuthoring({projectId,onRevision}:{
  projectId:string;onRevision:()=>Promise<void>;
}){
  const [view,setView]=useState<MapAuthoringView|null>(null);
  const [selected,setSelected]=useState("");
  const [year,setYear]=useState("");
  const [record,setRecord]=useState("");
  const [features,setFeatures]=useState("");
  const [route,setRoute]=useState("");
  const [tiePoints,setTiePoints]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  async function reload(){setView(await storyboardApi.mapAuthoring(projectId));}
  useEffect(()=>{setView(null);setSelected("");setError("");void reload().catch(e=>setError(problem(e)));},[projectId]);
  const current=view?.requirements.find(x=>x.requirement_id===selected);
  useEffect(()=>{
    const request=current?.request;
    setYear(request?String(request.year):current?String(current.start_year):"");
    setRecord(request?JSON.stringify(request.map_record,null,2):"");
    setFeatures(request?request.feature_ids.join(", "):"");
    setRoute(request?.route_feature_id??"");
    setTiePoints(request?.reviewed_tie_points?JSON.stringify(request.reviewed_tie_points,null,2):"");
  },[current?.requirement_id,current?.request]);
  async function save(){
    if(!view||!current||busy)return;
    setBusy(true);setError("");setNotice("");
    try{
      const parsed:unknown=JSON.parse(record);
      if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))throw Error("HistoricalMap.v1 must be an object.");
      let points:Record<string,unknown>[]|null=null;
      if(tiePoints.trim()){
        const values:unknown=JSON.parse(tiePoints);
        if(!Array.isArray(values)||values.some(v=>!v||typeof v!=="object"||Array.isArray(v)))
          throw Error("Tie points must be an array of explicitly reviewed objects.");
        points=values as Record<string,unknown>[];
      }
      const body:ReviewedMapInput={
        expected_revision:view.project_revision,story_sha256:view.story_sha256,
        year:Number(year),map_record:parsed as Record<string,unknown>,
        feature_ids:features.split(",").map(x=>x.trim()).filter(Boolean),
        route_feature_id:route.trim()||null,reviewed_tie_points:points,
      };
      if(!Number.isInteger(body.year)||body.year<current.start_year||body.year>current.end_year)
        throw Error("MAP_PERIOD_MISMATCH: select a year inside the frozen G1 requirement period.");
      await storyboardApi.saveMap(projectId,current.requirement_id,body,crypto.randomUUID());
      setNotice("The current G3 original, exact rights review, map period and features passed authoritative ingest.");
      await onRevision();await reload();
    }catch(e){setError(problem(e));}
    finally{setBusy(false);}
  }
  return <details className="panel map-authoring" aria-label="historical-map-authoring">
    <summary>Period map source authorization · required for geographic setups</summary>
    <p>Map inputs are checked against the current original bytes and human G3 approval. No modern-map fallback or invented route geometry is generated.</p>
    {error&&<p role="alert" className="notice error">{error}</p>}
    {notice&&<p role="status" className="notice success">{notice}</p>}
    {view&&<>
      <label htmlFor="map-requirement">Historical map requirement</label>
      <select id="map-requirement" value={selected} onChange={e=>setSelected(e.target.value)}>
        <option value="">Select a source-bound requirement</option>
        {view.requirements.map(r=><option value={r.requirement_id} key={r.requirement_id}>
          {r.requirement_id} · {r.start_year}–{r.end_year} · {r.request?"Authorized":"Not authorized"}
        </option>)}
      </select>
      {!view.requirements.length&&<p>This StoryPackage has no historical map requirements.</p>}
      {current&&<>
        <label htmlFor="map-year">Historical year · frozen G1 period</label>
        <input id="map-year" type="number" min={current.start_year} max={current.end_year}
          value={year} onChange={e=>setYear(e.target.value)}/>
        <label htmlFor="map-features">Exact reviewed feature IDs (comma-separated)</label>
        <input id="map-features" value={features} onChange={e=>setFeatures(e.target.value)}
          placeholder="Only features on the reviewed G3 original"/>
        <label htmlFor="map-route">Route LineString feature ID (only for actual geographic routes)</label>
        <input id="map-route" value={route} onChange={e=>setRoute(e.target.value)}
          placeholder="Leave empty when not route-bearing"/>
        <details><summary>Reviewed G3 HistoricalMap.v1 record · original SHA / rights / projection</summary>
          <p>Use provenance from the already approved G3 map. Schema and original bytes are revalidated on Save.</p>
          <label htmlFor="map-record">Exact reviewed HistoricalMap.v1 record</label>
          <textarea id="map-record" rows={12} spellCheck={false} value={record}
            onChange={e=>setRecord(e.target.value)}/>
          <label htmlFor="map-ties">Reviewed raster tie points (optional)</label>
          <textarea id="map-ties" rows={5} spellCheck={false} value={tiePoints} onChange={e=>setTiePoints(e.target.value)}/>
        </details>
        <div className="buttonrow"><button disabled={busy||!record.trim()} onClick={()=>void save()}>
          {busy?"Verifying map…":"Verify and save exact period map"}
        </button></div>
      </>}
    </>}
  </details>;
}
