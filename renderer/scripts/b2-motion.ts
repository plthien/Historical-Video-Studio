/** B2-04 native Windows Remotion motion-phase discriminators, synthetic B1 inputs. */
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
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
const caption=timeline.scenes[0].layers.find(l=>l.layer_kind==='text'&&l.text&&l.source_claim_id);
if(!caption)throw Error('B2_MOTION_CLAIM_TEXT_MISSING');
const font=resolve(process.env.WINDIR??'C:\\Windows','Fonts','arial.ttf');
const sourceDir=resolve(root,'.artifacts/media/b2-motion');
const hashing=(bytes:Buffer)=>createHash('sha256').update(bytes).digest('hex');
const baseline=structuredClone(timeline.scenes[0].events[0]);
const cueWord=String((baseline as Motion&{cue_word_id?:string}).cue_word_id??'word_001');
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
 {name:'stagger-reveal',event:sampleEvent('stagger-reveal',
  {ordered_layer_ids:cards.map(card=>card.layer_id),gap_frames:3,direction:'evidence_order'},
  'group_local',cards.map(card=>card.layer_id))},
 {name:'parallax-layers',event:sampleEvent('parallax-layers',
  {near_layer_ids:[cards[0].layer_id],far_layer_ids:[cards[1].layer_id],
   near_strength:.8,far_strength:.25,max_drift_px:80},
  'group_local',[cards[0].layer_id,cards[1].layer_id])},
 {name:'hard-cut',event:sampleEvent('hard-cut',
  {cut_reason:'semantic_change'},'screen',[cards[2].layer_id])},
 {name:'typewriter',event:sampleEvent('typewriter',
  {text_layer_id:caption.layer_id,characters_per_second:55,cursor_visible:true,
   quoted_source_claim_id:caption.source_claim_id!},'layer_local',[caption.layer_id])},
 {name:'kinetic-type',event:sampleEvent('kinetic-type',
  {word_ids:[cueWord],max_offset_px:24,line_preservation:true},
  'layer_local',[caption.layer_id])},
 {name:'text-highlight',event:sampleEvent('text-highlight',
  {source_word_ids:[cueWord],highlight_color_token:'gold',hold_after_frames:15},
  'layer_local',[caption.layer_id])},

];
const serveUrl=await bundle({entryPoint:resolve(root,'remotion/entry.tsx')});
const result:unknown[]=[];
for(const row of cases){
 const t=structuredClone(timeline);
 t.scenes[0].events.push(row.event);
 if(row.name==='kinetic-type'||row.name==='text-highlight'){
  // Synthetic renderer mechanics only. This is not an approved G2 word mapping.
  const target=t.scenes[0].layers.find(layer=>layer.layer_id===caption.layer_id)!;
  const token=/[\p{L}\p{N}][^\s]*/u.exec(target.text??'');
  if(!token)throw Error('B2_SYNTHETIC_WORD_TEXT_MISSING');
  target.word_spans=[{word_id:cueWord,word_text:token[0],
    start:token.index,end:token.index+token[0].length}];
 }
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
  result.push({preset:row.name,frame,path:file,sha256:hashing(bytes),pixelHash:hashes.at(-1),source:'SYNTHETIC_RENDER_FIXTURE'});
 }
 if(new Set(hashes).size<2)throw Error('B2_MOTION_PHASES_INERT_'+row.name);
 const wrongSpace=structuredClone(t);
 wrongSpace.scenes[0].events.find(e=>e.event_id===row.event.event_id)!.motion_space='invalid_space';
 let rejected=false;
 try{assertTimeline(wrongSpace);}catch(error){
  rejected=error instanceof RenderBlocked&&error.code==='RENDER_MOTION_SPACE';
 }
 result.push({preset:row.name,negativeAssertion:'wrong_transform_space',
  typedRejection:rejected,source:'SYNTHETIC_RENDER_FIXTURE'});
 if(!rejected)throw Error('B2_MOTION_NEGATIVE_NOT_BLOCKED_'+row.name);
 if(start>0){
  const before=start-1;
  const baseTimeline=structuredClone(t);
  baseTimeline.scenes[0].events=baseTimeline.scenes[0].events.filter(event=>event.event_id!==row.event.event_id);
  const baseMedia=loadApprovedMedia(baseTimeline,makeSyntheticManifest(baseTimeline,sourceDir,font));
  const baseComp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',
    inputProps:{timeline:baseTimeline,media:baseMedia}});
  const basePath=resolve(output,`b2-${row.name}-before-baseline.png`);
  const alteredPath=resolve(output,`b2-${row.name}-before-event.png`);
  await renderStill({serveUrl,composition:baseComp,inputProps:{timeline:baseTimeline,media:baseMedia},
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
// Presets that require compiler-owned reviewed map/connector geometry or a
// compiled camera track use their real B1 scenes rather than fabricated T03
// layer bindings.
const compiledPresetNames=new Set<string>();
for(const presetId of ['route-line-draw','map-region-wipe','editorial-connector-draw',
                       'camera-pan','camera-push']){
 const found=Object.entries(compiled).flatMap(([variant,value])=>
   value.scenes.map(candidate=>({variant,value,candidate,
     event:candidate.events.find(item=>item.preset_id===presetId)})))
   .find(item=>item.event);
 if(!found||!found.event)continue;
 const t=structuredClone(found.value);
 const isolatedScene={...structuredClone(found.candidate),start_frame:0};
 t.scenes=[isolatedScene];t.total_frames=isolatedScene.duration_frames;
 assertTimeline(t);
 const mediaDir=resolve(root,'.artifacts/media/b2-motion-compiled',presetId);
 const media=loadApprovedMedia(t,makeSyntheticManifest(t,mediaDir,font));
 const comp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps:{timeline:t,media}});
 const event=isolatedScene.events.find(item=>item.event_id===found.event!.event_id)!;
 const frames=[Math.max(0,event.start_frame-1),event.start_frame,
   Math.min(isolatedScene.duration_frames-1,event.start_frame+Math.floor(event.duration_frames/2)),
   Math.min(isolatedScene.duration_frames-1,event.start_frame+event.duration_frames)];
 const phaseHashes:string[]=[];
 for(const frame of frames){
  const file=resolve(output,`b2-${presetId}-compiled-${frame}.png`);
  await renderStill({serveUrl,composition:comp,inputProps:{timeline:t,media},frame,output:file,imageFormat:'png'});
  const bytes=readFileSync(file),png=PNG.sync.read(bytes);
  if(png.width!==1920||png.height!==1080||new Set(png.data).size<3)
   throw Error('B2_MOTION_BLANK_'+presetId);
  phaseHashes.push(hashing(Buffer.from(png.data)));
  result.push({preset:presetId,frame,path:file,sha256:hashing(bytes),pixelHash:phaseHashes.at(-1),
   source:'SYNTHETIC_B1_COMPILER_NOT_OPERATOR_APPROVED',
   camera:presetId.startsWith('camera-')?isolatedScene.camera:null});
 }
 if(new Set(phaseHashes).size<2)throw Error('B2_MOTION_PHASES_INERT_'+presetId);
 if(event.start_frame>0){
  const baselineTimeline=structuredClone(t);
  baselineTimeline.scenes[0].events=baselineTimeline.scenes[0].events.map(item=>
    item.event_id===event.event_id&&item.start_frame+item.duration_frames<isolatedScene.duration_frames
      ?{...item,start_frame:item.start_frame+1}:item);
  const baselineMedia=loadApprovedMedia(baselineTimeline,makeSyntheticManifest(baselineTimeline,mediaDir,font));
  const baselineComp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',
    inputProps:{timeline:baselineTimeline,media:baselineMedia}});
  const baselinePath=resolve(output,`b2-${presetId}-compiled-pre-baseline.png`);
  await renderStill({serveUrl,composition:baselineComp,inputProps:{timeline:baselineTimeline,media:baselineMedia},
    frame:frames[0],output:baselinePath,imageFormat:'png'});
  const eventPixels=PNG.sync.read(readFileSync(resolve(output,`b2-${presetId}-compiled-${frames[0]}.png`))).data;
  const baselinePixels=PNG.sync.read(readFileSync(baselinePath)).data;
  if(!eventPixels.equals(baselinePixels))throw Error('B2_'+presetId.toUpperCase().replace(/-/g,'_')+'_RETROACTIVE_MOTION');
 }
 const wrongSpace=structuredClone(t);
 wrongSpace.scenes[0].events.find(item=>item.event_id===event.event_id)!.motion_space='invalid_space';
 let rejected=false;
 try{assertTimeline(wrongSpace);}catch(error){
  rejected=error instanceof RenderBlocked&&error.code==='RENDER_MOTION_SPACE';
 }
 result.push({preset:presetId,negativeAssertion:'wrong_transform_space',
  typedRejection:rejected,source:'SYNTHETIC_B1_COMPILER_NOT_OPERATOR_APPROVED'});
 if(!rejected)throw Error('B2_MOTION_NEGATIVE_NOT_BLOCKED_'+presetId);
 compiledPresetNames.add(presetId);
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
result.push({preset:'title-mask-reveal',kind:'native_mask_pixels',...maskLedger});

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
Object.assign(frozenEvent,{phases:[{phase_id:'phase_b2_freeze_hold',kind:'hold',start_offset_frames:0,duration_frames:6,depends_on_phase_ids:[]}]});
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
// Derived from executed Chromium PNGs and negative assertions, never names.
const semanticRows=presets.presets.map(p=>{
 const proof=result.filter((entry):entry is Record<string,unknown>=>typeof entry==='object'&&entry!==null&&
   'preset' in entry&&(entry as {preset:string}).preset===p.preset_id);
 const phases=proof.filter(e=>typeof e.frame==='number'&&typeof e.path==='string');
 const verified=phases.length>=3&&phases.every(e=>existsSync(e.path as string)&&
   hashing(readFileSync(e.path as string))===e.sha256);
 const distinct=new Set(phases.map(e=>e.pixelHash)).size>=2;
 const negative=proof.some(e=>e.negativeAssertion==='wrong_transform_space'&&e.typedRejection===true);
 const prestart=proof.some(e=>e.preStartPixelMatch===true);
 const mechanics=verified&&distinct&&negative&&prestart;
 const dependency=p.preset_id==='number-count'?
  'No verified G1 intermediate historical observations for interpolation':
  p.preset_id==='mask-transition'?
  'No authorized two-scene surface identities and overlap window':null;
 const authority=proof.some(e=>e.source==='OPERATOR_APPROVED');
 const status=dependency?'BLOCKED_DEPENDENCY':!phases.length?'NOT_RUN':
  mechanics&&authority?'PASS':mechanics?'PARTIAL':'FAIL_CONFIRMED';
 return {preset_id:p.preset_id,primitive:p.render_recipe.primitive,
  motion_space:p.render_recipe.transform_space,status,
  mechanism_assertions:{validChromiumFrames:verified,distinctActualPixels:distinct,
    negativeWrongSpaceBlocked:negative,prestartInvariant:prestart},
  source_authority:authority?'OPERATOR_APPROVED':'SYNTHETIC_NOT_OPERATOR_APPROVED',
  actual_png_paths:phases.map(e=>e.path),frame_numbers:phases.map(e=>e.frame),
  negative_case:negative?'RENDER_MOTION_SPACE':'NOT_PROVED',
  evidence:proof,blocker:dependency};
});
writeFileSync(resolve(output,'b2-motion-19-presets.json'),JSON.stringify({
 status:semanticRows.every(row=>row.status==='PASS')?'PASS':'FAIL',
 registryCount:19,semanticPassCount:semanticRows.filter(row=>row.status==='PASS').length,
 note:'Strict motion owner: source authority and event-specific semantics must be proved separately.',
 rows:semanticRows
},null,2));
writeFileSync(resolve(output,'b2-motion-phases.json'),JSON.stringify({status:'FAIL',
 registryCount:19,cases:result,source:'SYNTHETIC_B1_COMPILED_NOT_LIVE_APPROVED'},null,2));
const incomplete=semanticRows.filter(row=>row.status!=='PASS');
const strictSemanticOwner=process.argv[2]!=='render';
if(incomplete.length&&strictSemanticOwner){
 console.error(JSON.stringify({status:'FAIL',renderer:'Remotion Chromium',
  phasePNGs:cases.length*3,source:'SYNTHETIC',mp4:process.argv[2]==='render',
  incomplete:incomplete.map(row=>({preset_id:row.preset_id,result:row.status,blocker:row.blocker}))}));
 throw Error('B2_MOTION_SEMANTIC_LEDGER_INCOMPLETE: every one of 19 registered presets requires PASS');
}
console.log(JSON.stringify({status:incomplete.length?'MULTILAYER_PASS_MOTION_INCOMPLETE':'PASS',renderer:'Remotion Chromium',
 phasePNGs:cases.length*3,source:'SYNTHETIC',mp4:process.argv[2]==='render',
 semanticOwner:strictSemanticOwner}));
