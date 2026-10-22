import React from 'react';
import type {Scene,ResolvedMedia,Layer} from '../schema';
import {fail} from '../schema';
import {BaseTemplate} from '../Primitives';

/** Exact source-date ports and frozen beat windows; all SVG geometry is camera-local. */
export function timelineRail(scene:Scene){
 const dates=scene.layers.filter(l=>l.layer_kind==='date');
 if(dates.length<2||dates.length>6||dates.some(l=>!l.text||!l.source_claim_id))
  fail('T05_CHRONOLOGY_INVALID',scene.setup_id,'Requires 2-6 claim-backed authored dates');
 const rail=scene.layers.find(l=>l.layer_kind==='annotation');
 if(!rail)fail('RENDER_TIMELINE_COLLISION',scene.setup_id,'Compiled non-text rail slot missing');
 const r=rail.rect_px,horizontal=r.w>=r.h;
 const axis=horizontal?r.y+r.h/2:r.x+r.w/2;
 const rects=dates.map(d=>d.rect_px);
 // All labels must be on one side of the approved, designated rail.
 const before=rects.every(d=>horizontal?d.y+d.h+6<=axis:d.x+d.w+6<=axis);
 const after=rects.every(d=>horizontal?d.y-6>=axis:d.x-6>=axis);
 if(!before&&!after)fail('RENDER_TIMELINE_COLLISION',scene.setup_id,'Rail crosses measured date/text content');
 const ordered=[...dates].sort((a,b)=>(horizontal?a.rect_px.x-b.rect_px.x:a.rect_px.y-b.rect_px.y));
 const years=ordered.map(l=>l.text!.match(/\b\d{3,4}\b/)?.[0]).map(x=>x?Number(x):null);
 if(years.every(x=>x!==null)&&years.some((y,i)=>i>0&&y!>years[i-1]!))
  fail('T05_CHRONOLOGY_INVALID',scene.setup_id,'Authored dates must be strictly increasing');
 const anchor=(layer:Layer):[number,number]=>{
  const b=layer.rect_px;
  return horizontal?[b.x+b.w/2,before?b.y+b.h:b.y]:
    [before?b.x+b.w:b.x,b.y+b.h/2];
 };
 const aligned=(port:[number,number]):[number,number]=>horizontal?[port[0],axis]:[axis,port[1]];
 const edges=ordered.slice(1).map((next,i)=>{
  const previous=ordered[i],a=anchor(previous),b=anchor(next);
  const aa=aligned(a),bb=aligned(b);
  const beat=scene.staging.beat_sequence.find(row=>row.focus_layer_id===next.layer_id) ??
    scene.staging.beat_sequence.find(row=>row.activated_layer_ids.includes(next.layer_id)&&
      row.local_start_frame>0);
  if(!beat)fail('T05_STAGING_MISSING',next.layer_id,'Date lacks a frozen authored reveal beat');
  const xy=([x,y]:[number,number])=>x.toFixed(2)+' '+y.toFixed(2);
  return {from:previous.layer_id,to:next.layer_id,start:beat.local_start_frame,end:beat.local_end_frame,
    d:`M ${xy(a)} L ${xy(aa)} L ${xy(bb)} L ${xy(b)}`,port:bb};
 });
 return {edges,rail:rail.layer_id};
}
export const T05:React.FC<{scene:Scene;frame:number;media:ResolvedMedia}>=({scene,frame,media})=>{
 const {edges}=timelineRail(scene);
 const underlay=<svg viewBox="0 0 1920 1080" width={1920} height={1080}
   style={{position:'absolute',inset:0,pointerEvents:'none'}} data-timeline-rail={scene.setup_id}>
   {edges.map((edge,i)=>{
    const p=Math.max(0,Math.min(1,(frame-edge.start)/(edge.end-edge.start||1)));
    return <path key={edge.to} data-rail-edge={i} data-rail-to={edge.to}
      d={edge.d} fill="none" stroke="#806449" strokeWidth={7}
      strokeLinecap="round" pathLength={1} strokeDasharray="1" strokeDashoffset={1-p}/>;
   })}
  </svg>;
 return <BaseTemplate scene={scene} frame={frame} media={media} decor="timeline" underlay={underlay}/>;
};
