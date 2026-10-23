/** B2-01 trust ingress shared by Node still render and future local Player host.
 * Caller passes a project locator, never an in-memory approved=true object.
 * Python verifies the CURRENT SQLite G1/G2/G3/G4 authority before export.
 */
import {spawnSync} from 'node:child_process';
import {readFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import {assertTimeline,fail,type Timeline} from '../remotion/schema';
import {loadApprovedMedia,type ResolveManifest} from './media';
import type {HistoryProps} from '../remotion/HistoryComposition';
const repo=resolve(import.meta.dirname,'..','..');
export function prepareApprovedLocalHistory(sqlite:string,artifactRoot:string,project:string):HistoryProps{
 if(!sqlite||!artifactRoot||!project)fail('RENDER_G4_NOT_AUTHORIZED',project||'project','Current local project required');
 const dir=mkdtempSync(join(tmpdir(),'hvs-trusted-preparation-'));
 try {
  const file=join(dir,'approved.json');
  const python=resolve(repo,'.venv','Scripts','python.exe');
  const result=spawnSync(python,['-m','renderer.scripts.export_approved_media',
   '--sqlite',sqlite,'--media-root',artifactRoot,'--project',project,'--output',file],
   {cwd:repo,encoding:'utf8',windowsHide:true});
  if(result.status!==0)fail('RENDER_G4_NOT_AUTHORIZED',project,
    'Current approved SQLite draft/export refused: '+(result.stderr||'export failed').slice(0,1000));
  const payload=JSON.parse(readFileSync(file,'utf8')) as {timeline:Timeline;manifest:ResolveManifest};
  assertTimeline(payload.timeline);
  if(payload.timeline.project_id!==project||payload.manifest.projectId!==project||
      payload.manifest.sourceKind!=='APPROVED_LOCAL')
   fail('RENDER_G4_NOT_AUTHORIZED',project,'Only current host-exported APPROVED_LOCAL sources are accepted');
  const media=loadApprovedMedia(payload.timeline,payload.manifest);
  if(media.sourceKind!=='APPROVED_LOCAL')fail('RENDER_SYNTHETIC_PROHIBITED',project,'Synthetic fixture cannot issue a host-authorized Player');
  return {timeline:payload.timeline,media};
 } finally {rmSync(dir,{recursive:true,force:true});}
}
