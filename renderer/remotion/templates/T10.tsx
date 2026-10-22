import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T10 renders frozen geometry and facts; no runtime research or inferred source. */
export const T10:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 if(!scene.layers.some(l=>l.layer_kind==='annotation'&&l.path_geometry_ref&&l.source_claim_id)||!scene.events.some(e=>e.preset_id==='editorial-connector-draw'&&e.motion_space==='group_local'))fail('T10_CAUSAL_SOURCE',scene.setup_id,'Editorial cause/effect links need claims and canvas connector');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="causal"/>;
};
