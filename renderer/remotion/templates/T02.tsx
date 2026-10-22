import React from 'react';
import type {Scene,ResolvedMedia} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';
/** T02 renders frozen geometry and facts; no runtime research or inferred source. */
export const T02:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 if(scene.layers.filter(l=>l.layer_kind==='portrait').length!==1||!scene.layers.some(l=>l.layer_kind==='headline'))fail('T02_PORTRAIT_IDENTITY',scene.setup_id,'One source portrait and named identity required');
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="portrait"/>;
};
