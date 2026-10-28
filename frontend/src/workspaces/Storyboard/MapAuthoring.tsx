import {useEffect,useMemo,useState} from "react";
import {storyboardApi,type MapAuthoringView,type ReviewedMapInput} from "../../api/storyboard";
import {ApiError} from "../../api/client";

type EvidencePoint={u:number|null;v:number|null;lon:number|null;lat:number|null;user_approved:boolean};
type EvidenceLabel={label_id:string;text:string;feature_id:string|null;lon:number|null;lat:number|null};
const errorText=(e:unknown)=>e instanceof ApiError?
  `${e.problem.code} · ${e.problem.entity_id??"/"}: ${e.problem.message} — ${e.problem.remediation}`:
  e instanceof Error?e.message:String(e);
const list=(v:string)=>v.split(",").map(x=>x.trim()).filter(Boolean);
const asArray=(v:unknown):Record<string,unknown>[]=>Array.isArray(v)?v.filter(x=>x&&typeof x==="object"):[];
const number=(v:unknown)=>typeof v==="number"&&Number.isFinite(v)?v:null;
const text=(v:unknown)=>typeof v==="string"?v:"";
const numericInput=(v:unknown)=>v==null?"":String(v);
function initial(requirement:MapAuthoringView["requirements"][number]):Record<string,unknown>{
  const source=requirement.approved_source;
  if(requirement.request){
    const existing=requirement.request.map_record;
    // Always use current G3 authority, even if a stale request was saved
    // before the original or approval was replaced.
    const sameSource=existing.source_asset_id===source?.source_asset_id
      && existing.source_original_sha256===source?.source_original_sha256
      && existing.rights_review_record_id===source?.rights_review_record_id;
    return {...existing,user_approved:sameSource&&existing.user_approved===true,
      source_asset_id:source?.source_asset_id??"",
      source_original_sha256:source?.source_original_sha256??"",
      rights_review_record_id:source?.rights_review_record_id??""};
  }
  return {
    schema_version:"HistoricalMap.v1",historical_map_id:"",
    source_asset_id:source?.source_asset_id??"",
    source_original_sha256:source?.source_original_sha256??"",
    rights_review_record_id:source?.rights_review_record_id??"",
    valid_year_from:requirement.start_year,valid_year_to:requirement.end_year,
    geography_mode:"",geometry_format:"",source_crs:"",
    normalized_crs:"EPSG:4326",map_projection:"mercator",
    geography_bbox:{min_lon:null,min_lat:null,max_lon:null,max_lat:null},
    geometry_object_sha256:null,raster_asset_sha256:null,approved_feature_ids:[],
    labels:[],geometry_evidence_url:"",user_approved:false,schematic_disclosure:null,
  };
}

