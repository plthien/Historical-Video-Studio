import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T06 renders frozen geometry and facts; no runtime research or inferred source. */
export const T06:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 if(!scene.layers.some(l=>l.layer_kind==='document'&&l.asset_id)||!scene.layers.some(l=>l.layer_kind==='text'&&l.source_claim_id))fail('T06_SOURCE_MISSING',scene.setup_id,'Approved document and exact source excerpt required');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="paper"/>;
};
