/** Test-only adapter for synthetic B1 compiler placeholders, NEVER production claims.
 * Keep layer IDs, geometry, source claims, staging, and source provenance unchanged.
 * Explicit chronology is assigned in the frozen spatial reading order.
 */
import type {Timeline} from '../remotion/schema';

const SYNTHETIC_DATES=['300 BCE','100 BCE','44 CE','476 CE','1492 CE','1914 CE'] as const;
export function adaptSyntheticT05Chronology(timeline:Timeline):Timeline{
 const adapted=structuredClone(timeline);
 for(const scene of adapted.scenes.filter(s=>s.template_id==='T05')){
  const dates=scene.layers.filter(l=>l.layer_kind==='date');
  if(dates.length<2||dates.length>6)throw Error('SYNTHETIC_T05_DATE_COUNT_INVALID');
  const centers=dates.map(d=>({x:d.rect_px.x+d.rect_px.w/2,y:d.rect_px.y+d.rect_px.h/2}));
  const horizontal=Math.max(...centers.map(p=>p.x))-Math.min(...centers.map(p=>p.x))>=
    Math.max(...centers.map(p=>p.y))-Math.min(...centers.map(p=>p.y));
  const ordered=[...dates].sort((a,b)=>horizontal?a.rect_px.x-b.rect_px.x:a.rect_px.y-b.rect_px.y);
  ordered.forEach((date,i)=>{date.text=SYNTHETIC_DATES[i];});
 }
 return adapted;
}
