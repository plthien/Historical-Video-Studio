import {useEffect,useRef,useState} from 'react';
import {api,ApiError,type ProjectInfo} from '../../api/client';
import {deliveryApi,type ExportResult,type RenderJob,type ReviewSession} from '../../api/delivery';

const key=()=>crypto.randomUUID();
const message=(e:unknown)=>e instanceof ApiError?`${e.problem.code}: ${e.problem.remediation}`:e instanceof Error?e.message:'Delivery operation failed';

export function DeliveryStudio({project,onRefresh}:{project:ProjectInfo;onRefresh:()=>Promise<void>}){
 const [job,setJob]=useState<RenderJob|null>(null);const [review,setReview]=useState<ReviewSession|null>(null);
 const [approval,setApproval]=useState<string|null>(null);const [result,setResult]=useState<ExportResult|null>(null);
 const [credits,setCredits]=useState<unknown[]>([]);const [busy,setBusy]=useState<string|null>(null);
 const [notice,setNotice]=useState<string>('');const video=useRef<HTMLVideoElement|null>(null);
 const g4=project.gates.find(g=>g.gate_id==='G4')!;const g5=project.gates.find(g=>g.gate_id==='G5')!;
 useEffect(()=>{let live=true;api.jobs(project.project_id).then(async jobs=>{
  const latest=jobs.find(x=>x.kind==='final_render');if(latest&&live){const loaded=await deliveryApi.read(project.project_id,latest.job_id);setJob(loaded);setResult(loaded.export);}
 }).catch(()=>{});return()=>{live=false};},[project.project_id]);
 async function run(label:string,action:()=>Promise<void>){if(busy)return;setBusy(label);setNotice('');
  try{await action();setNotice(label+' completed.');}catch(e){setNotice(message(e));}finally{setBusy(null);}}
 async function decide(gate:'G4'|'G5'){
  const item=gate==='G4'?g4:g5;if(!item.candidate_sha256||!item.dependency_fingerprint)return;
  const candidateSha=item.candidate_sha256,dependencyFingerprint=item.dependency_fingerprint;
  await run(`Approve ${gate}`,async()=>{const saved=await deliveryApi.decide(project.project_id,gate,{
   decision:'APPROVED',candidate_sha256:candidateSha,dependency_fingerprint:dependencyFingerprint,
   expected_revision:project.project_revision,affected_ids:[],comment:`Explicit ${gate} operator review in Delivery workspace`
  },key());if(gate==='G5')setApproval(saved.approval_id);await onRefresh();});
 }
 async function refreshJob(){if(job)setJob(await deliveryApi.read(project.project_id,job.render_job_id));await onRefresh();}
 return <div className="stack" aria-label="delivery-studio">
  <p>Production delivery uses the exact operator-approved G4 timeline, approved WAV, reviewed assets and pinned Remotion composition.</p>
  {notice&&<p role={notice.includes(':')?'alert':'status'}>{notice}</p>}
  <section className="panel"><h3>G4 production authority</h3><p>Status: <strong>{g4.state}</strong></p>
   <button disabled={!!busy||!['DRAFT','READY_FOR_REVIEW','CHANGES_REQUESTED','REJECTED','STALE'].includes(g4.state)}
    onClick={()=>void run('Prepare G4 candidate',async()=>{await deliveryApi.prepareG4(project.project_id,project.project_revision,key());await onRefresh();})}>Prepare exact G4 review candidate</button>
   <button disabled={!!busy||g4.state!=='READY_FOR_REVIEW'} onClick={()=>void decide('G4')}>Approve inspected G4</button>
  </section>
  <section className="panel"><h3>Full render</h3>
   <button disabled={!!busy||g4.state!=='APPROVED'} onClick={()=>void run('Queue render',async()=>{
    setJob(await deliveryApi.start(project.project_id,project.project_revision,key()));})}>Render full H264 + approved WAV/AAC</button>
   {job&&<><p>{job.state} · {job.progress.frames_processed}/{job.progress.total_frames} frames · QC {job.qc_status}</p>
    {job.error_code&&<p role="alert">{job.error_code}</p>}<button disabled={!!busy} onClick={()=>void run('Refresh render',refreshJob)}>Refresh progress</button>
    {['QUEUED','RUNNING'].includes(job.state)&&<button disabled={!!busy} onClick={()=>void run('Cancel render',async()=>{await deliveryApi.cancel(job.render_job_id,key());await refreshJob();})}>Cancel exact render</button>}
    {job.state==='FAILED_RETRYABLE'&&<button disabled={!!busy} onClick={()=>void run('Retry render',async()=>setJob(await deliveryApi.retry(project.project_id,job,project.project_revision,key())))}>Retry exact approved input</button>}</>}
  </section>
  {job?.state==='SUCCEEDED'&&job.qc_status==='PASS'&&<section className="panel"><h3>G5 audiovisual review</h3>
   <video ref={video} controls src={deliveryApi.media(project.project_id,job.render_job_id)} style={{width:'100%'}}
    onTimeUpdate={()=>{const media=video.current;if(review&&media&&!media.paused)void deliveryApi.heartbeat(project.project_id,review,media.currentTime,true);}}/>
   <button disabled={!!busy||!!review} onClick={()=>void run('Start verified review',async()=>setReview(await deliveryApi.startReview(project.project_id,job.render_job_id,key())))}>Start server-issued view/listen review</button>
   <button disabled={!!busy||!review} onClick={()=>void run('Complete verified review',async()=>{if(!review)return;await deliveryApi.completeReview(project.project_id,review,key());await onRefresh();})}>Confirm complete video and audio review</button>
   <button disabled={!!busy} onClick={()=>void run('Load credits',async()=>setCredits((await deliveryApi.credits(project.project_id)).assets))}>Inspect source credits ({credits.length})</button>
   <p>G5 status: <strong>{g5.state}</strong></p><button disabled={!!busy||g5.state!=='READY_FOR_REVIEW'} onClick={()=>void decide('G5')}>Approve exact G5 render</button>
  </section>}
  {g5.state==='APPROVED'&&job&&<section className="panel"><h3>Immutable export</h3>
   <button disabled={!!busy} onClick={()=>void run('Create export',async()=>{
    const id=approval??job.g5_approval_id;
    if(!id)throw Error('Refresh after G5 approval to obtain approval evidence.');
    /* approval ID is deliberately read from the decision response in this session. */
    setResult(await deliveryApi.export(project.project_id,project.project_revision,id,job.render_job_id,key()));})}>Package approved MP4 + attribution</button>
   {result&&<div><a href={deliveryApi.artifact(project.project_id,result.mp4_artifact_id)}>Download MP4</a>{' · '}
    <a href={deliveryApi.artifact(project.project_id,result.credits_artifact_id)}>Download credits</a>{' · '}
    <a href={deliveryApi.artifact(project.project_id,result.manifest_artifact_id)}>Download render manifest</a></div>}
  </section>}
 </div>;
}
