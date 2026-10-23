/** B2-04 native Windows Remotion motion-phase discriminators, synthetic B1 inputs. */
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {bundle} from '@remotion/bundler';
import {renderMedia,renderStill,selectComposition} from '@remotion/renderer';
import {PNG} from 'pngjs';
import type {Timeline,Motion,Scene} from '../remotion/schema';
import {assertTimeline,RenderBlocked} from '../remotion/schema';
import {loadApprovedMedia,makeSyntheticManifest} from './media';
import presets from '../../contracts/registries/motion-presets.v1.json';

const root=resolve(import.meta.dirname,'..');
const output=resolve(root,'.artifacts/renders');
mkdirSync(output,{recursive:true});
const compiled=JSON.parse(readFileSync(resolve(root,'.artifacts/compiled-30.json'),'utf8')) as Record<string,Timeline>;
const scene=compiled.A.scenes.find(s=>s.template_id==='T03');
if(!scene)throw Error('B2_MOTION_T03_MISSING');
const timeline=structuredClone(compiled.A);
timeline.scenes=[{...structuredClone(scene),start_frame:0}];
timeline.total_frames=scene.duration_frames;
const cards=timeline.scenes[0].layers.filter(l=>l.layer_kind==='archival_photo');
if(cards.length!==3)throw Error('B2_MOTION_CARD_ASSETS_MISSING');
const font=resolve(process.env.WINDIR??'C:\\Windows','Fonts','arial.ttf');
const sourceDir=resolve(root,'.artifacts/media/b2-motion');
const hashing=(bytes:Buffer)=>createHash('sha256').update(bytes).digest('hex');
const baseline=structuredClone(timeline.scenes[0].events[0]);
const duration=Math.min(20,Math.max(3,Math.floor(scene.duration_frames/8)));
const start=Math.min(scene.duration_frames-duration-1,Math.max(0,Math.floor(scene.duration_frames/3)));
function sampleEvent(preset:string,params:Record<string,unknown>,space:string,targets:string[]):Motion{
 return {...structuredClone(baseline),event_id:'event_b2_'+preset.replace(/-/g,'_'),
  preset_id:preset,layer_id:targets[0],affected_layer_ids:targets,
  start_frame:start,duration_frames:duration,motion_space:space,params,
  stagger:null,keyframes:[{frame:0,value:0,easing:'linear'},{frame:duration,value:1,easing:'ease_in_out'}]};
}
const syntheticOriginal=makeSyntheticManifest(timeline,sourceDir,font).assets.find(a=>a.assetId===cards[0].asset_id);
if(!syntheticOriginal)throw Error('B2_PHOTO_SOURCE_UNTRUSTED');
const cases=[
 {name:'pop-in',event:sampleEvent('pop-in',
  {from_scale:0.88,to_scale:1,overshoot:0.07},'layer_local',[cards[0].layer_id])},
 {name:'photo-card-enter',event:sampleEvent('photo-card-enter',
  {border_px:11,shadow_px:24,start_rotation_deg:-3,end_rotation_deg:0,
   source_original_sha256:syntheticOriginal.originalSha256},'layer_local',[cards[0].layer_id])},
 {name:'cross-dissolve',event:sampleEvent('cross-dissolve',
  {out_layer_id:cards[0].layer_id,in_layer_id:cards[1].layer_id,mix_curve:'ease_in_out'},
  'screen',[cards[0].layer_id,cards[1].layer_id])},
 {name:'whip-pan',event:sampleEvent('whip-pan',
  {direction:'left',sweep_px:150,motion_blur_px:8,max_use_per_minute:1},
  'screen',[cards[0].layer_id])},
];
const serveUrl=await bundle({entryPoint:resolve(root,'remotion/entry.tsx')});
const result:unknown[]=[];
for(const row of cases){
 const t=structuredClone(timeline);
 t.scenes[0].events.push(row.event);
 assertTimeline(t);
 const media=loadApprovedMedia(t,makeSyntheticManifest(t,sourceDir,font));
 const comp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps:{timeline:t,media}});
 const sampleFrames=[start,start+Math.floor(duration/2),start+duration];
 const hashes:string[]=[];
 for(const frame of sampleFrames){
  const file=resolve(output,'b2-'+row.name+'-'+frame+'.png');
  await renderStill({serveUrl,composition:comp,inputProps:{timeline:t,media},frame,output:file,imageFormat:'png'});
  const bytes=readFileSync(file),png=PNG.sync.read(bytes);
  if(png.width!==1920||png.height!==1080||new Set(png.data).size<3)throw Error('B2_MOTION_BLANK_'+row.name);
  hashes.push(hashing(Buffer.from(png.data)));
  result.push({preset:row.name,frame,sha256:hashing(bytes),pixelHash:hashes.at(-1),source:'SYNTHETIC'});
 }
 if(new Set(hashes).size<2)throw Error('B2_MOTION_PHASES_INERT_'+row.name);
 if((row.name==='whip-pan'||row.name==='cross-dissolve')&&start>0){
  const before=start-1;
  const baseMedia=loadApprovedMedia(timeline,makeSyntheticManifest(timeline,sourceDir,font));
  const baseComp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',
    inputProps:{timeline,media:baseMedia}});
  const basePath=resolve(output,`b2-${row.name}-before-baseline.png`);
  const alteredPath=resolve(output,`b2-${row.name}-before-event.png`);
  await renderStill({serveUrl,composition:baseComp,inputProps:{timeline,media:baseMedia},
    frame:before,output:basePath,imageFormat:'png'});
  await renderStill({serveUrl,composition:comp,inputProps:{timeline:t,media},
    frame:before,output:alteredPath,imageFormat:'png'});
  const basePixels=PNG.sync.read(readFileSync(basePath)).data;
  const alteredPixels=PNG.sync.read(readFileSync(alteredPath)).data;
  if(!basePixels.equals(alteredPixels))
    throw Error(`B2_${row.name.toUpperCase().replace(/-/g,'_')}_RETROACTIVE_MOTION: transition changed pre-start frame`);
  result.push({preset:row.name,frame:before,preStartPixelMatch:true,source:'SYNTHETIC'});
 }
}
// Pixel discriminators for native shape + timed directional reveal.
// A source-preserving change of native mask may not replace the G3 original.
const maskSource=cards[0];
const maskEvent=sampleEvent('title-mask-reveal',
  {direction:'left',distance_px:0,feather_px:12},'layer_local',[maskSource.layer_id]);
