import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {ApiError} from '../../api/client';
import {storyboardApi,type ScenePage,type BrowserPreview,type StoryboardScene,type AssetOptions} from '../../api/storyboard';
import {RemotionPreview} from '../../components/RemotionPreview';
import {deliveryApi} from '../../api/delivery';
import {BlueprintAuthoring} from './BlueprintAuthoring';

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
 const [layerW,setLayerW]=useState<number>(1);
 const [layerH,setLayerH]=useState<number>(1);
 const [cropX,setCropX]=useState<number>(0);
 const [cropY,setCropY]=useState<number>(0);
 const [cropW,setCropW]=useState<number>(1);
 const [cropH,setCropH]=useState<number>(1);
 const [motionEventId,setMotionEventId]=useState('');
 const [motionKey,setMotionKey]=useState('');
 const [motionValue,setMotionValue]=useState<string|number|boolean>('');
 const [beatId,setBeatId]=useState('');
 const [focusMove,setFocusMove]=useState('none');
 const [stageOp,setStageOp]=useState('');
 const [stageIndex,setStageIndex]=useState(0);
 const [snapshot,setSnapshot]=useState<BrowserPreview|null>(null);
 const [assetOptions,setAssetOptions]=useState<AssetOptions|null>(null);
 const [assetChoice,setAssetChoice]=useState('');
 const [assetLoading,setAssetLoading]=useState(false);
 const [pending,setPending]=useState<string|null>(null);
 const [error,setError]=useState('');
 const [success,setSuccess]=useState('');
 const previewRequest=useRef<{id:number;controller:AbortController}|null>(null);
 const previewSequence=useRef(0);
 const scene=useMemo(()=>page?.scenes.find(s=>s.scene_id===selected)??null,[page,selected]);
 const selectedLayer=useMemo(()=>scene?.layers.find(l=>l.layer_id===layerId)??null,[scene,layerId]);
 const motionEvent=useMemo(()=>scene?.events.find(event=>event.event_id===motionEventId)??null,[scene,motionEventId]);
 const selectedBeat=useMemo(()=>scene?.direction_beats.find(beat=>beat.beat_id===beatId)??null,[scene,beatId]);
 const selectedStage=selectedBeat?.staging[stageIndex]??null;
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
    setLayerW(selectedLayer.rect_px.w);setLayerH(selectedLayer.rect_px.h);
    setCropX(selectedLayer.crop_normalized.x);setCropY(selectedLayer.crop_normalized.y);
    setCropW(selectedLayer.crop_normalized.w);setCropH(selectedLayer.crop_normalized.h);}
 },[selectedLayer?.layer_id,selectedLayer?.rect_px.x,selectedLayer?.rect_px.y,
    selectedLayer?.rect_px.w,selectedLayer?.rect_px.h,
    selectedLayer?.crop_normalized.x,selectedLayer?.crop_normalized.y,
    selectedLayer?.crop_normalized.w,selectedLayer?.crop_normalized.h]);
 useEffect(()=>{
   let live=true;
   setAssetOptions(null);setAssetChoice('');
   if(!scene||!selectedLayer?.asset_id||!selectedLayer.source_asset_slot_id||!page)return;
   setAssetLoading(true);
   storyboardApi.assetOptions(projectId,scene.scene_id,selectedLayer.layer_id).then(result=>{
     if(!live)return;
     if(result.draft_manifest_sha256!==page.draft_manifest_sha256)return;
     setAssetOptions(result);
     setAssetChoice(result.selected_candidate_id);
   }).catch(error=>{if(live)setError(describe(error));})
     .finally(()=>{if(live)setAssetLoading(false);});
   return ()=>{live=false;};
 },[projectId,scene?.scene_id,selectedLayer?.layer_id,
    selectedLayer?.asset_id,selectedLayer?.source_asset_slot_id,page?.draft_manifest_sha256]);
 useEffect(()=>{setBeatId(scene?.direction_beats[0]?.beat_id??'');setStageIndex(0);},[scene?.scene_id]);
 useEffect(()=>{setStageIndex(0);},[selectedBeat?.beat_id]);
 useEffect(()=>{setStageOp(selectedStage?.operation??'');},
   [selectedBeat?.beat_id,stageIndex,selectedStage?.operation]);
 useEffect(()=>{setFocusMove(selectedBeat?.focus_move??'none');},
   [selectedBeat?.beat_id,selectedBeat?.focus_move]);
 useEffect(()=>{const event=scene?.events.find(item=>Object.entries(item.params).some(([key])=>
   !key.endsWith('_id')&&!key.endsWith('_ids')&&!key.includes('sha')&&!key.includes('claim')&&!key.includes('word')&&!key.includes('geometry')&&!key.includes('map')&&!key.includes('era')));
   setMotionEventId(event?.event_id??'');
 },[scene?.scene_id]);
 useEffect(()=>{const first=editableMotionKeys[0];setMotionKey(first?.[0]??'');setMotionValue(first?.[1]??'');},[motionEventId,scene?.scene_id,page?.project_revision]);
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
 const invalidatePreview=useCallback(()=>{
   previewRequest.current?.controller.abort();
   previewRequest.current=null;
   previewSequence.current+=1;
   setSnapshot(null);
 },[]);
 useEffect(()=>()=>previewRequest.current?.controller.abort(),[]);
 const currentSource=page?.draft_manifest_sha256;
 return <div className="stack" aria-label="storyboard-editor">
  <p>Real G4 storyboard draft · source and voice locked. G4/G5 revisions require explicit operator edits; preview does not approve or export a video.</p>
  {!page&&<div className="panel"><p>No compiled storyboard exists yet. Complete the G1-directed setups below and compile against current G1/G2/G3, alignment and map sources.</p>
  <BlueprintAuthoring projectId={projectId} onBuilt={async()=>{setError("");await load(0);await onRefresh();}}/></div>}
  {error&&<p role="alert" className="notice error">{error}</p>}
  {success&&<p role="status" className="notice success">{success}</p>}
  {!page&&<p role="status">No verified storyboard draft yet, or the source is blocked. G1/G2/G3 and G2 word map are required before live Player access.</p>}
  {page&&<>
   <div className="storyboard-workbench">
   <aside className="panel scene-rail" aria-label="Scene navigator">
    <h3>Scenes ({page.total})</h3>
    <small>Revision {page.project_revision} · G4 {page.g4_gate.state} · manifest {currentSource?.slice(0,16)}</small>
    <p>Preview is view-only. Production render authority requires this exact candidate and an explicit operator decision.</p>
    <div className="buttonrow">
     <button disabled={!!pending||page.g4_gate.state==='APPROVED'} onClick={()=>void operation('Prepare G4 review candidate',async()=>{
      await deliveryApi.prepareG4(projectId,page.project_revision,crypto.randomUUID());await load(offset,selected??undefined);await onRefresh();
     })}>Prepare G4 review candidate</button>
     <button disabled={!!pending||page.g4_gate.state!=='READY_FOR_REVIEW'||!page.g4_gate.candidate_sha256||!page.g4_gate.dependency_fingerprint}
      onClick={()=>void operation('Approve inspected G4',async()=>{
       const gate=page.g4_gate;if(!gate.candidate_sha256||!gate.dependency_fingerprint)return;
       await deliveryApi.decide(projectId,'G4',{decision:'APPROVED',candidate_sha256:gate.candidate_sha256,
        dependency_fingerprint:gate.dependency_fingerprint,expected_revision:page.project_revision,
        affected_ids:[],comment:'Explicit operator approval after Storyboard Player inspection'},crypto.randomUUID());
       await load(offset,selected??undefined);await onRefresh();
      })}>Approve inspected G4</button>
    </div>
    <div className="buttonrow">
     <button disabled={offset===0||!!pending} onClick={()=>void operation('Previous scenes',()=>load(Math.max(0,offset-24)))}>Previous 24</button>
     <button disabled={offset+24>=page.total||!!pending} onClick={()=>void operation('Next scenes',()=>load(offset+24))}>Next 24</button>
     <button disabled={!!pending} onClick={()=>void operation('Reload',async()=>{invalidatePreview();await load(offset,selected??undefined);await onRefresh();})}>Reload persisted draft</button>
    </div>
    <div role="listbox" aria-label="Storyboard scenes" style={{maxHeight:300,overflowY:'auto',display:'grid',gap:6}}>
     {page.scenes.map((s:StoryboardScene)=><button type="button" key={s.scene_id} role="option"
       aria-selected={selected===s.scene_id} onClick={()=>setSelected(s.scene_id)}
       style={{textAlign:'left'}}>
       <strong>{s.scene_id}</strong> · {s.template_id}/{s.variant_id} · frame {s.start_frame}–{s.start_frame+s.duration_frames-1}
     </button>)}
    </div>
   </aside>
   <section className="panel stage-panel" aria-label="Real Remotion Player stage">
     <small className="eyebrow">PERSISTED COMPILED SCENE · REAL PLAYER</small>
     <h3>{scene?.scene_id??"Select a scene"}</h3>
     <p className="provenance-line">Manifest {page.draft_manifest_sha256.slice(0,20)} · frame {scene?.start_frame??0}</p>
     <div className="media-stage">
       {snapshot?<RemotionPreview props={snapshot.props} frame={scene?.start_frame??0}/>:
         <div className="stage-empty">No simulated frame. Load verified source-bound Remotion Player below.</div>}
     </div>
        <button type="button" disabled={!!pending} onClick={()=>void operation('Load verified browser preview',async()=>{
     previewRequest.current?.controller.abort();
     const request={id:++previewSequence.current,controller:new AbortController()};
     previewRequest.current=request;
     const expectedManifest=page.draft_manifest_sha256;
     const expectedRevision=page.project_revision;
     const result=await storyboardApi.preview(projectId,request.controller.signal);
     if(previewRequest.current?.id!==request.id)return;
     const latest=await storyboardApi.scenes(projectId,offset,1);
     if(previewRequest.current?.id!==request.id)return;
     if(result.draft_manifest_sha256!==expectedManifest||result.project_revision!==expectedRevision||
        latest.draft_manifest_sha256!==result.draft_manifest_sha256||
        latest.project_revision!==result.project_revision)
       throw new Error('G4_DRAFT_STALE: reload current G4 after another edit.');
     setSnapshot(result);
     previewRequest.current=null;
   })}>{pending==='Load verified browser preview'?'Verifying host…':'Load real read-only Remotion Player'}</button>


   </section>
   {scene&&<section className="panel scene-inspector" aria-label="Scene inspector">
    <h3>Scene inspector — {scene.scene_id}</h3>
    <p>Setup {scene.setup_id} · {scene.layers.length} frozen layers · {scene.events.length} motion events</p>
    <label htmlFor="sb-variant">Registered presentation variant</label>
    <select id="sb-variant" value={variant} onChange={e=>setVariant(e.target.value)} disabled={!!pending}>
     {['A','B','C'].map(v=><option key={v} value={v}>{scene.template_id}.{v}</option>)}
    </select>
    <button type="button" disabled={!!pending||variant===scene.variant_id}
      onClick={()=>void operation('Save storyboard variant',async()=>{
        await storyboardApi.variant(projectId,scene.scene_id,variant,page.project_revision,crypto.randomUUID());
        invalidatePreview();await load(offset,scene.scene_id);await onRefresh();
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
      !Number.isInteger(layerX)||!Number.isInteger(layerY)||layerX<0||layerY<0||
      layerX+selectedLayer.rect_px.w>1920||layerY+selectedLayer.rect_px.h>1080||
      (selectedLayer.rect_px.x===layerX&&selectedLayer.rect_px.y===layerY)}
      onClick={()=>void operation('Save layer position',async()=>{
        if(!selectedLayer)return;
        await storyboardApi.geometry(projectId,scene.scene_id,selectedLayer.layer_id,
          {x_px:layerX,y_px:layerY},page.project_revision,crypto.randomUUID());
        invalidatePreview();await load(offset,scene.scene_id);await onRefresh();
      })}>Save position (G4/G5 stale)</button>
    <h4>Media layer dimensions — unchanged approved source</h4>
    <label htmlFor="sb-layer-w">Width (pixels)</label>
    <input type="number" id="sb-layer-w" min={1} max={1920-layerX}
      value={layerW} disabled={!!pending||!selectedLayer||selectedLayer.text!==null}
      onChange={e=>setLayerW(Number(e.target.value))}/>
    <label htmlFor="sb-layer-h">Height (pixels)</label>
    <input type="number" id="sb-layer-h" min={1} max={1080-layerY}
      value={layerH} disabled={!!pending||!selectedLayer||selectedLayer.text!==null}
      onChange={e=>setLayerH(Number(e.target.value))}/>
    {selectedLayer?.text!=null&&<small>Text box dimensions are fixed by pinned GDI font geometry; resizing requires remeasurement.</small>}
    <button disabled={!!pending||!selectedLayer||selectedLayer.text!==null||
      !Number.isInteger(layerW)||!Number.isInteger(layerH)||layerW<1||layerH<1||
      layerX+layerW>1920||layerY+layerH>1080||
      (layerW===selectedLayer.rect_px.w&&layerH===selectedLayer.rect_px.h)}
      onClick={()=>void operation('Save media dimensions',async()=>{
        if(!selectedLayer)return;
        await storyboardApi.geometry(projectId,scene.scene_id,selectedLayer.layer_id,
          {w_px:layerW,h_px:layerH},page.project_revision,crypto.randomUUID());
        invalidatePreview();await load(offset,scene.scene_id);await onRefresh();
      })}>Save size (G4/G5 stale)</button>
    <h4>Normalized crop — same approved original</h4>
    <div className="buttonrow">
      <label>X <input aria-label="Crop X" type="number" min={0} max={1} step={0.01} value={cropX} onChange={e=>setCropX(Number(e.target.value))}/></label>
      <label>Y <input aria-label="Crop Y" type="number" min={0} max={1} step={0.01} value={cropY} onChange={e=>setCropY(Number(e.target.value))}/></label>
      <label>W <input aria-label="Crop width" type="number" min={0.01} max={1} step={0.01} value={cropW} onChange={e=>setCropW(Number(e.target.value))}/></label>
      <label>H <input aria-label="Crop height" type="number" min={0.01} max={1} step={0.01} value={cropH} onChange={e=>setCropH(Number(e.target.value))}/></label>
    </div>
    <button disabled={!!pending||!selectedLayer||
      ![cropX,cropY,cropW,cropH].every(Number.isFinite)||
      cropX<0||cropY<0||cropW<=0||cropH<=0||cropX+cropW>1||cropY+cropH>1||
      (selectedLayer.crop_normalized.x===cropX&&selectedLayer.crop_normalized.y===cropY&&selectedLayer.crop_normalized.w===cropW&&selectedLayer.crop_normalized.h===cropH)}
      onClick={()=>void operation('Save normalized crop',async()=>{
        if(!selectedLayer)return;
        await storyboardApi.crop(projectId,scene.scene_id,selectedLayer.layer_id,{x:cropX,y:cropY,w:cropW,h:cropH},page.project_revision,crypto.randomUUID());
        invalidatePreview();await load(offset,scene.scene_id);await onRefresh();
      })}>Save crop (G4/G5 stale)</button>
    <h4>Current G3-reviewed same-slot source alternatives</h4>
    {selectedLayer?.source_asset_slot_id&&selectedLayer?.asset_id?
      <div className="stack" aria-label="g4-approved-asset-picker">
        <p>Frozen slot {selectedLayer.source_asset_slot_id}; current source {selectedLayer.asset_id}. G4 changes presentation only and cannot approve new G3 evidence.</p>
        {assetLoading?<p role="status">Checking current G3 pool…</p>:
         assetOptions?.options.length?
          <>
            <label htmlFor="sb-source-option">Eligible same-slot reviewed original</label>
            <select id="sb-source-option" aria-label="Eligible approved source" value={assetChoice}
              disabled={!!pending} onChange={e=>setAssetChoice(e.target.value)}>
              {assetOptions.options.map(option=><option key={option.candidate_id} value={option.candidate_id}>
                {option.title} · {option.candidate_id} · SHA {option.original_sha256.slice(0,12)}
              </option>)}
            </select>
            <small>G3 choice set {assetOptions.choice_set_id} · review SHA {assetOptions.choice_set_sha256?.slice(0,16)}</small>
            <button type="button" disabled={!!pending||!assetChoice||assetChoice===selectedLayer.asset_id||
              assetOptions.project_revision!==page.project_revision}
              onClick={()=>void operation('Save reviewed A/B original',async()=>{
                await storyboardApi.assetChoice(projectId,scene.scene_id,selectedLayer.layer_id,
                  assetChoice,page.project_revision,crypto.randomUUID());
                invalidatePreview();await load(offset,scene.scene_id);await onRefresh();
              })}>Save A/B source (G4/G5 stale)</button>
          </>:
          <p role="note">No current independently G3-approved alternatives for this source slot.</p>}
      </div>:
      <small>Choose a source-backed image layer to inspect eligible G3 alternatives.</small>}
    <h4>Frozen layers / approved sources</h4>
    <div style={{maxHeight:220,overflowY:'auto'}}>
     {scene.layers.map(l=><p key={l.layer_id}><strong>{l.layer_kind}</strong> · {l.layer_id}
       {l.text&&<span> · {l.text}</span>}
       {l.asset_id&&<small> · approved source {l.asset_id}</small>}</p>)}
    </div>
    <h4>Frozen-cue beat staging (G4 presentation only)</h4>
    {selectedBeat&&<>
      <label htmlFor="sb-beat">Authored beat</label>
      <select id="sb-beat" value={beatId} onChange={e=>setBeatId(e.target.value)}>
       {scene.direction_beats.map(beat=><option key={beat.beat_id} value={beat.beat_id}>{beat.beat_id}</option>)}
      </select>
      <label htmlFor="sb-focus-move">Authorized focus movement</label>
      <select id="sb-focus-move" value={focusMove} onChange={e=>setFocusMove(e.target.value)}>
       {['none','subject_to_subject','detail_to_overview','overview_to_detail','follow_path','static']
        .map(move=><option value={move} key={move}>{move}</option>)}
      </select>
      <p><strong>{selectedBeat.beat_id}</strong> · {selectedBeat.shot_goal}</p>
      <label htmlFor="sb-stage-step">Authored staging step</label>
      <select id="sb-stage-step" aria-label="Authored staging step" value={stageIndex} onChange={e=>setStageIndex(Number(e.target.value))}>
        {selectedBeat.staging.map((step,i)=><option key={i} value={i}>Step {i+1} · {step.ref} · priority {step.priority}</option>)}
      </select>
      <label htmlFor="sb-stage-op">Selected authored staging operation</label>
      <select id="sb-stage-op" value={stageOp} onChange={e=>setStageOp(e.target.value)}>
        {['enter','hold','highlight','exit','reposition','focus','draw_path','reveal_mask'].map(op=>
          <option value={op} key={op}>{op}</option>)}
      </select>
      <button disabled={!!pending||!selectedStage||(stageOp===selectedStage.operation&&
        focusMove===selectedBeat.focus_move)}
       onClick={()=>void operation('Save authored G4 beat staging',async()=>{
        const staging=selectedBeat.staging.map((step,i)=>i===stageIndex?{...step,operation:stageOp}:step);
        await storyboardApi.direction(projectId,{
          expected_revision:page.project_revision,
          story_revision_sha256:page.story_revision_sha256,setup_id:scene.setup_id,
          edit_reason:'Operator staging/focus adjustment for '+selectedBeat.beat_id,
          edits:[{beat_id:selectedBeat.beat_id,shot_goal:selectedBeat.shot_goal,focus_move:focusMove,staging}]
        },crypto.randomUUID());
        invalidatePreview();await load(offset,scene.scene_id);await onRefresh();
       })}>Save staging (G4/G5 stale)</button>
    </>}
    <h4>Authored motion events</h4>
     <p>Camera scalars compile into one bounded camera track; frozen source and focus IDs remain locked.</p>
    {motionEvent&&editableMotionKeys.length>0&&<div className="stack">
      <label htmlFor="sb-motion-event">Authored motion event</label>
      <select id="sb-motion-event" value={motionEventId} onChange={e=>setMotionEventId(e.target.value)}>
       {scene.events.filter(event=>Object.entries(event.params).some(([key])=>!key.endsWith('_id')&&!key.endsWith('_ids')&&!key.includes('sha')&&!key.includes('claim')&&!key.includes('word')&&!key.includes('geometry')&&!key.includes('map')&&!key.includes('era'))).map(event=><option key={event.event_id} value={event.event_id}>{event.preset_id} / {event.event_id}</option>)}
      </select>
      <label htmlFor="sb-motion-param">Authorized scalar presentation parameter</label>
      <select id="sb-motion-param" value={motionKey} onChange={e=>{setMotionKey(e.target.value);setMotionValue(motionEvent.params[e.target.value]??'');}}>
       {editableMotionKeys.map(([key])=><option key={key} value={key}>{key}</option>)}
      </select>
      {typeof motionEvent.params[motionKey]==='boolean'?<select aria-label="Motion parameter value" value={String(motionValue)}
        onChange={e=>setMotionValue(e.target.value==='true')}><option value="true">true</option><option value="false">false</option></select>:
       <input aria-label="Motion parameter value" value={String(motionValue)}
        type={typeof motionEvent.params[motionKey]==='number'?'number':'text'}
        onChange={e=>setMotionValue(typeof motionEvent.params[motionKey]==='number'?Number(e.target.value):e.target.value)}/>}
      <button disabled={!!pending||!motionKey||
        (typeof motionValue==='number'&&!Number.isFinite(motionValue))||motionValue===motionEvent.params[motionKey]} onClick={()=>void operation('Save motion parameter',async()=>{
        await storyboardApi.motion(projectId,scene.scene_id,motionEvent.event_id,motionEvent.preset_id,{[motionKey]:motionValue},page.project_revision,crypto.randomUUID());
        invalidatePreview();await load(offset,scene.scene_id);await onRefresh();
      })}>Save motion (G4/G5 stale)</button>
    </div>}
    <ul>{scene.events.map(e=><li key={e.event_id}>{e.preset_id} · {e.event_id} · frames {e.start_frame}–{e.start_frame+e.duration_frames}</li>)}</ul>
    <p><small>Source claim/cue identities and G3 asset IDs cannot be overwritten by direct browser props. Unsupported direct layout/motion replacement is rejected by the API.</small></p>
   </section>}
   </div>
   <details className="panel setup-drawer"><summary>G4 initial authoring / reviewed map requests (edit and rebuild)</summary>
      <BlueprintAuthoring projectId={projectId} onBuilt={async()=>{setError("");await load(0);await onRefresh();}}/>
   </details>
  </>}
 </div>;
}
