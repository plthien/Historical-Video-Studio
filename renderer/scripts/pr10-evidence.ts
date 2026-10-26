/** Native Chromium proof from current SQLite-approved synthetic G1/G3/G4 projects. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {bundle} from '@remotion/bundler';
import {renderStill,selectComposition} from '@remotion/renderer';
import {PNG} from 'pngjs';
import {prepareApprovedLocalHistory} from './approved-host';
import {assertMedia,RenderBlocked} from '../remotion/schema';
import type {HistoryProps} from '../remotion/HistoryComposition';

if(process.platform!=='win32')throw Error('PR10_NATIVE_WINDOWS_REQUIRED');
const root=resolve(import.meta.dirname,'..','..');
const out=resolve(root,'renderer','.artifacts','pr10-evidence');
mkdirSync(out,{recursive:true});
const sha=(b:Buffer)=>createHash('sha256').update(b).digest('hex');
const configs=['numeric','mask'].map(mode=>JSON.parse(readFileSync(resolve(root,'renderer','.artifacts','pr10-'+mode+'.json'),'utf8')));
const bundleUrl=await bundle({entryPoint:resolve(root,'renderer','remotion','entry.tsx')});
const evidence:Record<string,unknown>={kind:'SYNTHETIC_TEST_PROJECT_OPERATOR_APPROVAL_NOT_REAL_HISTORICAL_SOURCE',
                                  platform:process.platform,node:process.version};
function host(config:any):HistoryProps {
 const props=prepareApprovedLocalHistory(config.db,config.artifactRoot,config.project);
 if(props.media.sourceKind!=='APPROVED_LOCAL'||!props.media.authorizingG4ManifestSha256)
  throw Error('PR10_PRODUCTION_HOST_AUTHORITY_MISSING');
 assertMedia(props.timeline,props.media);
 return props;
}
async function frame(props:HistoryProps,at:number,name:string){
 const comp=await selectComposition({serveUrl:bundleUrl,id:'HistoricalTimelineV1',inputProps:props});
 if(comp.width!==1920||comp.height!==1080||comp.fps!==30||at<0||at>=comp.durationInFrames)
  throw Error('PR10_REAL_CHROMIUM_DIMENSIONS_OR_FRAME_MISMATCH');
 const path=resolve(out,name+'.png');
 await renderStill({serveUrl:bundleUrl,composition:comp,inputProps:props,output:path,imageFormat:'png',frame:at});
 const file=readFileSync(path),png=PNG.sync.read(file);
 if(png.width!==1920||png.height!==1080)throw Error('PR10_FRAME_NOT_1920_1080');
 return {path,frame:at,sha256:sha(file),pixelSha256:sha(Buffer.from(png.data)),pixels:png.data};
}
function assertNegative(name:string,run:()=>void){
 try {run()}catch(error){
  if(error instanceof RenderBlocked)return {name,code:error.code};
  throw error;
 }
 throw Error('PR10_NEGATIVE_ACCEPTED: '+name);
}
const numberConfig=configs[0],numeric=host(numberConfig);
const scene=numeric.timeline.scenes[0];
const event=scene.events.find(e=>e.preset_id==='number-count');
if(!event||!event.params.approved_numeric_series_id)throw Error('PR10_G03_REAL_AUTHORED_COUNT_MISSING');
const layer=scene.layers.find(l=>l.layer_id===event.layer_id)!;
const series=numeric.media.approvedNumericSeries?.[String(event.params.approved_numeric_series_id)];
if(!series||series.claimId!==layer.source_claim_id||series.observations.length<3)
 throw Error('PR10_G03_G1_APPROVED_NUMERIC_SERIES_MISSING');
const start=scene.start_frame+event.start_frame;
const mid=start+Math.floor(event.duration_frames/2);
const end=start+event.duration_frames-1;
const numericShots=[await frame(numeric,start,'g03-number-start'),await frame(numeric,mid,'g03-number-middle'),
                    await frame(numeric,end,'g03-number-final')];
if(new Set(numericShots.map(f=>f.pixelSha256)).size<2)
 throw Error('PR10_G03_CHROMIUM_NUMBER_COUNT_INERT');
const numericNegatives=[
 assertNegative('wrong-claim',()=>{
  const p=structuredClone(numeric);p.media.approvedNumericSeries![series.seriesId]!.claimId='forged_claim';
  assertMedia(p.timeline,p.media);
 }),
 assertNegative('wrong-endpoint',()=>{
  const p=structuredClone(numeric);p.media.approvedNumericSeries![series.seriesId]!.endValue='1915';
  assertMedia(p.timeline,p.media);
 }),
 assertNegative('wrong-G1-approval',()=>{
  const p=structuredClone(numeric);p.media.approvedNumericSeries![series.seriesId]!.approvalId='forged';
  assertMedia(p.timeline,p.media);
 })
];
evidence.g03={sourceClaim:series.claimId,reviewedSeriesId:series.seriesId,
              approvalId:series.approvalId,approvedSha256:series.seriesSha256,
              observedStrings:series.observations.map(x=>x.value),
              frames:numericShots.map(({pixels,...x})=>x),negatives:numericNegatives};

const maskConfig=configs[1];
const before=host(maskConfig);
const maskLayer=before.timeline.scenes[0].layers.find(l=>l.mask.kind==='polygon_asset');
if(!maskLayer||!before.media.maskDerivatives?.[maskLayer.mask.asset_id!])
 throw Error('PR10_G05_REAL_REVIEWED_G3_CUTOUT_MISSING');
const target=Math.min(before.timeline.total_frames-1,Math.max(1,Math.floor(before.timeline.total_frames/3)));
const a=await frame(before,target,'g05-g06-selected-A');
const maskNegative=[
 assertNegative('missing-derivative',()=>{
  const p=structuredClone(before);p.media.maskDerivatives={};assertMedia(p.timeline,p.media);
 }),
 assertNegative('wrong-mask-parent',()=>{
  const p=structuredClone(before);p.media.maskDerivatives![maskLayer.mask.asset_id!]!.parentOriginalSha256='f'.repeat(64);
  assertMedia(p.timeline,p.media);
 }),
 assertNegative('missing-mask-bytes',()=>{
  const p=structuredClone(before);delete p.media.assets[maskLayer.mask.asset_id!];assertMedia(p.timeline,p.media);
 })
];
const python=resolve(root,'.venv','Scripts','python.exe');
const switchResult=spawnSync(python,['-m','renderer.scripts.pr10_switch','--selected','b'],
                             {cwd:root,encoding:'utf8',windowsHide:true});
if(switchResult.status!==0)throw Error('PR10_G06_OPERATOR_PATCH_FAILED: '+(switchResult.stderr||switchResult.stdout));
const after=host(maskConfig);
const chosen=after.timeline.scenes[0].layers.find(l=>l.layer_id===maskLayer.layer_id);
if(chosen?.asset_id===maskLayer.asset_id||chosen?.mask.kind!=='polygon_asset')
 throw Error('PR10_G06_A_B_CHANGE_NOT_RECOMPILED');
if(before.timeline.story_sha256!==after.timeline.story_sha256||
   before.timeline.audio_sha256!==after.timeline.audio_sha256||
   before.timeline.word_map_sha256!==after.timeline.word_map_sha256)
 throw Error('PR10_G06_FROZEN_G1_G2_SOURCE_CHANGED');
const b=await frame(after,target,'g05-g06-selected-B');
if(a.pixelSha256===b.pixelSha256)throw Error('PR10_G06_SELECTED_B_PIXELS_IDENTICAL_TO_A');
const back=spawnSync(python,['-m','renderer.scripts.pr10_switch','--selected','a'],
                     {cwd:root,encoding:'utf8',windowsHide:true});
if(back.status!==0)throw Error('PR10_G06_RETURN_A_FAILED: '+(back.stderr||back.stdout));
const returned=host(maskConfig);
const a2=await frame(returned,target,'g05-g06-returned-A');
if(a2.pixelSha256!==a.pixelSha256)throw Error('PR10_G06_COLD_A_B_A_PIXELS_CHANGED');
evidence.g05={derivativeReview:before.media.maskDerivatives![maskLayer.mask.asset_id!],
             negative:maskNegative};
evidence.g06={operatorPatch:switchResult.stdout.trim(),returnPatch:back.stdout.trim(),
             screenshots:[a,b,a2].map(({pixels,...x})=>x),
             originalLayerId:maskLayer.layer_id,
             originalA:maskLayer.asset_id,selectedB:chosen!.asset_id,
             pixelsChanged:true,backToAStable:true};
writeFileSync(resolve(out,'g03-g05-g06-real-chromium.json'),JSON.stringify(evidence,null,2));
console.log(JSON.stringify({status:'LOCAL_PASS',source:'SYNTHETIC_G1_G3_REVIEWS',
                            g03Frames:numericShots.length,g05Mask:true,g06ABChanged:true,
                            evidence:resolve(out,'g03-g05-g06-real-chromium.json')}));
