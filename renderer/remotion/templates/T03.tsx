import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T03 renders frozen geometry and facts; no runtime research or inferred source. */
export const T03:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 const cards=scene.layers.filter(l=>l.layer_kind==='archival_photo');if(cards.length<2||cards.length>3||new Set(cards.map(l=>l.asset_id)).size!==cards.length)fail('T03_CARDS_INVALID',scene.setup_id,'2-3 independent approved cards required');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="collage"/>;
};
