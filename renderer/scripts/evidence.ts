import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname,join} from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {bundle} from '@remotion/bundler';
import {renderStill,renderMedia,selectComposition} from '@remotion/renderer';
import {PNG} from 'pngjs';
import {assertTimeline,activeScene,RenderBlocked,type Timeline} from '../remotion/schema';
import {loadApprovedMedia,makeSyntheticManifest} from './media';

const root=resolve(import.meta.dirname,'..');
const repo=resolve(root,'..');
const sha=(bytes:Buffer)=>createHash('sha256').update(bytes).digest('hex');
const args=process.argv.slice(2);
const mode=args[0]??'frames';
const selected=(args.find((x)=>x==='--templates')!==undefined?args[args.indexOf('--templates')+1].split(','):[]);
const isShared=args.includes('shared-composition');
const isSingle=args.includes('single-scene');
const exampleFile=resolve(repo,'contracts/examples/visual_cases/CompiledTimeline.visual_cases.synthetic.json');
const source=JSON.parse(readFileSync(exampleFile,'utf8')) as Timeline;
const compiledFile=resolve(root,'.artifacts/compiled-30.json');
const compiled=JSON.parse(readFileSync(compiledFile,'utf8')) as Record<string,Timeline>;
if(JSON.stringify(Object.keys(compiled).sort())!==JSON.stringify(['A','B','C']))throw new Error('B1_COMPILED_30_REQUIRED: genuine compiler-generated A/B/C inputs missing');
const fontFile=resolve(process.env.WINDIR??'C:\\Windows','Fonts','arial.ttf');
const output=resolve(root,'.artifacts','renders');
mkdirSync(output,{recursive:true});
const templateList=selected.length?selected:isShared?['T01']:isSingle?['T01']:Array.from({length:10},(_,i)=>'T'+String(i+1).padStart(2,'0'));
const sourceCases=Array.from({length:3},(_,i)=>['A','B','C'][i]).flatMap(variant=>compiled[variant].scenes.filter(s=>templateList.includes(s.template_id)).map(s=>({variant,scene:s})));
const entrypoint=resolve(root,'remotion','entry.tsx');
const bundlePath=await bundle({entryPoint:entrypoint,webpackOverride:(config)=>config,logLevel:'error'});
const metrics:unknown[]=[];
async function oneStill(timeline:Timeline,frame:number,label:string,mediaDir:string){
 const manifest=makeSyntheticManifest(timeline,mediaDir,fontFile);
 const media=loadApprovedMedia(timeline,manifest);
 const props={timeline,media};
 const comp=await selectComposition({serveUrl:bundlePath,id:'HistoricalTimelineV1',inputProps:props});
 if(comp.width!==1920||comp.height!==1080||comp.fps!==30||comp.durationInFrames!==timeline.total_frames)throw new Error('RENDER_FROZEN_FORMAT_MISMATCH');
 const path=resolve(output,label+'.png');
 await renderStill({serveUrl:bundlePath,composition:comp,inputProps:props,output:path,imageFormat:'png'});
 const png=PNG.sync.read(readFileSync(path));
 if(png.width!==1920||png.height!==1080)throw new Error('RENDER_DIMENSIONS_INVALID');
 const pixelHash=sha(Buffer.from(png.data));
 if(new Set(png.data).size<3)throw new Error('RENDER_BLANK_OR_MONOCHROME');
 return {path,sha256:sha(readFileSync(path)),pixelSha256:pixelHash,width:png.width,height:png.height,frame,
         sourceKind:'SYNTHETIC',g4ManifestSha256:media.authorizingG4ManifestSha256};
}
function isolated(scene:Timeline['scenes'][number], variant:string):Timeline{
 const copy=structuredClone(compiled[variant]) as Timeline;
 copy.scenes=[{...scene,start_frame:0}];copy.total_frames=scene.duration_frames;
 assertTimeline(copy);
 return copy;
}
for(const {variant,scene} of sourceCases){
 const timeline=isolated(scene,variant);
 const caseDir=resolve(root,'.artifacts','media',variant,scene.template_id);
 const early=8, middle=Math.floor(scene.duration_frames/2),late=scene.duration_frames-3;
 const samples=mode==='render'?[middle]:[early,middle,late];
 const shots=[];
 for(const frame of samples)shots.push(await oneStill(timeline,frame,`${scene.template_id}-${variant}-f${frame}`,caseDir));
 if(mode==='frames'){
  const same=await oneStill(timeline,middle,`${scene.template_id}-${variant}-repeat-f${middle}`,caseDir);
  if(same.pixelSha256!==shots[1].pixelSha256)throw new Error('RENDER_COLD_PIXEL_NONDETERMINISTIC: '+scene.template_id+'-'+variant);
  if(shots[0].pixelSha256===shots[2].pixelSha256&&scene.events.some(e=>e.preset_id!=='freeze-hold'))throw new Error('RENDER_MOTION_INERT: '+scene.template_id+'-'+variant);
 }
 metrics.push({template:scene.template_id,variant,shots});
}
if(mode==='render'){
 const chosen=isolated(compiled.A.scenes.find(s=>s.template_id==='T03')!, 'A');
 const mediaDir=resolve(root,'.artifacts','media','short-mp4');
 const media=loadApprovedMedia(chosen,makeSyntheticManifest(chosen,mediaDir,fontFile));
 const composition=await selectComposition({serveUrl:bundlePath,id:'HistoricalTimelineV1',inputProps:{timeline:chosen,media}});
 const mp4=resolve(output,'b2-synthetic-short.mp4');
 await renderMedia({serveUrl:bundlePath,composition,inputProps:{timeline:chosen,media},codec:'h264',outputLocation:mp4,pixelFormat:'yuv420p',crf:20,overwrite:true});
 const probe=spawnSync('ffprobe',['-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,r_frame_rate,nb_frames','-of','json',mp4],{encoding:'utf8'});
 if(probe.status!==0)throw Error('FFPROBE_FAILED '+probe.stderr);
 const stream=JSON.parse(probe.stdout).streams[0];
 if(stream.codec_name!=='h264'||stream.width!==1920||stream.height!==1080||stream.r_frame_rate!=='30/1'||Number(stream.nb_frames)!==chosen.total_frames)throw Error('MP4_STREAM_NOT_FROZEN '+JSON.stringify(stream));
 metrics.push({mp4,sha256:sha(readFileSync(mp4)),ffprobe:stream,sourceKind:'SYNTHETIC'});
}
function shouldFail(name:string,fn:()=>void){
 try{fn()}catch(e){if(!(e instanceof RenderBlocked))throw e;return {negative:name,code:e.code};}
 throw new Error('NEGATIVE_ACCEPTED '+name);
}
const negatives=[];
negatives.push(shouldFail('unregistered-template',()=>assertTimeline({...source,scenes:source.scenes.map((s,i)=>i===0?{...s,template_id:'T99'}:s)})));
negatives.push(shouldFail('stale-frame',()=>activeScene(source,source.total_frames)));
negatives.push(shouldFail('untrusted-media',()=>{let t=isolated(compiled.A.scenes[0],'A');loadApprovedMedia(t,{...makeSyntheticManifest(t,resolve(root,'.artifacts','negative'),fontFile),assets:[]});}));
const evidence={command:mode,runner:{node:process.version,platform:process.platform},source:'SYNTHETIC B1 compiled fixtures, not live G1-G4 approvals',samples:metrics,negatives};
writeFileSync(resolve(output,'b2-'+mode+'-evidence.json'),JSON.stringify(evidence,null,2));
console.log(JSON.stringify({status:'LOCAL_PASS',mode,cases:sourceCases.length,negative:negatives.length,renderer:'Remotion Chromium',evidenceDir:output}));
