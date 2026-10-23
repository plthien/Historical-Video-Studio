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
 const [snapshot,setSnapshot]=useState<BrowserPreview|null>(null);
 const [pending,setPending]=useState<string|null>(null);
 const [error,setError]=useState('');
 const [success,setSuccess]=useState('');
 const scene=useMemo(()=>page?.scenes.find(s=>s.scene_id===selected)??null,[page,selected]);
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
 useEffect(()=>{if(scene)setVariant(scene.variant_id);},[scene?.scene_id,scene?.variant_id]);
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
    <h4>Frozen layers / approved sources</h4>
    <div style={{maxHeight:220,overflowY:'auto'}}>
     {scene.layers.map(l=><p key={l.layer_id}><strong>{l.layer_kind}</strong> · {l.layer_id}
       {l.text&&<span> · {l.text}</span>}
       {l.asset_id&&<small> · approved source {l.asset_id}</small>}</p>)}
    </div>
    <h4>Authored motion events</h4>
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
