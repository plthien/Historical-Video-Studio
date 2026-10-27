import {origin,request,type GateDecision} from './client';

const p=encodeURIComponent;
const root=(id:string)=>`/projects/${p(id)}`;
export interface RenderJob {
 schema_version:'RenderJob.v1';render_job_id:string;project_id:string;state:string;
 timeline_sha256:string;audio_sha256:string;output_sha256:string|null;qc_status:string;
 attribution_manifest_sha256:string|null;qc_report_sha256:string|null;error_code:string|null;
 retry_count:number;attempt_id:string;render_input_manifest_sha256:string;
 progress:{frames_processed:number;total_frames:number};logs:string[];g5_approval_id:string|null;
 export:ExportResult|null;
}
export interface ReviewSession {review_session_id:string;nonce:string;candidate_sha256:string;}
export interface ExportResult {export_id:string;render_job_id:string;mp4_artifact_id:string;
 credits_artifact_id:string;manifest_artifact_id:string;qc_report_sha256:string;}
export const deliveryApi={
 prepareG4(id:string,revision:number,key:string){return request<{candidate_sha256:string;dependency_fingerprint:string;project_revision:number}>(
  root(id)+'/storyboard/candidate','POST',{expected_revision:revision},key);},
 decide(id:string,gate:'G4'|'G5',body:GateDecision,key:string){return request<{approval_id:string;project_revision:number;state:string}>(
  root(id)+`/gates/${gate}/decision`,'POST',body,key);},
 start(id:string,revision:number,key:string){return request<RenderJob>(root(id)+'/render-jobs','POST',
  {expected_revision:revision,codec:'h264',container:'mp4'},key);},
 read(id:string,job:string){return request<RenderJob>(root(id)+`/render-jobs/${p(job)}`);},
 cancel(job:string,key:string){return request<unknown>(`/jobs/${p(job)}/cancel`,'POST',undefined,key);},
 retry(id:string,job:RenderJob,revision:number,key:string){return request<RenderJob>(root(id)+'/render-jobs/retry','POST',
  {expected_revision:revision,approved_timeline_sha256:job.timeline_sha256,codec:'h264',container:'mp4'},key);},
 credits(id:string){return request<{assets:unknown[]}>(root(id)+'/attributions');},
 startReview(id:string,job:string,key:string){return request<ReviewSession>(root(id)+`/render-jobs/${p(job)}/review-sessions`,'POST',undefined,key);},
 heartbeat(id:string,session:ReviewSession,revision:number,position:number,playingVideo:boolean,playingWithAudio:boolean,key:string){return request<{viewed_seconds:number;listened_seconds:number}>(
  root(id)+`/review-sessions/${p(session.review_session_id)}/heartbeat`,'POST',
  {expected_revision:revision,nonce:session.nonce,position_seconds:position,playing_video:playingVideo,playing_with_audio:playingWithAudio},key);},
 completeReview(id:string,session:ReviewSession,key:string){return request<{completed:true;candidate_sha256:string}>(
  root(id)+`/review-sessions/${p(session.review_session_id)}/complete`,'POST',{nonce:session.nonce},key);},
 export(id:string,revision:number,approval:string,job:string,key:string){return request<ExportResult>(root(id)+'/delivery/export','POST',
  {expected_revision:revision,gate_g5_approval_id:approval,render_job_id:job,include_attribution:true},key);},
 media(id:string,job:string){return `${origin}${root(id)}/render-jobs/${p(job)}/media`;},
 artifact(id:string,artifact:string){return `${origin}${root(id)}/delivery/artifacts/${p(artifact)}`;}
};
