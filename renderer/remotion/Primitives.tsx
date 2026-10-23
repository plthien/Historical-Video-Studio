import React from 'react';
import {Img} from 'remotion';
import type {Scene,Layer,Motion,ResolvedMedia} from './schema';
import {fail} from './schema';

const clamp=(v:number)=>Math.min(1,Math.max(0,v));
const mix=(a:number,b:number,t:number)=>a+(b-a)*t;
const easing=(v:number,name:string)=>{const p=clamp(v);switch(name){
 case 'linear':return p;
 case 'ease_in_out':return p*p*(3-2*p);
 case 'ease_in':return p*p;
 case 'ease_out':return 1-(1-p)*(1-p);
 default:return fail('RENDER_CAMERA_EASING',name,'Unsupported authored camera easing');
}};
export function sampleCamera(keys:Scene['camera']['keyframes'],frame:number){
 if(!keys.length)fail('RENDER_CAMERA_KEYS','camera','A pinned camera needs at least one key');
 if(keys.some((k,i)=>i>0&&k.at_frame<=keys[i-1].at_frame))fail('RENDER_CAMERA_ORDER','camera','Camera keys must be strictly increasing');
 const fields=['x_px','y_px','scale','rotation_deg','opacity'] as const;
 if(keys.some(k=>fields.some(field=>!Number.isFinite(k[field]))||k.scale<=0||k.opacity<0||k.opacity>1))
  fail('RENDER_CAMERA_INVALID','camera','Invalid authored transform');
 if(frame<=keys[0].at_frame)return keys[0];
 for(let i=1;i<keys.length;i++){
  const b=keys[i],a=keys[i-1];
  if(frame<=b.at_frame){
   const t=easing((frame-a.at_frame)/(b.at_frame-a.at_frame),b.easing);
   return {...b,at_frame:frame,x_px:mix(a.x_px,b.x_px,t),y_px:mix(a.y_px,b.y_px,t),scale:mix(a.scale,b.scale,t),rotation_deg:mix(a.rotation_deg,b.rotation_deg,t),opacity:mix(a.opacity,b.opacity,t)};
  }
 }
 return keys[keys.length-1];
}
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
 let visibleText:string|undefined;
 for(const e of scene.events){
  const ordered=(e.params.ordered_layer_ids as string[]|undefined);
  const stagger=e.preset_id==='stagger-reveal'&&ordered?.includes(layer.layer_id);
  const dissolve=e.preset_id==='cross-dissolve'&&
   (e.params.out_layer_id===layer.layer_id||e.params.in_layer_id===layer.layer_id);
  if(e.layer_id!==layer.layer_id&&!e.affected_layer_ids.includes(layer.layer_id)&&!stagger&&!dissolve)continue;
  const delay=stagger?ordered!.indexOf(layer.layer_id)*Number(e.params.gap_frames??6):0;
  const starts=e.start_frame+delay;
  // The repeated B1 stagger events describe sequential beats for the
  // same source-card set. Pick the entrance nearest its FIRST activation,
  // not a future replay (which would re-hide an already revealed card).
  if(e.preset_id==='stagger-reveal'){
   const first=firstAppearance(scene,layer.layer_id);
   const all=scene.events.filter(candidate=>candidate.preset_id==='stagger-reveal'&&
    (candidate.layer_id===layer.layer_id||candidate.affected_layer_ids.includes(layer.layer_id)||
     (candidate.params.ordered_layer_ids as string[]|undefined)?.includes(layer.layer_id)));
   const begin=(candidate:Motion)=>{
    const order=candidate.params.ordered_layer_ids as string[]|undefined;
    const index=order?.indexOf(layer.layer_id)??-1;
    return candidate.start_frame+Math.max(0,index)*Number(candidate.params.gap_frames??6);
   };
   const sequence=[...all].sort((x,y)=>begin(x)-begin(y));
   const chosen=sequence.find(candidate=>begin(candidate)>=first)??sequence[sequence.length-1];
   if(chosen!==e)continue;
  }
  const p=eventProgress({...e,start_frame:starts},frame);
  switch(e.preset_id){
   case 'photo-card-enter':opacity*=p;scale*=mix(.93,1,p);rotation+=mix(Number(e.params.start_rotation_deg??-2),Number(e.params.end_rotation_deg??0),p);break;
   case 'pop-in':opacity*=p;scale*=mix(Number(e.params.from_scale??.95),Number(e.params.to_scale??1),p);break;
   case 'stagger-reveal':opacity*=p;translateY+=(1-p)*24;break;
   case 'title-mask-reveal':case 'typewriter':reveal=Math.min(reveal,p);opacity*=p;translateY+=(1-p)*Number(e.params.distance_px??20);break;
   case 'mask-transition':case 'map-region-wipe':reveal=Math.min(reveal,p);break;
   case 'text-highlight':highlight=Math.max(highlight,p);break;
   case 'kinetic-type':translateY+=(1-p)*Number(e.params.max_offset_px??24);break;
   case 'number-count':{
    const source=e.params.source_claim_id, end=Number(e.params.end_value);
    if(source!==layer.source_claim_id||!layer.text||Number(layer.text.replace(/,/g,''))!==end||
       e.params.intermediate_truthful!==true)
      fail('RENDER_COUNT_FACT_UNVERIFIED',e.event_id,'Number progression must be explicitly truth-safe and equal frozen exact factual text');
    visibleText=mix(Number(e.params.start_value??0),end,p).toFixed(Number(e.params.precision??0));
    break;
   }
   case 'parallax-layers':translateX+=p*Number(e.params.max_drift_px??40)*.5;break;
   case 'cross-dissolve':{
    const outgoing=e.params.out_layer_id,incoming=e.params.in_layer_id;
    if(typeof outgoing!=='string'||typeof incoming!=='string'||outgoing===incoming||
       !scene.layers.some(x=>x.layer_id===outgoing)||!scene.layers.some(x=>x.layer_id===incoming))
      fail('RENDER_CROSSFADE_TARGET',e.event_id,'Cross dissolve needs distinct authored, existing incoming/outgoing layers');
    if(e.params.mix_curve!=='linear'&&e.params.mix_curve!=='ease_in_out')
      fail('RENDER_CROSSFADE_CURVE',e.event_id,'Unsupported authored mix curve');
    const t=e.params.mix_curve==='ease_in_out'?p*p*(3-2*p):p;
    if(layer.layer_id===outgoing)opacity*=1-t;
    if(layer.layer_id===incoming)opacity*=t;
    break;
   }
   case 'whip-pan':break; // Screen-space transition is applied once outside the camera subtree.
   case 'camera-push':case 'camera-pan':break; // camera is sampled separately
   case 'freeze-hold':break;
   case 'hard-cut':opacity*=p>0?1:0;break;
   case 'editorial-connector-draw':case 'route-line-draw':break; // exact reviewed geometry below
   default:fail('RENDER_MOTION_UNIMPLEMENTED',e.event_id,'Compiled motion not implemented in B2-01..03; cannot silently ignore');
  }
 }
 return {opacity,scale,translateX,translateY,rotation,reveal,highlight,visibleText};
}
function firstAppearance(scene:Scene,layerId:string){
 const beats=scene.staging.beat_sequence.filter(b=>b.activated_layer_ids.includes(layerId));
 return beats.length?Math.min(...beats.map(b=>b.local_start_frame)):0;
}
function pathPoints(layer:Layer,media:ResolvedMedia):[number,number][]{
 const ref=layer.path_geometry_ref ?? fail('RENDER_GEOMETRY_UNTRUSTED',layer.layer_id,'Missing frozen geometry ref');
 const g=media.geometries[ref] ?? fail('RENDER_GEOMETRY_UNTRUSTED',layer.layer_id,'No verified geometry');
 const r=layer.rect_px;
 const points=g.coordinates.map(([x,y])=>{
  if(g.coordinateSpace==='ANNOTATION_CANVAS')return [x*r.w,y*r.h] as [number,number];
  const bbox=g.bbox;if(!bbox)fail('RENDER_MAP_VIEWPORT',layer.layer_id,'Historical map bbox absent');
  const [left,bottom,right,top]=bbox!;
  const projection=media.maps[g.historicalMapId!]?.projection;
  const clampLatitude=(lat:number)=>Math.max(-85.05112878,Math.min(85.05112878,lat));
  const merc=(lat:number)=>Math.log(Math.tan(Math.PI/4+clampLatitude(lat)*Math.PI/360));
  if(projection!=='mercator'&&projection!=='equirectangular')fail('RENDER_PROJECTION_UNSUPPORTED',layer.layer_id,'Unsupported reviewed projection cannot be silently drawn');
  const yNorm=projection==='mercator'?(merc(top)-merc(y))/(merc(top)-merc(bottom)):
    (top-y)/(top-bottom);
  return [((x-left)/(right-left))*r.w,yNorm*r.h] as [number,number];
 });
 return points;
}
function pathD(points:[number,number][]):string{
 return points.map(([x,y],i)=>(i?'L':'M')+x.toFixed(2)+' '+y.toFixed(2)).join(' ');
}
/** The arrow moves with the drawn path's actual tip, not a fabricated line endpoint. */
export function arrowPolygon(points:[number,number][],progress:number):string|null{
 if(progress<=0.01)return null;
 let total=0;const lengths:number[]=[];
 for(let i=1;i<points.length;i++){const d=Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]);lengths.push(d);total+=d;}
 if(total<1)fail('RENDER_ARROW_GEOMETRY','annotation','Arrow requires non-degenerate authored geometry');
 let remaining=total*clamp(progress);
 for(let i=1;i<points.length;i++){
  const d=lengths[i-1];
  if(remaining<=d||i===points.length-1){
   if(d===0){remaining-=d;continue;}
   const ux=(points[i][0]-points[i-1][0])/d,uy=(points[i][1]-points[i-1][1])/d;
   const tip=[points[i-1][0]+ux*Math.min(d,remaining),points[i-1][1]+uy*Math.min(d,remaining)];
   const base=[tip[0]-ux*19,tip[1]-uy*19],perp=[-uy*8,ux*8];
   return [tip,[base[0]+perp[0],base[1]+perp[1]],[base[0]-perp[0],base[1]-perp[1]]]
    .map(p=>p.map(x=>x.toFixed(2)).join(',')).join(' ');
  }
  remaining-=d;
 }
 return null;
}
function pathProgress(scene:Scene,layer:Layer,frame:number){
 const event=scene.events.find(e=>e.layer_id===layer.layer_id&&
  (e.preset_id==='route-line-draw'||e.preset_id==='editorial-connector-draw'));
 if(!event)fail('RENDER_PATH_MOTION_MISSING',layer.layer_id,'Route/connector needs authored compiled drawing event');
 return eventProgress(event!,frame);
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
  const points=pathPoints(layer,media),d=pathD(points);
  const event=scene.events.find(e=>e.layer_id===layer.layer_id&&
    (e.preset_id==='editorial-connector-draw'||e.preset_id==='route-line-draw'));
  const arrow=event?.params.arrowhead;
  if(arrow!==undefined&&typeof arrow!=='boolean')fail('RENDER_ARROW_FLAG',layer.layer_id,'Authored arrowhead must be boolean');
  if(arrow&& (layer.layer_kind!=='annotation'||event?.motion_space!=='group_local'||
      event.params.connector_geometry_ref!==layer.path_geometry_ref||
      event.params.source_claim_id!==layer.source_claim_id))
   fail('RENDER_ARROW_UNTRUSTED',layer.layer_id,'Directional arrow requires matching editorial geometry, claim and group-local motion');
  const polygon=arrow?arrowPolygon(points,progress):null;
  return <div style={style} data-layer={layer.layer_id} data-claim={layer.source_claim_id??undefined}><svg width="100%" height="100%" viewBox={`0 0 ${r.w} ${r.h}`} style={{overflow:'visible'}}>
   <path d={d} fill="none" stroke={layer.layer_kind==='route'?'#a73c27':'#5d6770'} strokeWidth={layer.layer_kind==='route'?7:5} strokeLinecap="round" strokeDasharray="1" pathLength={1} strokeDashoffset={1-progress}/>
   {polygon&&<polygon data-arrowhead={layer.layer_id} points={polygon} fill="#5d6770"/>}
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
  const txt=effect.visibleText??layer.text;const layout=layer.text_layout;
  if(!layout)fail('RENDER_TEXT_LAYOUT',layer.layer_id,'Text needs pinned glyph layout');
  const measured=layout!;
  const isHeading=layer.layer_kind==='headline';
  return <div style={{...style,padding:isHeading?10:6,display:'flex',alignItems:measured.vertical_align==='center'?'center':'flex-start',
    justifyContent:measured.horizontal_align==='center'?'center':'flex-start',background:layer.layer_kind==='date'?'#e6d6b9c9':undefined,
    clipPath:effect.reveal<1?`inset(0 ${(1-effect.reveal)*100}% 0 0)`:undefined}}
    data-layer={layer.layer_id} data-claim={layer.source_claim_id??undefined}>
   <span style={{fontFamily:media.fontFamily,color:effect.highlight>0.2?'#a65d20':ink,
     fontSize:measured.font_size_px,fontWeight:isHeading?700:500,lineHeight:measured.line_height,whiteSpace:'pre-wrap',overflow:'hidden',
     display:'-webkit-box',WebkitBoxOrient:'vertical',WebkitLineClamp:measured.max_lines}}>{txt}</span></div>;
 }
 return null;
};
export const BaseTemplate:React.FC<{scene:Scene;frame:number;media:ResolvedMedia;decor?:'map'|'portrait'|'collage'|'timeline'|'paper'|'split'|'fact'|'quote'|'causal'; underlay?:React.ReactNode}>=({scene,frame,media,decor,underlay})=>{
 const cards=scene.layers.filter(l=>l.layer_kind==='archival_photo');
 if(decor==='collage'&&new Set(cards.map(l=>l.asset_id)).size!==cards.length)fail('RENDER_COLLAGE_DUPLICATE',scene.setup_id,'Duplicate evidence cards');
 if(decor==='split'){
  const pair=scene.layers.filter(l=>l.layer_kind==='map');
  if(pair.length!==2||pair[0].asset_id===pair[1].asset_id||pair[0].map_binding?.historical_map_id===pair[1].map_binding?.historical_map_id)fail('RENDER_PERIOD_MAP_DUPLICATE',scene.setup_id,'Independent period maps required');
 }
 const local=frame;
 const camera=sampleCamera(scene.camera.keyframes,frame);
 const cameraStyle:React.CSSProperties={position:'absolute',inset:0,
   opacity:camera.opacity,
   transform:`translate(${camera.x_px}px,${camera.y_px}px) rotate(${camera.rotation_deg}deg) scale(${camera.scale})`,
   transformOrigin:'960px 540px'};
 const whips=scene.events.filter(e=>e.preset_id==='whip-pan');
 if(whips.length>1)fail('RENDER_WHIP_DUPLICATE',scene.setup_id,'Only one screen-space whip may affect a scene at once');
 const whip=whips[0];
 let screenStyle:React.CSSProperties={position:'absolute',inset:0};
 if(whip){
  const {direction,sweep_px,motion_blur_px}=whip.params;
  if((direction!=='left'&&direction!=='right')||typeof sweep_px!=='number'||
     sweep_px<40||sweep_px>480||typeof motion_blur_px!=='number'||
     motion_blur_px<0||motion_blur_px>40)
   fail('RENDER_WHIP_PARAMS',whip.event_id,'Invalid registered screen transition params');
  const p=eventProgress(whip,frame);
  const dir=direction==='left'?-1:1;
  screenStyle={...screenStyle,transform:`translateX(${dir*(1-p)*Number(sweep_px)}px)`,
   filter:`blur(${(1-p)*Number(motion_blur_px)}px)`};
 }
 const back:Record<string,string>={map:'#dfddcf',portrait:'#ded8c9',collage:'#cbc3b2',timeline:'#f0e7d4',paper:'#e6ddcb',split:'#d8d5c7',fact:'#f3ebde',quote:'#e8dfd1',causal:'#d9d4c4'};
 return <div style={{width:1920,height:1080,position:'relative',overflow:'hidden',background:back[decor??'paper']}}>
  <div style={screenStyle}><div style={cameraStyle}>{underlay}{[...scene.layers].sort((x,y)=>x.depth_order-y.depth_order).map(layer=>
    <CompiledLayer key={layer.layer_id} scene={scene} frame={local} layer={layer} media={media}/>)}</div></div>
 </div>;
};
