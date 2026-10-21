/** A3 local APIs: explicit source decisions and human review, never implicit approvals. */
import {request} from "./client";
const p=encodeURIComponent;
export interface Requirement {
  requirement: Record<string,unknown>; requirement_id:string; status:string; resolution_mode:string;
  operator_authorized:boolean; candidate_count:number; approval_record_id:string|null;
  approved_asset_id:string|null; approved_candidate_sha256:string|null;
}
export interface AssetCandidate {
  candidate_id:string; provider:string; title:string; original_sha256:string|null;
  rights_status:string; rights_statement?:string; asset_class?:string;
  hydrated?:boolean; item_id?:string; mime_type?:string; source_page_url?:string;
  creator?:string|null;creation_date?:string|null;place?:string|null;
  rights_uri?:string|null;historical_exactness?:string|null;historical_context_note?:string|null;
  source_story_sha256?:string; source_requirement_sha256?:string; metadata_sha256?:string;
  current_source:boolean; approved:boolean; user_approved:boolean;
}
export interface AssetReview {
  requirement_id:string; candidate_id:string; original_sha256:string; rights_status:"ELIGIBLE";
  rights_evidence_note:string; historical_context_note:string;
}
export interface ProviderInfo {provider:string;configured:boolean;live_status:string;base_url:string}
export const assetApi={
  requirements:(id:string)=>request<{project_revision:number;requirements:Requirement[]}>("/projects/"+p(id)+"/assets/requirements"),
  candidates:(id:string,rid:string)=>request<{project_revision:number;candidates:AssetCandidate[]}>("/projects/"+p(id)+"/assets/"+p(rid)+"/candidates"),
  choose:(id:string,rid:string,revision:number,mode:"MANUAL_UPLOAD"|"MANAGED_FALLBACK",reason:string)=>
    request<{project_revision:number}>("/projects/"+p(id)+"/assets/"+p(rid)+"/resolve","POST",{expected_revision:revision,resolution_mode:mode,reason},crypto.randomUUID()),
  search:(id:string,revision:number,rid:string,provider:string,query:string,cursor:string|null)=>
    request<{candidate_ids:string[];next_cursor:string|null}>("/projects/"+p(id)+"/assets/search","POST",
      {expected_revision:revision,requirement_id:rid,provider,query,cursor},crypto.randomUUID()),
  hydrate:(id:string,revision:number,rid:string,candidate_id:string)=>
    request<AssetCandidate>("/projects/"+p(id)+"/assets/"+p(rid)+"/hydrate","POST",
      {expected_revision:revision,candidate_id},crypto.randomUUID()),
  previewUrl:(id:string,rid:string,candidate_id:string)=>
    "http://127.0.0.1:8000/api/v1/projects/"+p(id)+"/assets/"+p(rid)+"/candidates/"+p(candidate_id)+"/original-preview",
  original:(id:string,revision:number,rid:string,candidate_id:string)=>
    request<AssetCandidate>("/projects/"+p(id)+"/assets/original","POST",
      {expected_revision:revision,requirement_id:rid,candidate_id},crypto.randomUUID()),
  upload:(id:string,revision:number,rid:string,data_base64:string,title:string,source_note:string,rights_note:string)=>
    request<{candidate:AssetCandidate}>("/projects/"+p(id)+"/assets/"+p(rid)+"/upload","POST",
      {expected_revision:revision,data_base64,title,source_note,rights_note},crypto.randomUUID()),
  batch:(id:string,revision:number,reviews:AssetReview[])=>
    request<{approved:{requirement_id:string;approval_record_id:string}[]}>("/projects/"+p(id)+"/assets/batch-approve","POST",
      {expected_revision:revision,reviews},crypto.randomUUID()),
  providers:()=>request<{providers:ProviderInfo[]}>("/providers"),
  settings:(provider:string,api_key:string|undefined,base_url:string,clear_key=false)=>
    request<{configured:boolean}>("/providers/settings","PUT",
      {provider,api_key:api_key||null,base_url,clear_key},crypto.randomUUID()),
  generate:(id:string,revision:number,requirement_id:string,model:string,prompt:string)=>
    request<{job_id:string;state:string}>("/projects/"+p(id)+"/assets/generate","POST",
      {expected_revision:revision,requirement_id,model,prompt,aspect_ratio:"16:9"},crypto.randomUUID())
};
