import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T01 renders frozen geometry and facts; no runtime research or inferred source. */
export const T01:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 const maps=scene.layers.filter(l=>l.layer_kind==='map');if(maps.length!==1||!maps[0].map_binding||!scene.layers.some(l=>l.layer_kind==='headline'&&l.source_claim_id))fail('T01_MAP_TRUTH',scene.setup_id,'Period map/claim-backed label required');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="map"/>;
};
