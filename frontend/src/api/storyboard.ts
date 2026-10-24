/** Typed B2-05 transport. Source identities are returned by the Windows-local host,
 * never minted by browser form inputs. */
import {request} from './client';
import type {HistoryProps} from '../../../renderer/remotion/HistoryComposition';
export interface StoryboardScene {
  scene_id:string;setup_id:string;template_id:string;variant_id:string;
  start_frame:number;duration_frames:number;
  layers:{layer_id:string;layer_kind:string;text:string|null;asset_id:string|null;
    rect_px:{x:number;y:number;w:number;h:number};crop_normalized:{x:number;y:number;w:number;h:number}}[];
  events:{event_id:string;preset_id:string;start_frame:number;duration_frames:number;params:Record<string,string|number|boolean>}[];
  direction_beats:{beat_id:string;shot_goal:string;focus_move:string;staging:{
    ref:string;operation:string;after_ref:string|null;motion_hint:string;priority:number;}[]}[];
  diagnostics:string[];
}
export interface ScenePage {
 project_revision:number;draft_manifest_sha256:string;story_revision_sha256:string;status:'G4_DRAFT_NOT_OPERATOR_APPROVED';
 total:number;offset:number;limit:number;scenes:StoryboardScene[];
}
export interface TimelineView {project_revision:number;draft_manifest_sha256:string;
 status:'G4_DRAFT_NOT_OPERATOR_APPROVED';timeline:HistoryProps['timeline'];}
export interface BrowserPreview {project_revision:number;draft_manifest_sha256:string;
 status:'G4_DRAFT_VIEW_ONLY';props:HistoryProps;}
export interface EditResult {timeline:HistoryProps['timeline'];recomputed_setup_ids:string[];
 retained_setup_ids:string[];project_revision:number;stale_gates:['G4','G5'];}
const path=(id:string)=>'/projects/'+encodeURIComponent(id)+'/storyboard';
export const storyboardApi={
 scenes:(id:string,offset=0,limit=24)=>request<ScenePage>(path(id)+`/scenes?offset=${offset}&limit=${limit}`),
 timeline:(id:string)=>request<TimelineView>(path(id)+'/timeline'),
 preview:(id:string,signal?:AbortSignal)=>request<BrowserPreview>(path(id)+'/preview','GET',undefined,undefined,signal),
 variant:(id:string,scene:string,variant:string,revision:number,key:string)=>
  request<EditResult>(path(id)+'/scenes/'+encodeURIComponent(scene),'PATCH',
    {expected_revision:revision,scene_id:scene,changes:{variant_id:variant}},key),
 geometry:(id:string,scene:string,layer:string,patch:Partial<{x_px:number;y_px:number;w_px:number;h_px:number}>,revision:number,key:string)=>
  request<EditResult>(path(id)+'/scenes/'+encodeURIComponent(scene),'PATCH',
    {expected_revision:revision,scene_id:scene,changes:{layer_edits:[{layer_id:layer,...patch}]}},key),
 crop:(id:string,scene:string,layer:string,crop_normalized:{x:number;y:number;w:number;h:number},revision:number,key:string)=>
  request<EditResult>(path(id)+'/scenes/'+encodeURIComponent(scene),'PATCH',
    {expected_revision:revision,scene_id:scene,changes:{layer_edits:[{layer_id:layer,crop_normalized}]}},key),
 motion:(id:string,scene:string,event_id:string,preset_id:string,params:Record<string,string|number|boolean>,revision:number,key:string)=>
  request<EditResult>(path(id)+'/scenes/'+encodeURIComponent(scene),'PATCH',
    {expected_revision:revision,scene_id:scene,changes:{motion_edits:[{event_id,preset_id,params}]}},key),
 direction:(id:string,body:unknown,key:string)=>
  request<EditResult>(path(id)+'/direction-revisions','POST',body,key)
};
