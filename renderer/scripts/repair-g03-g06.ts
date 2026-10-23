/** B2 G03/G06 RED→GREEN discriminators. Controlled host fixture is synthetic-only. */
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {HistoricalPlayer,prepareApprovedPlayerOnLocalHost,type PreparedHistoryPlayer} from '../remotion/PlayerMount';
import {timelineRail} from '../remotion/templates/T05';
import {RenderBlocked,type Scene,type Timeline} from '../remotion/schema';

const root=resolve(import.meta.dirname,'..');
const dir=resolve(root,'.artifacts/renders');mkdirSync(dir,{recursive:true});
const results:{gate:string;case:string;status:'PASS'|'FAIL';detail?:string}[]=[];
function must(value:unknown,message:string):asserts value {if(!value)throw Error(message);}
function test(gate:string,name:string,fn:()=>void){
 try{fn();results.push({gate,case:name,status:'PASS'});console.log('PASS '+gate+' '+name);}
 catch(e){const detail=e instanceof Error?e.message:String(e);
  results.push({gate,case:name,status:'FAIL',detail});console.error('FAIL '+gate+' '+name+': '+detail);}
}
function rejectedToken(token:unknown){
 try{
  renderToStaticMarkup(React.createElement(HistoricalPlayer,{prepared:token as PreparedHistoryPlayer}));
 }catch(e){
  if(e instanceof RenderBlocked&&e.code==='PLAYER_UNTRUSTED_PROPS')return;
  throw e;
 }
 throw Error('Forged capability reached Player child instead of PLAYER_UNTRUSTED_PROPS');
}
function mutationBlocked<T>(name:string,get:()=>T,set:(value:T)=>void,replacement:T){
 const original=get();
 try{set(replacement);}catch(e){if(!(e instanceof TypeError))throw e;}
 if(!Object.is(get(),original)){
  try{set(original);}catch{/* restore best effort in RED baseline */}
  throw Error(name+' changed after trusted issuance');
 }
}
const config=JSON.parse(readFileSync(resolve(root,'.artifacts/approved-player-test.json'),'utf8')) as
 {db:string;artifactRoot:string;project:string;source:string};
must(config.source==='SYNTHETIC_SQLITE_APPROVAL_FIXTURE_NOT_REAL_RIGHTS','Host fixture must be synthetic only');
const prepared=await prepareApprovedPlayerOnLocalHost(config.db,config.artifactRoot,config.project);
const props=prepared.props;
must(props.media.sourceKind==='APPROVED_LOCAL','Host fixture must pass controlled local gate');
const layer=props.timeline.scenes.flatMap(s=>s.layers).find(l=>l.text!==null);
must(layer,'Controlled host must contain a text layer');
const event=props.timeline.scenes.flatMap(s=>s.events)[0];
must(event,'Controlled host must contain a motion event');
const key=props.timeline.scenes[0]?.camera.keyframes[0];
must(key,'Controlled host must contain a camera keyframe');
const asset=Object.values(props.media.assets)[0];
must(asset,'Controlled host must contain embedded image media');
test('G03','detached recursively frozen timeline/media',()=>{
 must(Object.isFrozen(props.timeline.scenes)&&Object.isFrozen(props.timeline.scenes[0].layers)&&
 Object.isFrozen(layer)&&Object.isFrozen(event)&&Object.isFrozen(key)&&
 Object.isFrozen(props.media.assets)&&Object.isFrozen(asset),'Nested verified data is not frozen');
});
test('G03','nested text layer mutation',()=>mutationBlocked('text',()=>layer.text,v=>{layer.text=v;},'FORGED HISTORICAL TEXT'));
test('G03','nested event mutation',()=>mutationBlocked('event',()=>event.start_frame,v=>{event.start_frame=v;},event.start_frame+1));
test('G03','nested camera keyframe mutation',()=>mutationBlocked('keyframe',()=>key.scale,v=>{key.scale=v;},key.scale+0.2));
test('G03','nested layer array replacement',()=>{
 const layers=props.timeline.scenes[0].layers,original=layers[0];
 mutationBlocked('layer array',()=>layers[0],v=>{layers[0]=v;},{...original,text:'FORGED ARRAY LAYER'});
});
const forgedImage='data:image/png;base64,'+Buffer.from('tampered-but-valid-base64').toString('base64');
test('G03','image URI tampering with unchanged declared SHA',()=>{
 const originalSha=asset.originalSha256;
 mutationBlocked('image data URI',()=>asset.dataUri,v=>{asset.dataUri=v;},forgedImage);
 must(asset.originalSha256===originalSha,'Declared source SHA changed');
});
test('G03','font data URI tampering',()=>mutationBlocked('font URI',()=>props.media.fontDataUri,v=>{props.media.fontDataUri=v;},'data:font/ttf;base64,QUJD'));
test('G03','font metadata tampering',()=>mutationBlocked('font SHA',()=>props.media.fontSha256,v=>{props.media.fontSha256=v;},'a'.repeat(64)));
test('G03','forged image and G4 capability rejected before Player child',()=>{
 const media={...props.media,assets:{...props.media.assets,[asset.assetId]:{...asset,dataUri:forgedImage}}};
 rejectedToken({props:{timeline:props.timeline,media}});
 rejectedToken({props:{timeline:props.timeline,media:{...media,authorizingG4ManifestSha256:props.media.authorizingG4ManifestSha256}}});
});
test('G03','forged font capability rejected',()=>{
 rejectedToken({props:{timeline:props.timeline,media:{...props.media,fontDataUri:'data:font/ttf;base64,QUJD'}}});
});
test('G03','spread clone serialization and Proxy rejected',()=>{
 rejectedToken({...prepared});
 rejectedToken(structuredClone(prepared));
 rejectedToken(JSON.parse(JSON.stringify(prepared)));
 rejectedToken(new Proxy(prepared,{}));
 rejectedToken({props});
});
test('G03','valid host capability reaches shared Player composition',()=>{
 const child=HistoricalPlayer({prepared});
 must(React.isValidElement(child),'Approved host-issued Player child missing');
 must((child.props as {inputProps:unknown}).inputProps===props,'Player must use canonical issued snapshot');
});
let badHost=false;
try{await prepareApprovedPlayerOnLocalHost(config.db+'-missing',config.artifactRoot,config.project);}
catch(e){badHost=e instanceof RenderBlocked&&e.code==='RENDER_G4_NOT_AUTHORIZED';}
test('G03','missing SQLite G4 host fails closed',()=>must(badHost,'Missing G4 source was accepted'));

