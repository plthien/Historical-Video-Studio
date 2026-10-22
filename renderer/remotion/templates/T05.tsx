import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T05 renders frozen geometry and facts; no runtime research or inferred source. */
export const T05:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 const dates=scene.layers.filter(l=>l.layer_kind==='date');if(dates.length<2||dates.some(l=>!l.text||!l.source_claim_id)||!scene.layers.some(l=>l.layer_kind==='annotation'&&l.path_geometry_ref))fail('T05_CHRONOLOGY_INVALID',scene.setup_id,'Compiled dates and source-backed timeline connector required');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="timeline"/>;
};
