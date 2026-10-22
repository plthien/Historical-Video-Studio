/** B2-01 authorized local still; no B2-06 orchestration/export. */
import {resolve} from 'node:path';
import {bundle} from '@remotion/bundler';
import {renderStill,selectComposition} from '@remotion/renderer';
import {prepareApprovedLocalHistory} from './approved-host';
const repo=resolve(import.meta.dirname,'..','..');
const [db,mediaRoot,project,output]=process.argv.slice(2);
if(!db||!mediaRoot||!project||!output)throw Error('Use: render:approved-still <sqlite> <media-root> <project-id> <PNG output>');
const inputProps=prepareApprovedLocalHistory(db,mediaRoot,project);
const serveUrl=await bundle({entryPoint:resolve(repo,'renderer','remotion','entry.tsx')});
const comp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps});
await renderStill({serveUrl,composition:comp,inputProps,frame:0,output:resolve(output),imageFormat:'png'});
console.log(JSON.stringify({result:'LOCAL_APPROVED_STILL',project,frame:0,g4Head:inputProps.media.authorizingG4ManifestSha256,path:resolve(output)}));
