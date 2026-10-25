import {readFileSync,realpathSync,statSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,relative,isAbsolute} from 'node:path';
import {createHash} from 'node:crypto';
import type {Timeline,ResolvedMedia,MediaItem,Geometry,ReviewedMap,ApprovedNumericSeries} from '../remotion/schema';
import {assertTimeline,assertMedia,fail} from '../remotion/schema';
import {PNG} from 'pngjs';

const sha=(data:Buffer)=>createHash('sha256').update(data).digest('hex');
export type MediaEntry={assetId:string;path:string;originalSha256:string;approvalRecordId:string;sourceKind:'APPROVED_LOCAL'|'SYNTHETIC';mime:MediaItem['mime']};
export type ResolveManifest={approvedNumericSeries?:Record<string,ApprovedNumericSeries>;projectId:string;g4ManifestSha256:string;mediaRoot:string;assets:MediaEntry[];geometries:Geometry[];maps:ReviewedMap[];fontFile:string;fontSha256:string;fontFamily:string;sourceKind:'APPROVED_LOCAL'|'SYNTHETIC';syntheticNumericSeries?:Record<string,{fixtureId:string;values:number[]}>};
export function loadApprovedMedia(t:Timeline, manifest:ResolveManifest):ResolvedMedia{
 assertTimeline(t);
 if(manifest.projectId!==t.project_id||!/^[a-f0-9]{64}$/.test(manifest.g4ManifestSha256))fail('RENDER_G4_DRAFT_MISMATCH',t.project_id,'Trusted project G4 manifest SHA required');
 const root=realpathSync(resolve(manifest.mediaRoot));
 const assets:ResolvedMedia['assets']={};
 for(const entry of manifest.assets){
  if(!entry.approvalRecordId||entry.sourceKind!==manifest.sourceKind||!entry.assetId)fail('RENDER_MEDIA_UNAPPROVED',entry.assetId,'Review evidence/asset identity missing');
  if(entry.path.startsWith('http:')||entry.path.startsWith('https:')||entry.path.startsWith('data:'))fail('RENDER_REMOTE_MEDIA_BLOCKED',entry.assetId,'Never fetch remote media');
  const requested=resolve(root,entry.path);
  const candidate=relative(root,requested);
  if(candidate.startsWith('..')||isAbsolute(candidate))fail('RENDER_MEDIA_PATH_UNSAFE',entry.assetId,'Reject absolute escape or parent traversal');
  let p=requested;
  try{p=realpathSync(requested);}catch{fail('RENDER_MEDIA_MISSING',entry.assetId,'Approved original missing from local immutable store');}
  const rel=relative(root,p);
  if(rel.startsWith('..')||isAbsolute(rel)||!statSync(p).isFile())fail('RENDER_MEDIA_PATH_UNSAFE',entry.assetId,'Media must live under immutable media root');
  const bytes=readFileSync(p);
  if(sha(bytes)!==entry.originalSha256)fail('RENDER_MEDIA_SHA_MISMATCH',entry.assetId,'SHA of immutable local source bytes changed');
  if(assets[entry.assetId])fail('RENDER_MEDIA_DUPLICATE',entry.assetId,'Duplicate media identity');
  assets[entry.assetId]={assetId:entry.assetId,originalSha256:entry.originalSha256,approvalRecordId:entry.approvalRecordId,
    sourceKind:entry.sourceKind,mime:entry.mime,dataUri:'data:'+entry.mime+';base64,'+bytes.toString('base64')};
 }
 const fontFile=realpathSync(resolve(manifest.fontFile));
 const fontBytes=readFileSync(fontFile);
 if(sha(fontBytes)!==manifest.fontSha256)fail('RENDER_FONT_SHA_MISMATCH',fontFile,'Measured font source changed');
 const media:ResolvedMedia={assets,geometries:Object.fromEntries(manifest.geometries.map(x=>[x.geometryRef,x])),maps:Object.fromEntries(manifest.maps.map(x=>[x.historicalMapId,x])),
   fontSha256:manifest.fontSha256,fontFamily:manifest.fontFamily,fontDataUri:'data:font/ttf;base64,'+fontBytes.toString('base64'),
   sourceKind:manifest.sourceKind,authorizingG4ManifestSha256:manifest.g4ManifestSha256,
   ...(manifest.sourceKind==="APPROVED_LOCAL"&&manifest.approvedNumericSeries?{approvedNumericSeries:manifest.approvedNumericSeries}:{}),
    ...(manifest.sourceKind==='SYNTHETIC'&&manifest.syntheticNumericSeries?{syntheticNumericSeries:manifest.syntheticNumericSeries}:{})};
 assertMedia(t,media);
 return media;
}
/** Generated *only* for test fixtures; never claims a current G3 review. */
export function makeSyntheticManifest(t:Timeline,directory:string,fontFile:string):ResolveManifest{
 mkdirSync(directory,{recursive:true});
 const ids=[...new Set(t.scenes.flatMap(s=>s.layers.map(l=>l.asset_id).filter((x):x is string=>Boolean(x))))];
 const assets=ids.map((id,i)=>{
  const png=new PNG({width:640,height:360,colorType:6});
  for(let y=0;y<360;y++)for(let x=0;x<640;x++){
   let k=(y*640+x)*4;
   png.data[k]=110+(i*23+x/12)%110;
   png.data[k+1]=95+(i*17+y/7)%120;
   png.data[k+2]=65+(i*19+x/13)%110;
   png.data[k+3]=255;
  }
  const bytes=PNG.sync.write(png);
  const path=id+'.png';writeFileSync(resolve(directory,path),bytes);
  return {assetId:id,path,originalSha256:sha(bytes),approvalRecordId:'SYNTHETIC_TEST_ONLY_'+id,sourceKind:'SYNTHETIC' as const,mime:'image/png' as const};
 });
 const maps=t.scenes.flatMap(scene=>scene.layers.filter(l=>l.layer_kind==='map'&&l.map_binding).map((l,i)=>{
  const original=assets.find(x=>x.assetId===l.asset_id);
  if(!original)fail('SYNTHETIC_MAP_MISSING',l.layer_id,'Synthetic image not generated');
  return {historicalMapId:l.map_binding!.historical_map_id,projection:'mercator',
    viewport:[9,49,13,53] as [number,number,number,number],
    reviewedYear:scene.template_id==='T07'?(i===0?1871:1914):1871,
    sourceOriginalSha256:original!.originalSha256,
    coordinateKind:l.map_binding!.coordinate_kind as ReviewedMap['coordinateKind']};
 }));
 const geos=t.scenes.flatMap(s=>s.layers.filter(l=>l.path_geometry_ref).map(l=>{
  const isRoute=l.layer_kind==='route';
  return {geometryRef:l.path_geometry_ref!,sourceOriginalSha256:assets.find(x=>x.assetId===s.layers.find(x=>x.layer_kind==='map')?.asset_id)?.originalSha256??'f'.repeat(64),
    coordinateSpace:isRoute?'WGS84' as const:'ANNOTATION_CANVAS' as const,
    historicalMapId:isRoute?s.layers.find(x=>x.layer_kind==='map')?.map_binding?.historical_map_id??null:null,
    reviewedYear:isRoute?1871:null,
    bbox:isRoute?[9,49,13,53] as [number,number,number,number]:null,
    coordinates:isRoute?[[9.8,49.5],[10.7,50.2],[11.8,51.9]] as [number,number][]:[[0.08,0.5],[0.45,0.2],[0.91,0.5]] as [number,number][]
  };
 }));
 return {projectId:t.project_id,g4ManifestSha256:sha(Buffer.from('SYNTHETIC TEST G4 '+t.project_id)),
  mediaRoot:directory,assets,geometries:geos,maps,fontFile,fontSha256:sha(readFileSync(fontFile)),
  fontFamily:'Arial',sourceKind:'SYNTHETIC'};
}
