import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T04 renders frozen geometry and facts; no runtime research or inferred source. */
export const T04:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 if(!scene.layers.some(l=>l.layer_kind==='map'&&l.map_binding)||!scene.layers.some(l=>l.layer_kind==='route'&&l.path_geometry_ref)||!scene.events.some(e=>e.preset_id==='route-line-draw'&&e.motion_space==='map_world'))fail('T04_ROUTE_UNTRUSTED',scene.setup_id,'Period map and reviewed geographic route required');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="map"/>;
};
