import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T08 renders frozen geometry and facts; no runtime research or inferred source. */
export const T08:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 if(!scene.layers.some(l=>l.layer_kind==='date'&&l.text&&l.source_claim_id)||!scene.layers.some(l=>l.layer_kind==='headline'&&l.source_claim_id))fail('T08_UNSOURCED_FACT',scene.setup_id,'Compiled fact, unit and source claim required');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="fact"/>;
};
