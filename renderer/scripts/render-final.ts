/** B3 production entry: same HistoricalTimelineV1 frames, then exact approved WAV -> AAC mux. */
import {bundle} from '@remotion/bundler';
import {renderMedia,selectComposition} from '@remotion/renderer';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {prepareApprovedLocalHistory} from './approved-host';

const repo=resolve(import.meta.dirname,'..','..');
const [db,mediaRoot,project,audioPath,output]=process.argv.slice(2);
if(!db||!mediaRoot||!project||!audioPath||!output)throw Error('RENDER_ARGUMENTS_INVALID');
const inputProps=prepareApprovedLocalHistory(db,mediaRoot,project,true);
if(inputProps.timeline.audio_sha256!==createHash('sha256').update(readFileSync(audioPath)).digest('hex'))
 throw Error('RENDER_AUDIO_SHA_MISMATCH');
const dir=mkdtempSync(join(tmpdir(),'hvs-remotion-'));
try{
 const silent=join(dir,'visual.mp4');
 const serveUrl=await bundle({entryPoint:resolve(repo,'renderer','remotion','entry.tsx')});
 const composition=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps});
 await renderMedia({serveUrl,composition,inputProps,outputLocation:silent,codec:'h264',
  pixelFormat:'yuv420p',crf:18,overwrite:true,onProgress:({progress})=>
   console.log(JSON.stringify({kind:'progress',framesProcessed:Math.floor(progress*composition.durationInFrames),
    totalFrames:composition.durationInFrames}))});
 // No -shortest, padding, trim, resample or tempo filter: preserve both authored
 // visual duration and the exact approved WAV timing while encoding it as AAC.
 const mux=spawnSync('ffmpeg',['-v','error','-y','-i',silent,'-i',audioPath,
  '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k',
  '-movflags','+faststart',output],{encoding:'utf8',windowsHide:true});
 if(mux.status!==0)throw Error('RENDER_MUX_FAILED: '+mux.stderr.slice(0,1000));
 console.log(JSON.stringify({kind:'complete',framesProcessed:composition.durationInFrames,
  totalFrames:composition.durationInFrames,output:resolve(output)}));
}finally{rmSync(dir,{recursive:true,force:true});}
