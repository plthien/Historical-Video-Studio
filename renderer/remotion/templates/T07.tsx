import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T07 renders frozen geometry and facts; no runtime research or inferred source. */
export const T07:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 const maps=scene.layers.filter(l=>l.layer_kind==='map');if(maps.length!==2||maps[0].asset_id===maps[1].asset_id||maps[0].map_binding?.historical_map_id===maps[1].map_binding?.historical_map_id||scene.layers.filter(l=>l.layer_kind==='date').length!==2)fail('T07_PERIOD_PAIR_INVALID',scene.setup_id,'Two separately reviewed dates/maps required');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="split"/>;
};