export function MapAuthoring({projectId,onRevision}:{
  projectId:string;onRevision:()=>Promise<void>;
}){
  const [view,setView]=useState<MapAuthoringView|null>(null);
  const [selected,setSelected]=useState("");
  const [draft,setDraft]=useState<Record<string,unknown>>({});
  const [advanced,setAdvanced]=useState("");
  const [year,setYear]=useState("");
  const [renderFeatures,setRenderFeatures]=useState("");
  const [approvedFeaturesText,setApprovedFeaturesText]=useState("");
  const [route,setRoute]=useState("");
  const [tiePoints,setTiePoints]=useState<EvidencePoint[]>([]);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const current=useMemo(()=>view?.requirements.find(r=>r.requirement_id===selected),[view,selected]);
  async function reload(){setView(await storyboardApi.mapAuthoring(projectId));}
  useEffect(()=>{setView(null);setSelected("");setError("");setNotice("");
    void reload().catch(e=>setError(errorText(e)));},[projectId]);
  useEffect(()=>{
    if(!current){setDraft({});setAdvanced("");return;}
    const value=initial(current);
    setDraft(value);setAdvanced(JSON.stringify(value,null,2));
    setYear(String(current.request?.year??current.start_year));
    setRenderFeatures(current.request?.feature_ids.join(", ")??"");
    setApprovedFeaturesText(Array.isArray(value.approved_feature_ids)?
      value.approved_feature_ids.join(", "):"");
    setRoute(current.request?.route_feature_id??"");
    setTiePoints(asArray(current.request?.reviewed_tie_points).map(p=>({
      u:number(p.u),v:number(p.v),lon:number(p.lon),lat:number(p.lat),
      user_approved:p.user_approved===true
    })));
  },[current]);
  function patch(key:string,value:unknown){setDraft(d=>({...d,[key]:value}));}
  function patchBounds(key:string,value:number|null){
    setDraft(d=>({...d,geography_bbox:{...(d.geography_bbox as Record<string,unknown>??{}),[key]:value}}));
  }
  const source=current?.approved_source;
  const bbox=draft.geography_bbox as Record<string,unknown>|undefined;
  // Keep raw typing separate: stripping trailing commas on each keystroke
  // prevents the operator from entering a second reviewed feature ID.
  const approvedFeatureIds=list(approvedFeaturesText);
  const labels:EvidenceLabel[]=asArray(draft.labels).map(label=>({
    label_id:text(label.label_id),text:text(label.text),
    feature_id:label.feature_id==null?null:text(label.feature_id),
    lon:number(label.lon),lat:number(label.lat)
  }));
  const isRaster=draft.geography_mode==="raster_georeferenced";
  function setMapMode(mode:string){
    setDraft(d=>({...d,geography_mode:mode,
      geometry_format:mode==="raster_georeferenced"?"RASTER":d.geometry_format==="RASTER"?"":d.geometry_format,
      raster_asset_sha256:mode==="raster_georeferenced"?(source?.source_original_sha256??null):null}));
  }
  async function save(){
    if(!view||!current||busy)return;
    setBusy(true);setError("");setNotice("");
    try{
      if(!source||view.g3_state!=="APPROVED")
        throw Error("G3_APPROVAL_REQUIRED · Approve the current G3 historical map original first.");
      const y=Number(year);
      if(!Number.isInteger(y)||y<current.start_year||y>current.end_year)
        throw Error("MAP_PERIOD_MISMATCH · Select a year from the frozen G1 requirement.");
      if(!text(draft.historical_map_id).trim()||!text(draft.geometry_evidence_url).startsWith("https://"))
        throw Error("MAP_EVIDENCE_REQUIRED · Provide the map ID and a reviewed HTTPS geometry evidence URL.");
      if(draft.user_approved!==true)
        throw Error("MAP_RIGHTS_UNREVIEWED · Confirm independent geographic and source review.");
      if(!bbox||["min_lon","min_lat","max_lon","max_lat"].some(k=>number(bbox[k])===null))
        throw Error("MAP_GEOMETRY_INVALID · Enter all four reviewed geography bounds.");
      const left=bbox.min_lon as number,right=bbox.max_lon as number;
      const lower=bbox.min_lat as number,upper=bbox.max_lat as number;
      if(left>=right||lower>=upper||left< -180||right>180||lower< -90||upper>90)
        throw Error("MAP_GEOMETRY_INVALID · Reviewed bbox must have valid WGS84 min/max coordinates.");
      const validatedPoints=tiePoints.map(p=>{
        if([p.u,p.v,p.lon,p.lat].some(v=>v===null)||!p.user_approved)
          throw Error("MAP_GEOREFERENCE_REQUIRED · Approve all four coordinates of each raster tie point.");
        return {...p,source_original_sha256:source.source_original_sha256,
          rights_review_record_id:source.rights_review_record_id};
      });
      const record={
        ...draft,
        schema_version:"HistoricalMap.v1",
        normalized_crs:"EPSG:4326",
        source_asset_id:source.source_asset_id,
        source_original_sha256:source.source_original_sha256,
        rights_review_record_id:source.rights_review_record_id,
        raster_asset_sha256:isRaster?source.source_original_sha256:null,
        approved_feature_ids:approvedFeatureIds,
      };
      const body:ReviewedMapInput={
        expected_revision:view.project_revision,story_sha256:view.story_sha256,year:y,
        map_record:record,feature_ids:list(renderFeatures),
        route_feature_id:route||null,
        reviewed_tie_points:isRaster&&validatedPoints.length?validatedPoints:null,
      };
      await storyboardApi.saveMap(projectId,current.requirement_id,body,crypto.randomUUID());
      setNotice("Map request passed current G3 original SHA, rights event, G1 year and geometry ingest; not G4 approved.");
      await onRevision();await reload();
    }catch(e){setError(errorText(e));}finally{setBusy(false);}
  }
  return <details className="panel map-authoring" aria-label="historical-map-authoring">
    <summary>Historical map · review exact source and geography</summary>
    <p>Only a current G3-approved original may authorize geography. The coordinates and features below must come from independent period evidence; no modern map or synthetic boundary is inserted.</p>
    {error&&<p role="alert" className="notice error">{error}</p>}
    {notice&&<p role="status" className="notice success">{notice}</p>}
    {!view?<p role="status">Checking approved historical map requirements…</p>:<>
      <p className="provenance-line">G3 {view.g3_state} · Story SHA {view.story_sha256.slice(0,16)} · Revision {view.project_revision}</p>
      <label htmlFor="map-requirement">G1 historical map requirement</label>
      <select id="map-requirement" value={selected} onChange={e=>setSelected(e.target.value)} disabled={busy}>
        <option value="">Select a historical map requirement</option>
        {view.requirements.map(r=><option value={r.requirement_id} key={r.requirement_id}>
          {r.requirement_id} · {r.start_year}–{r.end_year} · {r.approved_source?"G3 source current":"G3 source required"}
        </option>)}
      </select>
      {!view.requirements.length&&<p>This Story has no historical map requirements.</p>}
      {current&&<>
        <div className="field-group"><strong>Exact G3-reviewed original</strong>
          {source?<p className="provenance-line">Candidate {source.source_asset_id}<br/>
            Original SHA {source.source_original_sha256}<br/>
            Rights approval {source.rights_review_record_id}</p>:
            <p role="alert">No currently G3-approved original for this requirement. Resolve and review it in Historical Assets before map authoring.</p>}
          <p className="provenance-line">G1 reconstruction policy: {current.map_reconstruction_policy}</p>
        </div>
        <fieldset disabled={busy||!source||view.g3_state!=="APPROVED"}>
          <div className="field-grid">
            <div><label htmlFor="map-record-id">Unique historical map ID</label>
              <input id="map-record-id" value={text(draft.historical_map_id)}
                onChange={e=>patch("historical_map_id",e.target.value)}/></div>
            <div><label htmlFor="map-year">G1 event year</label>
              <input id="map-year" type="number" min={current.start_year} max={current.end_year}
                value={year} onChange={e=>setYear(e.target.value)}/></div>
            <div><label htmlFor="map-valid-from">Source valid from year</label>
              <input id="map-valid-from" type="number" value={numericInput(draft.valid_year_from)}
                onChange={e=>patch("valid_year_from",e.target.value===""?null:Number(e.target.value))}/></div>
            <div><label htmlFor="map-valid-to">Source valid through year</label>
              <input id="map-valid-to" type="number" value={numericInput(draft.valid_year_to)}
                onChange={e=>patch("valid_year_to",e.target.value===""?null:Number(e.target.value))}/></div>
            <div><label htmlFor="map-geography-mode">Reviewed geography mode</label>
              <select id="map-geography-mode" value={text(draft.geography_mode)} onChange={e=>setMapMode(e.target.value)}>
                <option value="">Select from actual evidence</option>
                <option value="vector_period">Source vector geography</option>
                <option value="raster_georeferenced">Reviewed raster georeference</option>
                <option value="schematic_approved">Explicitly disclosed schematic</option>
              </select></div>
            <div><label htmlFor="map-geometry-format">Actual stored original format</label>
              <select id="map-geometry-format" value={text(draft.geometry_format)}
                disabled={isRaster} onChange={e=>patch("geometry_format",e.target.value)}>
                <option value="">Select verified original format</option>
                <option value="GeoJSON">GeoJSON</option>
                <option value="GPKG_DERIVED_GEOJSON">GPKG-derived GeoJSON</option>
                <option value="RASTER">RASTER</option>
              </select></div>
            <div><label htmlFor="map-source-crs">Source coordinate reference system</label>
              <input id="map-source-crs" value={text(draft.source_crs)}
                onChange={e=>patch("source_crs",e.target.value)} placeholder="e.g. EPSG:4326 only when documented"/></div>
            <div><label htmlFor="map-projection">Display projection</label>
              <select id="map-projection" value={text(draft.map_projection)}
                onChange={e=>patch("map_projection",e.target.value)}>
                <option value="mercator">Mercator</option>
                <option value="equal_earth">Equal Earth</option>
                <option value="equirectangular">Equirectangular</option>
              </select></div>
            <div className="span-all"><label htmlFor="map-evidence-url">Evidence URL for period geometry</label>
              <input id="map-evidence-url" type="url" value={text(draft.geometry_evidence_url)}
                onChange={e=>patch("geometry_evidence_url",e.target.value)}
                placeholder="https:// — source supporting actual period geometry"/></div>
            <div className="span-all"><label htmlFor="map-schematic-disclosure">Schematic disclosure (mandatory for schematics)</label>
              <textarea id="map-schematic-disclosure" value={text(draft.schematic_disclosure)}
                onChange={e=>patch("schematic_disclosure",e.target.value.trim()?e.target.value:null)} rows={2}/></div>
          </div>
          <fieldset className="field-group">
            <legend>Reviewed geographic bounding box · WGS84</legend>
            <div className="field-grid">{(["min_lon","min_lat","max_lon","max_lat"] as const).map(k=>
              <div key={k}><label htmlFor={"map-"+k}>{k.replace("_"," ").toUpperCase()}</label>
                <input id={"map-"+k} type="number" step="any" value={numericInput(bbox?.[k])}
                  onChange={e=>patchBounds(k,e.target.value===""?null:Number(e.target.value))}/></div>)}
            </div>
          </fieldset>
          <div className="field-group">
            <label htmlFor="map-approved-features">Feature IDs reviewed on actual period source</label>
            <input id="map-approved-features" value={approvedFeaturesText}
              onChange={e=>setApprovedFeaturesText(e.target.value)}
              placeholder="Comma separated, exact feature IDs; empty for raster"/>
            <label htmlFor="map-render-features">Subset of approved features to render</label>
            <input id="map-render-features" value={renderFeatures}
              onChange={e=>setRenderFeatures(e.target.value)}
              placeholder="Exact reviewed IDs"/>
            <label htmlFor="map-route">Route feature (only if actual LineString present)</label>
            <select id="map-route" value={route} onChange={e=>setRoute(e.target.value)}>
              <option value="">No geographic route</option>
              {approvedFeatureIds.map(id=><option key={id} value={id}>{id}</option>)}
            </select>
            <label htmlFor="map-geometry-sha">Reviewed normalized geometry SHA (if already known)</label>
            <input id="map-geometry-sha" value={text(draft.geometry_object_sha256)}
              onChange={e=>patch("geometry_object_sha256",e.target.value||null)}
              placeholder="Optional — backend verifies derived geometry if supplied"/>
          </div>
          <fieldset className="field-group">
            <legend>Period map labels · reviewed feature/text/coordinates</legend>
            {labels.map((label,i)=><div className="panel" key={i}>
              <div className="field-grid">
                {(["label_id","text","feature_id","lon","lat"] as const).map(k=>
                  <div key={k}><label>{k}
                    <input type={k==="lon"||k==="lat"?"number":"text"} step="any"
                      value={numericInput(k==="lon"||k==="lat"?label[k]:text(label[k]))}
                      onChange={e=>{
                        const value=(k==="lon"||k==="lat")?(e.target.value===""?null:Number(e.target.value)):(e.target.value||null);
                        patch("labels",labels.map((v,j)=>i===j?{...v,[k]:value}:v));
                      }}/></label></div>)}
              </div>
              <button type="button" onClick={()=>patch("labels",labels.filter((_,j)=>i!==j))}>Remove label</button>
            </div>)}
            <button type="button" onClick={()=>patch("labels",[...labels,{label_id:"",text:"",feature_id:null,lon:null,lat:null}])}>Add reviewed label</button>
          </fieldset>
          {isRaster&&<fieldset className="field-group">
            <legend>Raster UV ↔ historical geography tie points</legend>
            <p>At least three independently reviewed, noncollinear points are required for geographic raster coordinates. Each point is bound to the exact G3 original and rights approval on Save.</p>
            {tiePoints.map((p,i)=><div className="panel" key={i}>
              <div className="field-grid">{(["u","v","lon","lat"] as const).map(k=>
                <div key={k}><label>{k}
                  <input type="number" step="any" value={numericInput(p[k])}
                    onChange={e=>setTiePoints(old=>old.map((pt,j)=>j===i?
                      {...pt,[k]:e.target.value===""?null:Number(e.target.value)}:pt))}/></label></div>)}</div>
              <label><input type="checkbox" checked={p.user_approved}
                onChange={e=>setTiePoints(old=>old.map((pt,j)=>j===i?{...pt,user_approved:e.target.checked}:pt))}/>
                I independently reviewed this tie point against period evidence</label>
              <button type="button" onClick={()=>setTiePoints(old=>old.filter((_,j)=>j!==i))}>Remove tie point</button>
            </div>)}
            <button type="button" onClick={()=>setTiePoints(old=>[...old,{u:null,v:null,lon:null,lat:null,user_approved:false}])}>
              Add reviewed raster tie point
            </button>
          </fieldset>}
          <label><input type="checkbox" checked={draft.user_approved===true}
            onChange={e=>patch("user_approved",e.target.checked)}/>
            I verified this historical geography and the original G3 rights evidence.</label>
          <details><summary>Advanced HistoricalMap.v1 JSON inspection / explicit override</summary>
            <p>Source SHA, candidate and approval identities will always be replaced by current G3 values at Save. Raw JSON is not the primary authoring interface.</p>
            <button type="button" onClick={()=>setAdvanced(JSON.stringify(draft,null,2))}>Copy current fields into JSON editor</button>
            <textarea rows={12} value={advanced} spellCheck={false} onChange={e=>setAdvanced(e.target.value)}/>
            <button type="button" onClick={()=>{
              try{const value:unknown=JSON.parse(advanced);
                if(!value||typeof value!=="object"||Array.isArray(value))throw Error("HistoricalMap must be an object");
                const parsed=value as Record<string,unknown>;
                setDraft(parsed);
                setApprovedFeaturesText(Array.isArray(parsed.approved_feature_ids)?
                  parsed.approved_feature_ids.join(", "):"");
                setError("");
              }catch(e){setError(errorText(e));}
            }}>Apply reviewed advanced fields</button>
          </details>
          <button type="button" className="primary" disabled={busy||!draft.user_approved||!text(draft.historical_map_id).trim()}
            onClick={()=>void save()}>{busy?"Verifying current approved original…":"Verify & save period map"}</button>
        </fieldset>
      </>}
    </>}
  </details>;
}