const compiled=JSON.parse(readFileSync(resolve(root,'.artifacts/compiled-30.json'),'utf8')) as Record<string,Timeline>;
const original=compiled.A.scenes.find(s=>s.template_id==='T05');
must(original,'Missing compiler T05 source');
function syntheticChronology(labels:(string|null)[]):Scene{
 const scene=structuredClone(original!);
 const base=scene.layers.find(l=>l.layer_kind==='date');
 must(base&&base.source_claim_id,'Controlled T05 date layer must be claim-backed');
 const n=labels.length;
 const dates=labels.map((text,i)=>({...structuredClone(base),layer_id:'synthetic_chronology_'+i,text,
  rect_px:{x:Math.round(100+i*(1700/n)),y:365,w:140,h:150}}));
 scene.layers=[...scene.layers.filter(l=>l.layer_kind!=='date'),...dates];
 scene.staging.beat_sequence=dates.map((d,i)=>({local_start_frame:i*20,
  local_end_frame:i===n-1?scene.duration_frames:(i+1)*20,
  focus_layer_id:d.layer_id,activated_layer_ids:dates.slice(0,i+1).map(x=>x.layer_id),hidden_layer_ids:[]}));
 return scene;
}
function chronologyPass(name:string,labels:(string|null)[]){
 test('G06',name,()=>must(timelineRail(syntheticChronology(labels)).edges.length===labels.length-1,'Wrong rail edge count'));
}
function chronologyReject(name:string,labels:(string|null)[]){
 test('G06',name,()=>{
  try{timelineRail(syntheticChronology(labels));}
  catch(e){if(e instanceof RenderBlocked&&e.code==='T05_CHRONOLOGY_INVALID')return;throw e;}
  throw Error('Invalid chronology was accepted');
 });
}
chronologyPass('valid BCE 300→100',['300 BCE','100 BCE']);
chronologyReject('reversed BCE 100→300',['100 BCE','300 BCE']);
chronologyPass('BCE to CE without historical year zero',['100 BCE','1 BCE','1 CE','44 CE']);
chronologyPass('valid CE 476→1492→1914',['476 CE','1492 CE','1914 CE']);
chronologyReject('reversed CE 1492→476',['1492 CE','476 CE']);
chronologyReject('mixed valid and unparseable',['300 BCE','UNVERIFIED date_late']);
chronologyReject('missing date label',['300 BCE',null]);
chronologyReject('ambiguous two-digit year',['44','100 CE']);
chronologyReject('equal chronology',['300 BCE','300 BCE']);
chronologyReject('year zero forbidden',['0 CE','1 CE']);
chronologyReject('malformed era token',['300 B.C.','100 CE']);
chronologyPass('BC AD aliases and prefix AD',['300 BC','100 BC','AD 44','476 CE']);
chronologyPass('documented circa prefix',['c. 300 BCE','100 BCE']);
chronologyPass('bare 3/4 digit CE compatibility',['476','1492']);
chronologyReject('unparseable mixed era',['300 BCE','100 UNKNOWN']);
const failures=results.filter(r=>r.status==='FAIL');
writeFileSync(resolve(dir,'b2-g03-g06-regressions.json'),JSON.stringify({status:failures.length?'FAIL':'PASS',
 source:'SYNTHETIC_SQLITE_APPROVAL_FIXTURE_NOT_REAL_RIGHTS',cases:results},null,2));
if(failures.length)throw Error('B2_G03_G06_REGRESSIONS_FAILED: '+failures.map(x=>x.gate+'/'+x.case).join('; '));
console.log(JSON.stringify({status:'PASS',g03:results.filter(x=>x.gate==='G03').length,g06:results.filter(x=>x.gate==='G06').length}));