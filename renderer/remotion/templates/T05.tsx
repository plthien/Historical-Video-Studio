import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T05: chronological rail connects exact compiled dated text, never invented events. */
export const T05:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 const dates=scene.layers.filter(l=>l.layer_kind==='date');
 if(dates.length<2||dates.some(l=>!l.text||!l.source_claim_id))fail('T05_CHRONOLOGY_INVALID',scene.setup_id,'Source-claim-backed chronological labels required');
 const [first,second]=dates;
 const x1=first.rect_px.x+first.rect_px.w/2,y1=first.rect_px.y+first.rect_px.h/2;
 const x2=second.rect_px.x+second.rect_px.w/2,y2=second.rect_px.y+second.rect_px.h/2;
 const localProgress=Math.min(1,Math.max(0,(frame-8)/45));
 return <div style={{width:1920,height:1080,position:'relative'}}>
   <BaseTemplate scene={scene} frame={frame} media={media} decor="timeline"/>
   <svg viewBox="0 0 1920 1080" width={1920} height={1080} style={{position:'absolute',inset:0,pointerEvents:'none'}}>
    <path d={`M ${x1} ${y1} L ${x2} ${y2}`} fill="none" stroke="#806449" strokeWidth={8} strokeDasharray="1" pathLength={1} strokeDashoffset={1-localProgress}/>
    <circle cx={x1} cy={y1} r={12} fill="#8f6a3d"/>
    <circle cx={x2} cy={y2} r={12} fill="#8f6a3d" opacity={localProgress}/>
   </svg>
 </div>;
};