const nativeMask=(kind:'none'|'rectangle'|'ellipse',feather_px:number,withReveal:boolean)=>{
 const t=structuredClone(timeline);
 const layer=t.scenes[0].layers.find(l=>l.layer_id===maskSource.layer_id)!;
 layer.mask={kind,asset_id:null,feather_px};
 if(withReveal)t.scenes[0].events.push(maskEvent);
 assertTimeline(t);
 return t;
};
async function maskStill(t:Timeline,frame:number,label:string){
 const media=loadApprovedMedia(t,makeSyntheticManifest(t,sourceDir,font));
 const comp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps:{timeline:t,media}});
 const file=resolve(output,'b2-mask-'+label+'.png');
 await renderStill({serveUrl,composition:comp,inputProps:{timeline:t,media},frame,output:file,imageFormat:'png'});
 const bytes=readFileSync(file),png=PNG.sync.read(bytes);
 if(png.width!==1920||png.height!==1080)throw Error('B2_MASK_INVALID_FRAME_'+label);
 return {path:file,sha256:hashing(bytes),png};
}
function maskDiff(a:PNG,b:PNG,layer:typeof maskSource){
 const r=layer.rect_px;
 let changed=0,count=0,total=0;
 for(let y=r.y;y<r.y+r.h;y+=2)for(let x=r.x;x<r.x+r.w;x+=2){
  const k=(y*1920+x)*4,delta=Math.abs(a.data[k]-b.data[k])+
    Math.abs(a.data[k+1]-b.data[k+1])+Math.abs(a.data[k+2]-b.data[k+2]);
  changed+=delta>12?1:0;total+=delta/3;count++;
 }
 return {changedPixels:changed,sampledPixels:count,meanRGBDifference:total/count};
}
const maskFrame=Math.min(start+Math.floor(duration/2),scene.duration_frames-2);
const maskedRect=await maskStill(nativeMask('rectangle',0,false),maskFrame,'rectangle');
const maskedEllipse=await maskStill(nativeMask('ellipse',0,false),maskFrame,'ellipse');
const maskedFeather=await maskStill(nativeMask('ellipse',16,false),maskFrame,'ellipse-feather16');
const maskedReveal=await maskStill(nativeMask('ellipse',16,true),maskFrame,'ellipse-feather16-reveal-mid');
const maskLedger={
 source:'SYNTHETIC_B1_COMPILED_NOT_REAL_RIGHTS',frame:maskFrame,layerId:maskSource.layer_id,
 nativeShape:maskDiff(maskedRect.png,maskedEllipse.png,maskSource),
 feather:maskDiff(maskedEllipse.png,maskedFeather.png,maskSource),
 reveal:maskDiff(maskedFeather.png,maskedReveal.png,maskSource),
 PNGs:[maskedRect,maskedEllipse,maskedFeather,maskedReveal].map(({path,sha256})=>({path,sha256}))
};
if(maskLedger.nativeShape.changedPixels<15)throw Error('B2_NATIVE_ELLIPSE_VISUALLY_INERT');
if(maskLedger.feather.changedPixels<15)throw Error('B2_NATIVE_FEATHER_VISUALLY_INERT');
if(maskLedger.reveal.changedPixels<15)throw Error('B2_SHAPE_REVEAL_VISUALLY_INERT');
writeFileSync(resolve(output,'b2-mask-roi.json'),JSON.stringify(maskLedger,null,2));
result.push({kind:'native_mask_pixels',...maskLedger});

