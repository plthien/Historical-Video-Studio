/** B2-01 authorized local still only. Not B2-06 render orchestration/export. */
import {spawnSync} from 'node:child_process';
import {readFileSync,mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import {bundle} from '@remotion/bundler';
import {renderStill,selectComposition} from '@remotion/renderer';
import {assertTimeline} from '../remotion/schema';
import {loadApprovedMedia,type ResolveManifest} from './media';
const repo=resolve(import.meta.dirname,'..','..');
const [db,mediaRoot,project,output]=process.argv.slice(2);
if(!db||!mediaRoot||!project||!output)throw Error('Use: render:approved-still <sqlite> <media-root> <project-id> <PNG output>');
const dir=mkdtempSync(join(tmpdir(),'hvs-approved-render-'));
const manifestPath=resolve(dir,'source.json');
const python=resolve(repo,'.venv','Scripts','python.exe');
const child=spawnSync(python,['-m','renderer.scripts.export_approved_media',
 '--sqlite',db,'--media-root',mediaRoot,'--project',project,'--output',manifestPath],
 {cwd:repo,encoding:'utf8',windowsHide:true});
if(child.status!==0)throw Error('RENDER_G4_NOT_AUTHORIZED: '+child.stderr);
const doc=JSON.parse(readFileSync(manifestPath,'utf8'));
const timeline=doc.timeline,manifest=doc.manifest as ResolveManifest;
assertTimeline(timeline);
if(manifest.sourceKind!=='APPROVED_LOCAL')throw Error('RENDER_SYNTHETIC_PROHIBITED: approved render entry only');
const media=loadApprovedMedia(timeline,manifest);
const inputProps={timeline,media};
const serveUrl=await bundle({entryPoint:resolve(repo,'renderer','remotion','entry.tsx'),logLevel:'error'});
const comp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps});
await renderStill({serveUrl,composition:comp,inputProps,frame:0,output:resolve(output),imageFormat:'png'});
console.log(JSON.stringify({result:'LOCAL_APPROVED_STILL',project,frame:0,g4Head:manifest.g4ManifestSha256,path:resolve(output)}));
