import {useCallback,useEffect,useMemo,useState} from 'react';
import {ApiError} from '../../api/client';
import {storyboardApi,type ScenePage,type BrowserPreview,type StoryboardScene} from '../../api/storyboard';
import {RemotionPreview} from '../../components/RemotionPreview';

function describe(error:unknown){
 if(error instanceof ApiError)return `${error.status} ${error.problem.code}: ${error.problem.message} — ${error.problem.remediation}`;
 return error instanceof Error?error.message:'Local storyboard operation failed';
}
export function StoryboardStudio({projectId,onRefresh}:{projectId:string;onRefresh:()=>Promise<void>}){
 const [page,setPage]=useState<ScenePage|null>(null);
 const [offset,setOffset]=useState(0);
 const [selected,setSelected]=useState<string|null>(null);
 const [variant,setVariant]=useState('A');
 const [layerId,setLayerId]=useState<string>('');
 const [layerX,setLayerX]=useState<number>(0);
 const [layerY,setLayerY]=useState<number>(0);
 const [cropX,setCropX]=useState<number>(0);
 const [cropY,setCropY]=useState<number>(0);
 const [cropW,setCropW]=useState<number>(1);
 const [cropH,setCropH]=useState<number>(1);
 const [motionEventId,setMotionEventId]=useState('');
 const [motionKey,setMotionKey]=useState('');
 const [motionValue,setMotionValue]=useState<string|number|boolean>('');
 const [stageOp,setStageOp]=useState('');
 const [snapshot,setSnapshot]=useState<BrowserPreview|null>(null);
 const [pending,setPending]=useState<string|null>(null);
 const [error,setError]=useState('');
 const [success,setSuccess]=useState('');
 const scene=useMemo(()=>page?.scenes.find(s=>s.scene_id===selected)??null,[page,selected]);
 const selectedLayer=useMemo(()=>scene?.layers.find(l=>l.layer_id===layerId)??null,[scene,layerId]);
 const motionEvent=useMemo(()=>scene?.events.find(event=>event.event_id===motionEventId)??null,[scene,motionEventId]);
 const editableMotionKeys=useMemo(()=>motionEvent?Object.entries(motionEvent.params).filter(([key])=>
   !key.endsWith('_id')&&!key.endsWith('_ids')&&!key.includes('sha')&&!key.includes('claim')&&!key.includes('word')&&
   !key.includes('geometry')&&!key.includes('map')&&!key.includes('era')):[],[motionEvent]);
 const load=useCallback(async (nextOffset:number,preferred?:string)=>{
   const result=await storyboardApi.scenes(projectId,nextOffset,24);
   setPage(result);setOffset(nextOffset);
   setSelected(old=>preferred??(result.scenes.some(s=>s.scene_id===old)?old:result.scenes[0]?.scene_id??null));
 },[projectId]);
 useEffect(()=>{
   let live=true;
   storyboardApi.scenes(projectId,0,24).then(result=>{
     if(!live)return;
     setPage(result);setOffset(0);setSelected(result.scenes[0]?.scene_id??null);
   }).catch(e=>{if(live)setError(describe(e));});
   return ()=>{live=false;};
 },[projectId]);
 useEffect(()=>{
   if(scene){setVariant(scene.variant_id);
    setLayerId(scene.layers[0]?.layer_id??'');
   }
 },[scene?.scene_id,scene?.variant_id]);
 useEffect(()=>{
   if(selectedLayer){setLayerX(selectedLayer.rect_px.x);setLayerY(selectedLayer.rect_px.y);
    setCropX(selectedLayer.crop_normalized.x);setCropY(selectedLayer.crop_normalized.y);
    setCropW(selectedLayer.crop_normalized.w);setCropH(selectedLayer.crop_normalized.h);}
 },[selectedLayer?.layer_id,selectedLayer?.rect_px.x,selectedLayer?.rect_px.y,
    selectedLayer?.crop_normalized.x,selectedLayer?.crop_normalized.y,
    selectedLayer?.crop_normalized.w,selectedLayer?.crop_normalized.h]);
 useEffect(()=>{setStageOp(scene?.direction_beats[0]?.staging[0]?.operation??'');},
   [scene?.scene_id,scene?.direction_beats[0]?.staging[0]?.operation]);
 useEffect(()=>{const event=scene?.events.find(item=>Object.entries(item.params).some(([key])=>
   !key.endsWith('_id')&&!key.endsWith('_ids')&&!key.includes('sha')&&!key.includes('claim')&&!key.includes('word')&&!key.includes('geometry')&&!key.includes('map')&&!key.includes('era')));
   setMotionEventId(event?.event_id??'');
 },[scene?.scene_id]);
 useEffect(()=>{const first=editableMotionKeys[0];setMotionKey(first?.[0]??'');setMotionValue(first?.[1]??'');},[motionEventId,scene?.scene_id]);
 async function operation(label:string,run:()=>Promise<void>){
   if(pending)return;
   setPending(label);setError('');setSuccess('');
   try{await run();setSuccess(label+' completed and read back from persisted G4 draft.');}
   catch(e){
     setError(describe(e));
     if(e instanceof ApiError&&e.status===409){
       try{await load(offset,selected??undefined);await onRefresh();}catch{/* Retain conflict */ }
     }
   }finally{setPending(null);}
 }
 const currentSource=page?.draft_manifest_sha256;
 return <div className="stack" aria-label="storyboard-editor">
  <p>Real G4 storyboard draft · source and voice locked. G4/G5 revisions require explicit operator edits; preview does not approve or export a video.</p>
  {error&&<p role="alert" className="notice error">{error}</p>}
  {success&&<p role="status" className="notice success">{success}</p>}
  {!page&&<div className="panel" role="status">Loading current immutable G4 draft. G1/G2/G3 approval, G2 word map and G4 compilation are required.</div>}
  {page&&<>
   <div className="panel">
    <h3>Scenes ({page.total})</h3>
    <small>Revision {page.project_revision} · {page.status} · manifest {currentSource?.slice(0,16)}</small>
    <div className="buttonrow">
     <button disabled={offset===0||!!pending} onClick={()=>void operation('Previous scenes',()=>load(Math.max(0,offset-24)))}>Previous 24</button>
     <button disabled={offset+24>=page.total||!!pending} onClick={()=>void operation('Next scenes',()=>load(offset+24))}>Next 24</button>
     <button disabled={!!pending} onClick={()=>void operation('Reload',async()=>{await load(offset,selected??undefined);setSnapshot(null);await onRefresh();})}>Reload persisted draft</button>
    </div>
    <div role="listbox" aria-label="Storyboard scenes" style={{maxHeight:300,overflowY:'auto',display:'grid',gap:6}}>
     {page.scenes.map((s:StoryboardScene)=><button type="button" key={s.scene_id} role="option"
       aria-selected={selected===s.scene_id} onClick={()=>setSelected(s.scene_id)}
       style={{textAlign:'left'}}>
       <strong>{s.scene_id}</strong> · {s.template_id}/{s.variant_id} · frame {s.start_frame}–{s.start_frame+s.duration_frames-1}
     </button>)}
    </div>
   </div>
   {scene&&<section className="panel" aria-label="Scene inspector">
    <h3>Scene inspector — {scene.scene_id}</h3>
    <p>Setup {scene.setup_id} · {scene.layers.length} frozen layers · {scene.events.length} motion events</p>
    <label htmlFor="sb-variant">Registered presentation variant</label>
    <select id="sb-variant" value={variant} onChange={e=>setVariant(e.target.value)} disabled={!!pending}>
     {['A','B','C'].map(v=><option key={v} value={v}>{scene.template_id}.{v}</option>)}
    </select>
    <button type="button" disabled={!!pending||variant===scene.variant_id}
      onClick={()=>void operation('Save storyboard variant',async()=>{
        await storyboardApi.variant(projectId,scene.scene_id,variant,page.project_revision,crypto.randomUUID());
        await load(offset,scene.scene_id);setSnapshot(null);await onRefresh();
      })}>{pending==='Save storyboard variant'?'Saving…':'Save G4 revision (G4/G5 stale)'}</button>
    <h4>Presentation geometry — frozen layer source</h4>
    <label htmlFor="sb-layer">Layer to reposition</label>
    <select id="sb-layer" value={layerId} onChange={e=>setLayerId(e.target.value)}>
      {scene.layers.map(l=><option key={l.layer_id} value={l.layer_id}>{l.layer_kind} · {l.layer_id}</option>)}
    </select>
    <label htmlFor="sb-layer-x">X (pixels)</label>
    <input type="number" id="sb-layer-x" value={layerX} min={0} max={1919}
      onChange={e=>setLayerX(Number(e.target.value))}/>
    <label htmlFor="sb-layer-y">Y (pixels)</label>
    <input type="number" id="sb-layer-y" value={layerY} min={0} max={1079}
      onChange={e=>setLayerY(Number(e.target.value))}/>
    <button disabled={!!pending||!selectedLayer||
      (selectedLayer.rect_px.x===layerX&&selectedLayer.rect_px.y===layerY)}
      onClick={()=>void operation('Save layer position',async()=>{
        if(!selectedLayer)return;
        await storyboardApi.geometry(projectId,scene.scene_id,selectedLayer.layer_id,
          {x_px:layerX,y_px:layerY},page.project_revision,crypto.randomUUID());
        await load(offset,scene.scene_id);setSnapshot(null);await onRefresh();
      })}>Save position (G4/G5 stale)</button>
    <h4>Normalized crop — same approved original</h4>
    <div className="buttonrow">
      <label>X <input aria-label="Crop X" type="number" min={0} max={1} step={0.01} value={cropX} onChange={e=>setCropX(Number(e.target.value))}/></label>
      <label>Y <input aria-label="Crop Y" type="number" min={0} max={1} step={0.01} value={cropY} onChange={e=>setCropY(Number(e.target.value))}/></label>
      <label>W <input aria-label="Crop width" type="number" min={0.01} max={1} step={0.01} value={cropW} onChange={e=>setCropW(Number(e.target.value))}/></label>
      <label>H <input aria-label="Crop height" type="number" min={0.01} max={1} step={0.01} value={cropH} onChange={e=>setCropH(Number(e.target.value))}/></label>
    </div>
    <button disabled={!!pending||!selectedLayer||
      (selectedLayer.crop_normalized.x===cropX&&selectedLayer.crop_normalized.y===cropY&&selectedLayer.crop_normalized.w===cropW&&selectedLayer.crop_normalized.h===cropH)}
      onClick={()=>void operation('Save normalized crop',async()=>{
        if(!selectedLayer)return;
        await storyboardApi.crop(projectId,scene.scene_id,selectedLayer.layer_id,{x:cropX,y:cropY,w:cropW,h:cropH},page.project_revision,crypto.randomUUID());
        await load(offset,scene.scene_id);setSnapshot(null);await onRefresh();
      })}>Save crop (G4/G5 stale)</button>
    <h4>Frozen layers / approved sources</h4>
    <div style={{maxHeight:220,overflowY:'auto'}}>
     {scene.layers.map(l=><p key={l.layer_id}><strong>{l.layer_kind}</strong> · {l.layer_id}
       {l.text&&<span> · {l.text}</span>}
       {l.asset_id&&<small> · approved source {l.asset_id}</small>}</p>)}
    </div>
    <h4>Frozen-cue beat staging (G4 presentation only)</h4>
    {scene.direction_beats[0]&&<>
      <p><strong>{scene.direction_beats[0].beat_id}</strong> · {scene.direction_beats[0].shot_goal}</p>
      <label htmlFor="sb-stage-op">First authored staging operation</label>
      <select id="sb-stage-op" value={stageOp} onChange={e=>setStageOp(e.target.value)}>
        {['enter','hold','highlight','exit','reposition','focus','draw_path','reveal_mask'].map(op=>
          <option value={op} key={op}>{op}</option>)}
      </select>
      <button disabled={!!pending||stageOp===scene.direction_beats[0].staging[0]?.operation}
       onClick={()=>void operation('Save authored G4 beat staging',async()=>{
        const first=scene.direction_beats[0];
        const staging=first.staging.map((step,i)=>i===0?{...step,operation:stageOp}:step);
        await storyboardApi.direction(projectId,{
          expected_revision:page.project_revision,
          story_revision_sha256:page.story_revision_sha256,setup_id:scene.setup_id,
          edit_reason:'Operator staging adjustment for '+first.beat_id,
          edits:[{beat_id:first.beat_id,shot_goal:first.shot_goal,focus_move:'none',staging}]
        },crypto.randomUUID());
        await load(offset,scene.scene_id);setSnapshot(null);await onRefresh();
       })}>Save staging (G4/G5 stale)</button>
    </>}
    <h4>Authored motion events</h4>
    {motionEvent&&editableMotionKeys.length>0&&<div className="stack">
      <label htmlFor="sb-motion-event">Authored motion event</label>
      <select id="sb-motion-event" value={motionEventId} onChange={e=>setMotionEventId(e.target.value)}>
       {scene.events.filter(event=>Object.entries(event.params).some(([key])=>!key.endsWith('_id')&&!key.endsWith('_ids')&&!key.includes('sha')&&!key.includes('claim')&&!key.includes('word')&&!key.includes('geometry')&&!key.includes('map')&&!key.includes('era'))).map(event=><option key={event.event_id} value={event.event_id}>{event.preset_id} / {event.event_id}</option>)}
      </select>
      <label htmlFor="sb-motion-param">Authorized scalar presentation parameter</label>
      <select id="sb-motion-param" value={motionKey} onChange={e=>{setMotionKey(e.target.value);setMotionValue(motionEvent.params[e.target.value]??'');}}>
       {editableMotionKeys.map(([key])=><option key={key} value={key}>{key}</option>)}
      </select>
      <input aria-label="Motion parameter value" value={String(motionValue)} onChange={e=>setMotionValue(typeof motionEvent.params[motionKey]==='number'?Number(e.target.value):e.target.value)}/>
      <button disabled={!!pending||!motionKey||motionValue===motionEvent.params[motionKey]} onClick={()=>void operation('Save motion parameter',async()=>{
        await storyboardApi.motion(projectId,scene.scene_id,motionEvent.event_id,motionEvent.preset_id,{[motionKey]:motionValue},page.project_revision,crypto.randomUUID());
        await load(offset,scene.scene_id);setSnapshot(null);await onRefresh();
      })}>Save motion (G4/G5 stale)</button>
    </div>}
    <ul>{scene.events.map(e=><li key={e.event_id}>{e.preset_id} · {e.event_id} · frames {e.start_frame}–{e.start_frame+e.duration_frames}</li>)}</ul>
    <p><small>Source claim/cue identities and G3 asset IDs cannot be overwritten by direct browser props. Unsupported direct layout/motion replacement is rejected by the API.</small></p>
   </section>}
   <button type="button" disabled={!!pending} onClick={()=>void operation('Load verified browser preview',async()=>{
     const result=await storyboardApi.preview(projectId);
     if(result.draft_manifest_sha256!==page.draft_manifest_sha256)
       throw new Error('G4_DRAFT_STALE: reload current G4 after another edit.');
     setSnapshot(result);
   })}>{pending==='Load verified browser preview'?'Verifying host…':'Load real read-only Remotion Player'}</button>
   {snapshot&&<RemotionPreview props={snapshot.props} frame={scene?.start_frame??0}/>}
  </>}
 </div>;
}