const cropFixture=structuredClone(timeline);
const cropTarget=cropFixture.scenes[0].layers.find(l=>l.layer_id===maskSource.layer_id)!;
cropTarget.crop_normalized={x:0.1,y:0.1,w:0.8,h:0.8};
assertTimeline(cropFixture);
const cropBaseline=await maskStill(timeline,maskFrame,'crop-before');
const cropAfter=await maskStill(cropFixture,maskFrame,'crop-after');
const cropPixelChange=maskDiff(cropBaseline.png,cropAfter.png,maskSource);
if(cropPixelChange.changedPixels<15)throw Error('B2_APPROVED_ORIGINAL_CROP_VISUALLY_INERT');
const cropMediaBefore=makeSyntheticManifest(timeline,sourceDir,font).assets.find(a=>a.assetId===maskSource.asset_id);
const cropMediaAfter=makeSyntheticManifest(cropFixture,sourceDir,font).assets.find(a=>a.assetId===maskSource.asset_id);
if(!cropMediaBefore||!cropMediaAfter||cropMediaBefore.originalSha256!==cropMediaAfter.originalSha256)
 throw Error('B2_CROP_MUTATED_SYNTHETIC_SOURCE_BYTES');
const cropLedger={source:'SYNTHETIC_B1_COMPILED_NOT_REAL_RIGHTS',layer:maskSource.layer_id,
 frame:maskFrame,originalSha256:cropMediaBefore.originalSha256,
 before:{path:cropBaseline.path,sha256:cropBaseline.sha256},
 after:{path:cropAfter.path,sha256:cropAfter.sha256},roi:cropPixelChange};
writeFileSync(resolve(output,'b2-crop-roi.json'),JSON.stringify(cropLedger,null,2));
result.push({kind:'source_preserving_crop_pixels',...cropLedger});

// Layer-local freeze-hold must visibly pause an overlapping motion phase,
// while keeping the camera and unrelated layer schedule unchanged.
const activePop=cases.find(c=>c.name==='pop-in')!.event;
const popTimeline=structuredClone(timeline);
popTimeline.scenes[0].events.push(activePop);
const heldTimeline=structuredClone(popTimeline);
const frozenEvent=sampleEvent('freeze-hold',{hold_frames:6,preserve_voice:true},
  'layer_local',[cards[0].layer_id]);
frozenEvent.start_frame=start+3;
frozenEvent.duration_frames=6;
frozenEvent.keyframes=[{frame:0,value:1,easing:'linear'},{frame:6,value:1,easing:'linear'}];
frozenEvent.animated_property='opacity';
frozenEvent.phases=[{phase_id:'phase_b2_freeze_hold',kind:'hold',start_offset_frames:0,duration_frames:6,depends_on_phase_ids:[]}];
heldTimeline.scenes[0].events.push(frozenEvent);
assertTimeline(heldTimeline);
const holdFrame=start+7;
const baselineHold=await maskStill(popTimeline,holdFrame,'freeze-baseline');
const activeHold=await maskStill(heldTimeline,holdFrame,'freeze-active');
const frozenROI=maskDiff(baselineHold.png,activeHold.png,maskSource);
if(frozenROI.changedPixels<15)throw Error('B2_LAYER_FREEZE_INERT');
const preHold=await maskStill(popTimeline,start+2,'freeze-pre-baseline');
const withPreHold=await maskStill(heldTimeline,start+2,'freeze-pre-candidate');
if(!preHold.png.data.equals(withPreHold.png.data))throw Error('B2_FREEZE_RETROACTIVE_FRAMES');
const holdLedger={preset:'freeze-hold',source:'SYNTHETIC',frame:holdFrame,
 unchangedPreStart:true,roi:frozenROI,
 PNGs:[baselineHold,activeHold].map(x=>({path:x.path,sha256:x.sha256}))};
