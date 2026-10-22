import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T09 renders frozen geometry and facts; no runtime research or inferred source. */
export const T09:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 if(!scene.layers.some(l=>l.layer_kind==='headline'&&l.text&&l.source_claim_id)||!scene.layers.some(l=>l.layer_kind==='text'&&l.text&&l.source_claim_id))fail('T09_QUOTE_UNVERIFIED',scene.setup_id,'Quote and attribution must come from approved source text');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="quote"/>;
};
