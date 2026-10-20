import {request} from "./client";
export type VoiceAttempt = {attempt_id:string;section_id:string;story_sha256:string;text_sha256:string;
  audio_sha256:string;raw_audio_sha256:string;provider_id:string;voice_id:string;kind:string;
  source_attempt_id:string|null;selected:boolean;compatible_source:boolean;
  duration_seconds:number;sample_rate:number;sample_count:number;settings:{speed?:number}};
export type SectionHistory = {section_id:string;attempts:VoiceAttempt[];selected_attempt_id:string|null};
export type JobState={job_id:string;state:string;error_code:string|null;retry_count:number};
export type FinalAudio={audio_sha256:string;transcript_sha256:string;duration_samples:number;
  sample_rate:number;selected_attempt_ids:string[];section_offsets:{section_id:string;start_sample:number;end_sample:number}[]};
export type AlignmentStatus={approval_id:string|null;current:boolean;final_audio:FinalAudio|null;
  word_map:{words:{word_id:string;text:string;section_id:string;start_sample:number;end_sample:number}[];anomalies:unknown[]}|null;
  alignment_job:JobState|null;assembly_job:JobState|null;g4_ready_dependency:boolean};
const enc=encodeURIComponent;
const root=(id:string)=>"/projects/"+enc(id)+"/voice";
export const voiceApi={
  attempts:(p:string,s:string)=>request<SectionHistory>(root(p)+"/sections/"+enc(s)+"/attempts"),
  regenerate:(p:string,s:string,body:unknown,k:string)=>request<{job_id:string;state:string}>(
    root(p)+"/sections/"+enc(s)+"/regenerate","POST",body,k),
  correct:(p:string,s:string,body:unknown,k:string)=>request<{project_revision:number}>(
    root(p)+"/sections/"+enc(s)+"/correction","POST",body,k),
  restore:(p:string,s:string,body:unknown,k:string)=>request<{project_revision:number}>(
    root(p)+"/sections/"+enc(s)+"/select-attempt","POST",body,k),
  status:(p:string)=>request<AlignmentStatus>(root(p)+"/alignment"),
  retry:(p:string,body:unknown,k:string)=>request<{job_id:string}>(root(p)+"/alignment/retry","POST",body,k),
  job:(id:string)=>request<JobState>("/jobs/"+enc(id)),
  audio:(p:string,sha:string)=>"http://127.0.0.1:8000/api/v1"+root(p)+"/audio/"+enc(sha)
};