writeFileSync(resolve(output,'b2-freeze-hold.json'),JSON.stringify(holdLedger,null,2));
result.push(holdLedger);



if(presets.presets.length!==19||new Set(presets.presets.map(x=>x.render_recipe.primitive)).size!==19)
 throw Error('B2_MOTION_REGISTRY_INCOMPLETE');
let malformed=structuredClone(timeline);
malformed.scenes[0].events.push({...cases[0].event,params:{...cases[0].event.params,in_layer_id:'layer_does_not_exist'}});
let failClosed=false;
try{assertTimeline(malformed);}catch(e){failClosed=e instanceof RenderBlocked&&e.code==='RENDER_MOTION_PARAMS';}
if(!failClosed) {
 // The property passes the schema's identifier grammar; the compositor must
 // still reject the unresolvable target before rendering.
 const media=loadApprovedMedia(malformed,makeSyntheticManifest(malformed,sourceDir,font));
 const comp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps:{timeline:malformed,media}});
 try{await renderStill({serveUrl,composition:comp,inputProps:{timeline:malformed,media},frame:start+5,
   output:resolve(output,'b2-forged-crossfade.png'),imageFormat:'png'});}catch{failClosed=true;}
}
if(!failClosed)throw Error('B2_CROSSFADE_FORGED_TARGET_ACCEPTED');
if(process.argv[2]==='render'){
 const media=loadApprovedMedia(timeline,makeSyntheticManifest(timeline,sourceDir,font));
 const comp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps:{timeline,media}});
 const out=resolve(output,'b2-multi-layer-synthetic.mp4');
 await renderMedia({serveUrl,composition:comp,inputProps:{timeline,media},outputLocation:out,
  codec:'h264',pixelFormat:'yuv420p',crf:22,overwrite:true});
 const probe=spawnSync('ffprobe',['-v','error','-show_entries','stream=codec_name,width,height,r_frame_rate',
 '-select_streams','v:0','-of','json',out],{encoding:'utf8'});
 if(probe.status!==0)throw Error('B2_FFPROBE_FAILED '+probe.stderr);
 const info=JSON.parse(probe.stdout).streams[0];
 if(info.codec_name!=='h264'||info.width!==1920||info.height!==1080||info.r_frame_rate!=='30/1')
  throw Error('B2_MOTION_MP4_INVALID');
 result.push({mp4:out,sha256:hashing(readFileSync(out)),ffprobe:info,source:'SYNTHETIC'});
}
const executedNames=new Set(cases.map(c=>c.name));
const semanticRows=presets.presets.map(p=>({
 preset_id:p.preset_id,primitive:p.render_recipe.primitive,motion_space:p.render_recipe.transform_space,
 source_provenance:'SYNTHETIC_B1_COMPILED_NOT_OPERATOR_RIGHTS',
 evidence:result.filter((entry):entry is Record<string,unknown>=>typeof entry==='object'&&entry!==null&&
   'preset' in entry&&(entry as {preset:string}).preset===p.preset_id),
 result:executedNames.has(p.preset_id)?'PARTIAL_PHASE_PIXEL_PROOF':'NOT_RUN',
 negative_case:p.preset_id==='cross-dissolve'?'forged_target_blocked':null
}));
writeFileSync(resolve(output,'b2-motion-19-presets.json'),JSON.stringify({
 status:'PARTIAL',registryCount:19,
 note:'Actual semantic coverage only for sampled presets; registry names do not establish 19/19.',
 rows:semanticRows
},null,2));
writeFileSync(resolve(output,'b2-motion-phases.json'),JSON.stringify({status:'LOCAL_PASS',
 registryCount:19,cases:result,source:'SYNTHETIC_B1_COMPILED_NOT_LIVE_APPROVED'},null,2));
console.log(JSON.stringify({status:'LOCAL_PASS',renderer:'Remotion Chromium',
 phasePNGs:cases.length*3,source:'SYNTHETIC',mp4:process.argv[2]==='render'}));
