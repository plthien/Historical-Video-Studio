import React from 'react';
import {AbsoluteFill,useCurrentFrame} from 'remotion';
import {activeScene,assertMedia,assertTimeline,type Timeline,type ResolvedMedia,fail} from './schema';
import {T01} from './templates/T01';import {T02} from './templates/T02';import {T03} from './templates/T03';import {T04} from './templates/T04';import {T05} from './templates/T05';
import {T06} from './templates/T06';import {T07} from './templates/T07';import {T08} from './templates/T08';import {T09} from './templates/T09';import {T10} from './templates/T10';
export type HistoryProps={timeline:Timeline;media:ResolvedMedia};
const Templates:{[K in string]:React.FC<{scene:Timeline['scenes'][number];frame:number;media:ResolvedMedia}>}={T01,T02,T03,T04,T05,T06,T07,T08,T09,T10};
/** Only composition used by Remotion Player, renderStill and renderMedia. */
export const HistoryComposition:React.FC<HistoryProps>=({timeline,media})=>{
 const frame=useCurrentFrame();
 assertTimeline(timeline);
 assertMedia(timeline,media);
 const {scene,localFrame}=activeScene(timeline,frame);
 const Template=Templates[scene.template_id];
 if(!Template)fail('RENDER_TEMPLATE_UNKNOWN',scene.setup_id,'No registered historical scene implementation');
 if(!/^[A-Za-z0-9 _-]{1,64}$/.test(media.fontFamily))fail('RENDER_FONT_FAMILY_INVALID',scene.setup_id,'Unsafe font face');
 return <AbsoluteFill style={{backgroundColor:'#e6decf',overflow:'hidden'}} data-global-frame={frame} data-scene-id={scene.scene_id}>
  <style>{`@font-face{font-family:"${media.fontFamily}";src:url("${media.fontDataUri}") format("truetype");font-weight:400 900;}`}</style>
  <Template scene={scene} frame={localFrame} media={media}/>
 </AbsoluteFill>;
};
