/** B2-06: 61-scene deterministic synthetic B1 long-project rendering and navigation
 * smoke. Video output is explicitly a short excerpt, NOT a full longform deliverable.
 */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {performance} from 'node:perf_hooks';
import {createHash} from 'node:crypto';
import {bundle} from '@remotion/bundler';
import {renderStill,renderMedia,selectComposition} from '@remotion/renderer';
import {PNG} from 'pngjs';
import {activeScene,assertTimeline,type Timeline} from '../remotion/schema';
import {adaptSyntheticT05Chronology} from './synthetic-t05-chronology';
import {makeSyntheticManifest,loadApprovedMedia} from './media';

const root=resolve(import.meta.dirname,'..');
const out=resolve(root,'.artifacts/renders');
mkdirSync(out,{recursive:true});
const compiled=JSON.parse(readFileSync(resolve(root,'.artifacts/compiled-30.json'),'utf8')) as Record<string,Timeline>;
const templates=compiled.A.scenes;
if(templates.length<10)throw Error('B2_LONGFORM_B1_COMPILER_SCENES_MISSING');
const scenes=Array.from({length:61},(_,i)=>{
 const source=structuredClone(templates[i%templates.length]);
 return {...source,scene_id:'scene_b2_long_'+String(i+1).padStart(3,'0'),
  setup_id:'setup_b2_long_'+String(i+1).padStart(3,'0'),start_frame:0};
});
let next=0;
for(const scene of scenes){scene.start_frame=next;next+=scene.duration_frames;}
const timeline=adaptSyntheticT05Chronology({...structuredClone(compiled.A),scenes,total_frames:next});
assertTimeline(timeline);
const t0=performance.now();
const checks=Array.from({length:1000},(_,i)=>Math.floor(i*timeline.total_frames/1000));
for(const seek of checks){const {scene,localFrame}=activeScene(timeline,seek);
 if(localFrame<0||localFrame>=scene.duration_frames)throw Error('B2_LONGFORM_SEEK_OUTSIDE_SCENE');}
const seekMs=performance.now()-t0;
const seekThresholdMs=2000;
if(seekMs>=seekThresholdMs)throw Error('B2_LONGFORM_SEEK_BUDGET '+seekMs);
const font=resolve(process.env.WINDIR??'C:\\Windows','Fonts','arial.ttf');
const media=loadApprovedMedia(timeline,makeSyntheticManifest(timeline,resolve(root,'.artifacts/media/b2-longform'),font));
const serveUrl=await bundle({entryPoint:resolve(root,'remotion/entry.tsx')});
const comp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps:{timeline,media}});
const samples=[0,30,60].map(i=>({scene:i,frame:scenes[i].start_frame+Math.floor(scenes[i].duration_frames/2)}));
const hashes=[];
for(const row of samples){
 const owner=activeScene(timeline,row.frame).scene;
 if(owner.scene_id!==scenes[row.scene].scene_id)throw Error('B2_LONGFORM_SCENE_OWNER_INVALID '+row.scene);
 const file=resolve(out,'b2-longform-scene-'+row.scene+'.png');
 await renderStill({serveUrl,composition:comp,inputProps:{timeline,media},frame:row.frame,output:file,imageFormat:'png'});
 const bytes=readFileSync(file),png=PNG.sync.read(bytes);
 if(png.width!==1920||png.height!==1080||new Set(png.data).size<3)
  throw Error('B2_LONGFORM_FRAME_BLANK '+row.scene);
 hashes.push({scene:row.scene,sceneId:owner.scene_id,frame:row.frame,width:png.width,height:png.height,sha256:createHash('sha256').update(bytes).digest('hex')});
}
const video=resolve(out,'b2-61-scene-project-first-60f-EXCERPT.mp4');
const rangeEnd=Math.min(59,timeline.total_frames-1);
await renderMedia({serveUrl,composition:{...comp,durationInFrames:rangeEnd+1},
 inputProps:{timeline,media},codec:'h264',
 outputLocation:video,pixelFormat:'yuv420p',crf:22,overwrite:true});
const probe=spawnSync('ffprobe',['-v','error','-select_streams','v:0',
 '-count_frames','-show_entries','stream=codec_name,width,height,r_frame_rate,nb_frames,nb_read_frames,duration','-of','json',video],{encoding:'utf8'});
if(probe.status!==0)throw Error('B2_LONGFORM_FFPROBE_FAILED '+probe.stderr);
const info=JSON.parse(probe.stdout).streams[0];
if(info.codec_name!=='h264'||info.width!==1920||info.height!==1080||info.r_frame_rate!=='30/1'||
    Number(info.nb_read_frames)!==rangeEnd+1||Number(info.nb_frames)!==rangeEnd+1||
    Math.abs(Number(info.duration)-(rangeEnd+1)/30)>1/30)
 throw Error('B2_LONGFORM_MP4_INVALID '+JSON.stringify(info));
const evidence={status:'LOCAL_PASS',scope:'61_SCENE_PROJECT_PIXEL_SMOKE_AND_REAL_MP4_EXCERPT_ONLY',
 provenance:'SYNTHETIC_B1_COMPILER_NOT_OPERATOR_APPROVED',sceneCount:61,totalFrames:timeline.total_frames,
 navigation:{seeks:1000,elapsedMs:seekMs,thresholdMs:seekThresholdMs},snapshots:hashes,
 video:{path:video,framesRendered:rangeEnd+1,ffprobe:info,fullLongformRendered:false}};
writeFileSync(resolve(out,'b2-longform-61-scene.json'),JSON.stringify(evidence,null,2));
console.log(JSON.stringify(evidence));
