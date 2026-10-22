import Ajv2020 from 'ajv/dist/2020.js';
import timelineSchema from '../../contracts/schema/CompiledTimeline.v1.schema.json';
import layouts from '../../contracts/registries/layouts.v1.json';
import motions from '../../contracts/registries/motion-presets.v1.json';

export type Rect = {x:number;y:number;w:number;h:number};
export type MediaKind = 'SYNTHETIC'|'APPROVED_LOCAL';
export type MediaItem={assetId:string; originalSha256:string; mime:'image/png'|'image/jpeg'|'image/webp'; dataUri:string; sourceKind:MediaKind; approvalRecordId:string};
export type Geometry = {geometryRef:string; coordinates:[number,number][]; coordinateSpace:'WGS84'|'ANNOTATION_CANVAS'; sourceOriginalSha256:string; historicalMapId:string|null; reviewedYear:number|null; bbox:[number,number,number,number]|null};
export type ReviewedMap={historicalMapId:string;projection:string;viewport:[number,number,number,number];reviewedYear:number;sourceOriginalSha256:string;coordinateKind:'geo_wgs84'|'raster_uv'};
export type ResolvedMedia={assets:Record<string,MediaItem>; geometries:Record<string,Geometry>; maps:Record<string,ReviewedMap>; fontFamily:string; fontSha256:string; fontDataUri:string; sourceKind:MediaKind; authorizingG4ManifestSha256:string};
export type Layer={layer_id:string; layer_kind:string; asset_id:string|null; text:string|null; source_claim_id:string|null; z_index:number;depth_order:number;rect_px:Rect; crop_normalized:Rect;object_fit:'contain'|'cover'|'fill';mask:{kind:string;asset_id:string|null;feather_px:number};map_binding:{historical_map_id:string;feature_id:string|null;coordinate_kind:string;anchor_latlon:[number,number]|null}|null; parent_layer_id:string|null;group_id:string; text_layout:{font_size_px:number;line_height:number;max_lines:number;horizontal_align:string;vertical_align:string}|null; template_slot_id:string;source_asset_slot_id:string|null; path_geometry_ref:string|null; treatment:{kind:string;source_preserving:boolean;evidence_badge:string}};
export type Key={frame:number;value:number;easing:string};
export type Motion={event_id:string; layer_id:string; preset_id:string;start_frame:number; duration_frames:number;params:Record<string,unknown>;keyframes:Key[];motion_space:string;affected_layer_ids:string[];animated_property:string;stagger:{order:string[];offset_frames:number}|null};
export type Beat={local_start_frame:number;local_end_frame:number;focus_layer_id:string;activated_layer_ids:string[];hidden_layer_ids:string[]};
export type CameraKey={at_frame:number;x_px:number;y_px:number;scale:number;rotation_deg:number;opacity:number;easing:string};
export type Scene={scene_id:string;setup_id:string;template_id:string;variant_id:string;start_frame:number;duration_frames:number;asset_ids:string[];layers:Layer[];events:Motion[];camera:{keyframes:CameraKey[];transform_order:string;focus_path:unknown[]};staging:{beat_sequence:Beat[];composition_graph:{edges:unknown[]};};transition_out:{type:string;duration_frames:number}};
export type Timeline={schema_version:'CompiledTimeline.v1';project_id:string;fps:30;width:1920;height:1080;total_frames:number;dependency_fingerprint:string;audio_sha256:string;word_map_sha256:string;asset_snapshot_sha256:string;scenes:Scene[]};
const ajv=new Ajv2020({allErrors:true,strict:false});
const validate=ajv.compile(timelineSchema);
const validLayouts=new Set(layouts.layouts.map(l=>l.template_id+':'+l.variant_id));
const motionById=new Map(motions.presets.map(m=>[m.preset_id,m]));
export class RenderBlocked extends Error{constructor(readonly code:string, readonly subject:string, detail:string){super(code+' at '+subject+': '+detail);this.name='RenderBlocked';}}
export const fail=(code:string,at:string,message:string):never=>{throw new RenderBlocked(code,at,message)};
export function assertTimeline(input:unknown):asserts input is Timeline {
 if(!validate(input))fail('RENDER_SCHEMA_INVALID','timeline',ajv.errorsText(validate.errors,{separator:'; '}));
 const t=input as Timeline;
 if(t.fps!==30||t.width!==1920||t.height!==1080)fail('RENDER_FORMAT_INVALID',t.project_id,'Frozen 1920x1080 @ 30fps required');
 let end=0;
 for(const s of t.scenes){
  if(s.start_frame!==end||s.duration_frames<1)fail('RENDER_FRAME_COVERAGE',s.setup_id,'Unbroken scene frame ownership required');
  end+=s.duration_frames;
  if(!validLayouts.has(s.template_id+':'+s.variant_id))fail('RENDER_LAYOUT_UNKNOWN',s.setup_id,'Unregistered template variant');
  const ids=new Set(s.layers.map(l=>l.layer_id));
  if(ids.size!==s.layers.length)fail('RENDER_LAYER_DUPLICATE',s.setup_id,'Layer identities must be unique');
  for(const l of s.layers){
   const r=l.rect_px,c=l.crop_normalized;
   if(r.w<=0||r.h<=0||r.x<0||r.y<0||r.x+r.w>1920||r.y+r.h>1080)fail('RENDER_RECT_INVALID',l.layer_id,'Compiled rect exceeds canvas');
   if(c.x<0||c.y<0||c.w<=0||c.h<=0||c.x+c.w>1.0000001||c.y+c.h>1.0000001)fail('RENDER_CROP_INVALID',l.layer_id,'UV outside original');
   if(l.mask.kind!=='none')fail('RENDER_MASK_UNSUPPORTED',l.layer_id,'Requires separately verified G3 derivative mask');
   if(l.parent_layer_id&&!ids.has(l.parent_layer_id))fail('RENDER_PARENT_UNKNOWN',l.layer_id,'Unknown hierarchy parent');
   if(l.asset_id&&!s.asset_ids.includes(l.asset_id))fail('RENDER_ASSET_UNLISTED',l.layer_id,'Asset absent from frozen scene manifest');
  }
  for(const e of s.events){
   const spec=motionById.get(e.preset_id);
   if(!spec)fail('RENDER_MOTION_UNKNOWN',e.event_id,'Unregistered motion');
   if(!ids.has(e.layer_id)||e.affected_layer_ids.some(id=>!ids.has(id)))fail('RENDER_MOTION_TARGET',e.event_id,'Unresolved layer reference');
   if(e.start_frame<0||e.start_frame+e.duration_frames>s.duration_frames)fail('RENDER_MOTION_BOUNDS',e.event_id,'Event outside scene');
   if(e.motion_space!==spec!.render_recipe.transform_space)fail('RENDER_MOTION_SPACE',e.event_id,'Compiled motion-space mismatches registered preset');
  }
 }
 if(end!==t.total_frames)fail('RENDER_FRAME_COVERAGE',t.project_id,'Total frame ceiling does not equal scene sum');
}
export function assertMedia(t:Timeline,m:ResolvedMedia){
 if(!m|| !/^[a-f0-9]{64}$/.test(m.authorizingG4ManifestSha256))fail('RENDER_DRAFT_UNTRUSTED',t.project_id,'Node must attach verified G4 draft manifest');
 if(!/^[a-f0-9]{64}$/.test(m.fontSha256)||!m.fontDataUri.startsWith('data:font/'))fail('RENDER_FONT_UNTRUSTED',t.project_id,'Pinned local font required');
 for(const s of t.scenes)for(const l of s.layers){
  if(l.asset_id){let a=m.assets[l.asset_id];if(!a||a.assetId!==l.asset_id||!a.originalSha256||!a.approvalRecordId||!a.dataUri.startsWith('data:image/'))fail('RENDER_MEDIA_UNTRUSTED',l.layer_id,'Asset bytes/rights need local verified resolver');}
  if(l.map_binding){
   const map=m.maps[l.map_binding.historical_map_id];
   if(!map||map.historicalMapId!==l.map_binding.historical_map_id||map.coordinateKind!==l.map_binding.coordinate_kind||
      !l.asset_id||!m.assets[l.asset_id]||map.sourceOriginalSha256!==m.assets[l.asset_id].originalSha256)
     fail('RENDER_MAP_UNREVIEWED',l.layer_id,'B1-02 period map does not match actual immutable approved original');
  }
  if(l.path_geometry_ref){let g=m.geometries[l.path_geometry_ref];if(!g||g.geometryRef!==l.path_geometry_ref||g.coordinates.length<2)fail('RENDER_GEOMETRY_UNTRUSTED',l.layer_id,'Reviewed path geometry missing');
   if(l.layer_kind==='route'&&(g.coordinateSpace!=='WGS84'||!g.historicalMapId||!g.bbox||g.reviewedYear===null||
    !s.layers.some(x=>x.layer_kind==='map'&&x.map_binding?.historical_map_id===g.historicalMapId&&
      x.asset_id&&m.assets[x.asset_id]?.originalSha256===g.sourceOriginalSha256)))
      fail('RENDER_ROUTE_UNREVIEWED',l.layer_id,'Historical route geometry must bind the exact reviewed period-map original');
   if(l.layer_kind==='annotation'&&g.coordinateSpace!=='ANNOTATION_CANVAS')fail('RENDER_EDITORIAL_GEOMETRY',l.layer_id,'Editorial connector cannot use geographical coordinate space');
  }
 }
 const pair=t.scenes.filter(s=>s.template_id==='T07');
 for(const s of pair){
  const maps=s.layers.filter(l=>l.layer_kind==='map');
  if(maps.length!==2||maps[0].asset_id===maps[1].asset_id||maps[0].map_binding?.historical_map_id===maps[1].map_binding?.historical_map_id)fail('RENDER_PERIOD_MAP_DUPLICATE',s.setup_id,'T07 needs distinct approved historical map sources');
  const first=m.maps[maps[0].map_binding!.historical_map_id],second=m.maps[maps[1].map_binding!.historical_map_id];
  if(!first||!second||first.projection!==second.projection||JSON.stringify(first.viewport)!==JSON.stringify(second.viewport)||
     first.reviewedYear===second.reviewedYear)fail('RENDER_PERIOD_MAP_MISMATCH',s.setup_id,'T07 needs two reviewed years with identical frozen projection and viewport');
 }
 for(const s of t.scenes.filter(s=>s.template_id==='T03')){
  const cards=s.layers.filter(l=>l.layer_kind==='archival_photo');
  const originals=cards.map(l=>l.asset_id&&m.assets[l.asset_id]?.originalSha256);
  if(cards.length<2||originals.some(x=>!x)||new Set(originals).size!==cards.length)
   fail('RENDER_COLLAGE_DUPLICATE',s.setup_id,'Every evidence card must use a distinct approved original');
 }
}
export function activeScene(t:Timeline,globalFrame:number):{scene:Scene;localFrame:number}{
 if(!Number.isInteger(globalFrame)||globalFrame<0||globalFrame>=t.total_frames)fail('RENDER_FRAME_OUTSIDE',t.project_id,'Frame not owned by timeline');
 const scene=t.scenes.find(s=>globalFrame>=s.start_frame&&globalFrame<s.start_frame+s.duration_frames);
 if(!scene)fail('RENDER_FRAME_GAP',t.project_id,'No scene owns frame');
 return {scene:scene!,localFrame:globalFrame-scene!.start_frame};
}
