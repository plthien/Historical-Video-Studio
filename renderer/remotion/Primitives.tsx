import React from 'react';
import {Img} from 'remotion';
import type {Scene,Layer,Motion,ResolvedMedia} from './schema';
import {fail} from './schema';

const clamp=(v:number)=>Math.min(1,Math.max(0,v));
const mix=(a:number,b:number,t:number)=>a+(b-a)*t;
export function interpolateKeys(keys:{frame:number;value:number}[],frame:number){
 if(!keys.length)return 1;
 if(frame<=keys[0].frame)return keys[0].value;
 for(let i=1;i<keys.length;i++)if(frame<=keys[i].frame){
  const a=keys[i-1],b=keys[i];return mix(a.value,b.value,clamp((frame-a.frame)/(b.frame-a.frame||1)));
 }
 return keys[keys.length-1].value;
}
function eventProgress(e:Motion,f:number){
 if(f<e.start_frame)return 0;
 if(f>=e.start_frame+e.duration_frames)return 1;
 return clamp(interpolateKeys(e.keyframes,f-e.start_frame));
}
function motionForLayer(scene:Scene,layer:Layer,frame:number){
 let opacity=1,scale=1,translateX=0,translateY=0,rotation=0,reveal=1,highlight=0;
 for(const e of scene.events){
  const ordered=(e.params.ordered_layer_ids as string[]|undefined);
  const stagger=e.preset_id==='stagger-reveal'&&ordered?.includes(layer.layer_id);
  if(e.layer_id!==layer.layer_id&&!e.affected_layer_ids.includes(layer.layer_id)&&!stagger)continue;
  const delay=stagger?ordered!.indexOf(layer.layer_id)*Number(e.params.gap_frames??6):0;
  const p=eventProgress({...e,start_frame:e.start_frame+delay},frame);
  switch(e.preset_id){
   case 'photo-card-enter':opacity*=p;scale*=mix(.93,1,p);rotation+=mix(Number(e.params.start_rotation_deg??-2),Number(e.params.end_rotation_deg??0),p);break;
   case 'pop-in':opacity*=p;scale*=mix(Number(e.params.from_scale??.95),Number(e.params.to_scale??1),p);break;
   case 'stagger-reveal':opacity*=p;translateY+=(1-p)*24;break;
   case 'title-mask-reveal':case 'typewriter':reveal=Math.min(reveal,p);opacity*=p;translateY+=(1-p)*Number(e.params.distance_px??20);break;
   case 'mask-transition':case 'map-region-wipe':reveal=Math.min(reveal,p);break;
   case 'text-highlight':highlight=Math.max(highlight,p);break;
   case 'parallax-layers':translateX+=p*Number(e.params.max_drift_px??40)*.5;break;
   case 'camera-push':case 'camera-pan':break; // camera is sampled separately
   case 'freeze-hold':break;
   case 'hard-cut':opacity*=p>0?1:0;break;
   case 'editorial-connector-draw':case 'route-line-draw':break; // exact reviewed geometry below
   default:fail('RENDER_MOTION_UNIMPLEMENTED',e.event_id,'Compiled motion not implemented in B2-01..03; cannot silently ignore');
  }
 }
 return {opacity,scale,translateX,translateY,rotation,reveal,highlight};
}
function firstAppearance(scene:Scene,layerId:string){
 const beats=scene.staging.beat_sequence.filter(b=>b.activated_layer_ids.includes(layerId));
 return beats.length?Math.min(...beats.map(b=>b.local_start_frame)):0;
}
function pathD(layer:Layer,media:ResolvedMedia){
 if(!layer.path_geometry_ref)return '';
 const g=media.geometries[layer.path_geometry_ref];
 if(!g)fail('RENDER_GEOMETRY_UNTRUSTED',layer.layer_id,'No verified geometry');
 const r=layer.rect_px;
 const points=g.coordinates.map(([x,y])=>{
  if(g.coordinateSpace==='ANNOTATION_CANVAS')return [x*r.w,y*r.h];
  const bbox=g.bbox;if(!bbox)fail('RENDER_MAP_VIEWPORT',layer.layer_id,'Historical map bbox absent');
  const [left,bottom,right,top]=bbox;
  return [((x-left)/(right-left))*r.w,((top-y)/(top-bottom))*r.h];
 });
 return points.map(([x,y],i)=>(i?'L':'M')+x.toFixed(2)+' '+y.toFixed(2)).join(' ');
}
function pathProgress(scene:Scene,layer:Layer,frame:number){
 const event=scene.events.find(e=>e.layer_id===layer.layer_id&&
  (e.preset_id==='route-line-draw'||e.preset_id==='editorial-connector-draw'));
 if(!event)fail('RENDER_PATH_MOTION_MISSING',layer.layer_id,'Route/connector needs authored compiled drawing event');
 return eventProgress(event,frame);
}
const ink='#303b39';
export const CompiledLayer:React.FC<{scene:Scene;layer:Layer;frame:number;media:ResolvedMedia}>=({scene,layer,frame,media})=>{
 const first=firstAppearance(scene,layer.layer_id);
 const effect=motionForLayer(scene,layer,frame);
 const r=layer.rect_px,c=layer.crop_normalized;
 const shown=frame>=first;
 const style:React.CSSProperties={position:'absolute',left:r.x,top:r.y,width:r.w,height:r.h,zIndex:layer.z_index,overflow:'hidden',
   opacity:shown?effect.opacity:0,transform:`translate(${effect.translateX}px,${effect.translateY}px) rotate(${effect.rotation}deg) scale(${effect.scale})`,
   transformOrigin:'center',borderRadius:layer.layer_kind==='archival_photo'?4:0, boxSizing:'border-box'};
 if(layer.layer_kind==='route'||layer.layer_kind==='annotation'){
  const progress=pathProgress(scene,layer,frame);
  const d=pathD(layer,media);
  return <div style={style} data-layer={layer.layer_id} data-claim={layer.source_claim_id??undefined}><svg width="100%" height="100%" viewBox={`0 0 ${r.w} ${r.h}`} style={{overflow:'visible'}}>
   <path d={d} fill="none" stroke={layer.layer_kind==='route'?'#a73c27':'#5d6770'} strokeWidth={layer.layer_kind==='route'?7:5} strokeLinecap="round" strokeDasharray="1" pathLength={1} strokeDashoffset={1-progress}/>
  </svg></div>;
 }
 if(layer.asset_id){
  const asset=media.assets[layer.asset_id];
  if(!asset)fail('RENDER_ASSET_UNTRUSTED',layer.layer_id,'Missing locally approved media');
  const imageStyle:React.CSSProperties={position:'absolute',width:`${100/c.w}%`,height:`${100/c.h}%`,left:`${-100*c.x/c.w}%`,top:`${-100*c.y/c.h}%`,objectFit:layer.object_fit};
  return <div style={{...style,clipPath:effect.reveal<1?`inset(0 ${(1-effect.reveal)*100}% 0 0)`:undefined,
       border:layer.layer_kind==='archival_photo'?'5px solid #f0e7d6':undefined,
       boxShadow:layer.layer_kind==='archival_photo'?'0 9px 20px #0004':undefined}} data-layer={layer.layer_id} data-asset={layer.asset_id} data-claim={layer.source_claim_id??undefined}>
    <Img src={asset.dataUri} style={imageStyle}/>
   </div>;
 }
 if(layer.text!==null){
  const txt=layer.text;const layout=layer.text_layout;
  if(!layout)fail('RENDER_TEXT_LAYOUT',layer.layer_id,'Text needs pinned glyph layout');
  const isHeading=layer.layer_kind==='headline';
  return <div style={{...style,padding:isHeading?10:6,display:'flex',alignItems:layout.vertical_align==='center'?'center':'flex-start',
    justifyContent:layout.horizontal_align==='center'?'center':'flex-start',background:layer.layer_kind==='date'?'#e6d6b9c9':undefined,
    clipPath:effect.reveal<1?`inset(0 ${(1-effect.reveal)*100}% 0 0)`:undefined}}
    data-layer={layer.layer_id} data-claim={layer.source_claim_id??undefined}>
   <span style={{fontFamily:media.fontFamily,color:effect.highlight>0.2?'#a65d20':ink,
     fontSize:layout.font_size_px,fontWeight:isHeading?700:500,lineHeight:layout.line_height,whiteSpace:'pre-wrap',overflow:'hidden',
     display:'-webkit-box',WebkitBoxOrient:'vertical',WebkitLineClamp:layout.max_lines}}>{txt}</span></div>;
 }
 return null;
};
export const BaseTemplate:React.FC<{scene:Scene;frame:number;media:ResolvedMedia;decor?:'map'|'portrait'|'collage'|'timeline'|'paper'|'split'|'fact'|'quote'|'causal'}>=({scene,frame,media,decor})=>{
 const cards=scene.layers.filter(l=>l.layer_kind==='archival_photo');
 if(decor==='collage'&&new Set(cards.map(l=>l.asset_id)).size!==cards.length)fail('RENDER_COLLAGE_DUPLICATE',scene.setup_id,'Duplicate evidence cards');
 if(decor==='split'){
  const pair=scene.layers.filter(l=>l.layer_kind==='map');
  if(pair.length!==2||pair[0].asset_id===pair[1].asset_id||pair[0].map_binding?.historical_map_id===pair[1].map_binding?.historical_map_id)fail('RENDER_PERIOD_MAP_DUPLICATE',scene.setup_id,'Independent period maps required');
 }
 const cam=scene.camera.keyframes;
 const local=frame;
 const k=cam.length===1?0:clamp((local-cam[0].at_frame)/(cam[cam.length-1].at_frame-cam[0].at_frame||1));
 const a=cam[0],b=cam[cam.length-1];
 const cameraStyle:React.CSSProperties={position:'absolute',inset:0,
   transform:`translate(${mix(a.x_px,b.x_px,k)}px,${mix(a.y_px,b.y_px,k)}px) scale(${mix(a.scale,b.scale,k)})`,
   transformOrigin:'960px 540px'};
 const back:Record<string,string>={map:'#dfddcf',portrait:'#ded8c9',collage:'#cbc3b2',timeline:'#f0e7d4',paper:'#e6ddcb',split:'#d8d5c7',fact:'#f3ebde',quote:'#e8dfd1',causal:'#d9d4c4'};
 return <div style={{width:1920,height:1080,position:'relative',overflow:'hidden',background:back[decor??'paper']}}>
  <div style={cameraStyle}>{[...scene.layers].sort((x,y)=>x.depth_order-y.depth_order).map(layer=>
    <CompiledLayer key={layer.layer_id} scene={scene} frame={local} layer={layer} media={media}/>)}</div>
 </div>;
};
