import React from 'react';
import {AbsoluteFill,useCurrentFrame} from 'remotion';
import {activeScene,assertMedia,assertTimeline,type Timeline,type ResolvedMedia,fail} from './schema';
import {T01} from './templates/T01';import {T02} from './templates/T02';import {T03} from './templates/T03';import {T04} from './templates/T04';import {T05} from './templates/T05';
import {T06} from './templates/T06';import {T07} from './templates/T07';import {T08} from './templates/T08';import {T09} from './templates/T09';import {T10} from './templates/T10';
export type HistoryProps={timeline:Timeline;media:ResolvedMedia};
const Templates:{[K in string]:React.FC<{scene:Timeline['scenes'][number];frame:number;media:ResolvedMedia}>}={T01,T02,T03,T04,T05,T06,T07,T08,T09,T10};
/** Native screen-space mask: visible black region expands across the incoming surface. */
function boundaryMask(shape:string,direction:string,progress:number,feather:number):React.CSSProperties{
 const p=Math.min(1,Math.max(0,progress));
 if(!Number.isFinite(feather)||feather<0||feather>60)
  fail('RENDER_TRANSITION_FEATHER','mask','Feather exceeds registered native screen wipe bounds');
 const horizontal=direction==='left'||direction==='right';
 if(!['left','right','up','down'].includes(direction)||!['rect','circle','diagonal'].includes(shape))
  fail('RENDER_TRANSITION_SHAPE','mask','Only registered native transition shapes are supported');
 const length=shape==='circle'?1110:shape==='diagonal'?2205:horizontal?1920:1080;
 const boundary=p*length, inner=Math.max(0,boundary-feather/2),outer=Math.min(length,boundary+feather/2);
 if(shape==='circle'){
  const gradient=`radial-gradient(circle at center, #000 ${inner}px, transparent ${outer}px)`;
  return {maskImage:gradient,WebkitMaskImage:gradient};
 }
 const angle=shape==='diagonal'?
  ({left:'135deg',right:'315deg',up:'45deg',down:'225deg'}[direction]):
  ({left:'to right',right:'to left',up:'to bottom',down:'to top'}[direction]);
 const gradient=`linear-gradient(${angle}, #000 ${inner}px, transparent ${outer}px)`;
 return {maskImage:gradient,WebkitMaskImage:gradient};
}
/** Only composition used by Remotion Player, renderStill and renderMedia. */
export const HistoryComposition:React.FC<HistoryProps>=({timeline,media})=>{
 const frame=useCurrentFrame();
 assertTimeline(timeline);
 assertMedia(timeline,media);
 const {scene,localFrame}=activeScene(timeline,frame);
 const Template=Templates[scene.template_id];
 if(!Template)fail('RENDER_TEMPLATE_UNKNOWN',scene.setup_id,'No registered historical scene implementation');
 if(!/^[A-Za-z0-9 _-]{1,64}$/.test(media.fontFamily))fail('RENDER_FONT_FAMILY_INVALID',scene.setup_id,'Unsafe font face');
 const index=timeline.scenes.findIndex(row=>row.scene_id===scene.scene_id);
 const previous=index>0?timeline.scenes[index-1]:null;
 const candidates=scene.events.filter(e=>e.preset_id==='mask-transition'&&e.start_frame===0);
 const boundary=previous?.transition_out.type==='mask_reveal'&&
   previous.transition_out.duration_frames>0&&candidates.length===1&&
   candidates[0].duration_frames===previous.transition_out.duration_frames?
   candidates[0]:null;
 // Never infer an outgoing surface from layer z-order or arbitrary browser props.
 const outgoing=boundary&&previous?Templates[previous.template_id]:null;
 const maskedScene=boundary?{...scene,events:scene.events.filter(e=>e.event_id!==boundary.event_id)}:scene;
 const progress=boundary?(localFrame+1)/boundary.duration_frames:1;
 return <AbsoluteFill style={{backgroundColor:'#e6decf',overflow:'hidden'}} data-global-frame={frame} data-scene-id={scene.scene_id}>
  <style>{`@font-face{font-family:"${media.fontFamily}";src:url("${media.fontDataUri}") format("truetype");font-weight:400 900;}`}</style>
  {boundary&&outgoing&&previous&&localFrame<boundary.duration_frames?
   <>
    {React.createElement(outgoing,{scene:previous,frame:previous.duration_frames-1,media})}
    <AbsoluteFill style={boundaryMask(String(boundary.params.mask_shape),
      String(boundary.params.wipe_direction),progress,Number(boundary.params.feather_px))}>
     <Template scene={maskedScene} frame={localFrame} media={media}/>
    </AbsoluteFill>
   </>:
   <Template scene={maskedScene} frame={localFrame} media={media}/>}
 </AbsoluteFill>;
};
