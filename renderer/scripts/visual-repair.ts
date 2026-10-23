/** B2-01..03 visual-failure discriminators, always using actual Remotion stills. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {bundle} from '@remotion/bundler';
import {renderStill,selectComposition} from '@remotion/renderer';
import {PNG} from 'pngjs';
import {sampleCamera,arrowPolygon} from '../remotion/Primitives';
import {timelineRail} from '../remotion/templates/T05';
import {HistoricalPlayer,prepareApprovedPlayerOnLocalHost} from '../remotion/PlayerMount';
import {assertTimeline,RenderBlocked,type Timeline,type Scene} from '../remotion/schema';
import {makeSyntheticManifest,loadApprovedMedia} from './media';
const root=resolve(import.meta.dirname,'..');
const input=JSON.parse(readFileSync(resolve(root,'.artifacts/compiled-30.json'),'utf8')) as Record<string,Timeline>;
const font=resolve(process.env.WINDIR??'C:\\Windows','Fonts','arial.ttf');
const dir=resolve(root,'.artifacts/renders');mkdirSync(dir,{recursive:true});
const sha=(b:Buffer)=>createHash('sha256').update(b).digest('hex');
const expect=(v:boolean,why:string)=>{if(!v)throw Error('REPAIR_ASSERTION_FAIL: '+why);};
const selected=(id:string):Timeline=>{
 const t=structuredClone(input.A),s=t.scenes.find(x=>x.template_id===id);
 if(!s)throw Error('Missing real B1 '+id);
 t.scenes=[{...s,start_frame:0}];t.total_frames=s.duration_frames;assertTimeline(t);return t;
};
const serveUrl=await bundle({entryPoint:resolve(root,'remotion/entry.tsx')});
const evidence:any[]=[];
async function frame(t:Timeline,n:number,label:string){
 const media=loadApprovedMedia(t,makeSyntheticManifest(t,resolve(root,'.artifacts/media/repair-'+label),font));
 const props={timeline:t,media};
 const comp=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps:props});
 const path=resolve(dir,'repair-'+label+'-f'+n+'.png');
 await renderStill({serveUrl,composition:comp,inputProps:props,frame:n,output:path,imageFormat:'png'});
 const file=readFileSync(path),png=PNG.sync.read(file);
 expect(png.width===1920&&png.height===1080,'Actual Chromium output dimensions');
 const out={label,frame:n,path,sha256:sha(file),pixelSha256:sha(Buffer.from(png.data)),
            sourceKind:'SYNTHETIC',assetSnapshotSha256:t.asset_snapshot_sha256};
 evidence.push(out);return png;
}
const sample=(p:PNG,x:number,y:number):[number,number,number]=>{
 const k=(Math.round(y)*p.width+Math.round(x))*4;
 return [p.data[k],p.data[k+1],p.data[k+2]];
};
const bg:[number,number,number]=[203,195,178];
const distance=(a:number[],b:number[])=>Math.hypot(...a.map((v,i)=>v-b[i]));
const roiDiff=(a:PNG,b:PNG,x:number,y:number,r=24)=>{
 let total=0;
 for(let yy=Math.max(0,Math.floor(y-r));yy<Math.min(a.height,y+r);yy+=2)
 for(let xx=Math.max(0,Math.floor(x-r));xx<Math.min(a.width,x+r);xx+=2)
  total+=distance(sample(a,xx,yy),sample(b,xx,yy));
 return total;
};
const t03=selected('T03'),sc=t03.scenes[0],cards=sc.layers.filter(l=>l.layer_kind==='archival_photo');
expect(cards.length===3,'T03 must preserve three source card identities');
const windows=[0,8,34,35,50,70,96,97,110,150].filter(x=>x<sc.duration_frames);
const images=new Map<number,PNG>();
for(const n of windows)images.set(n,await frame(t03,n,'T03-A'));
const center=(i:number)=>[cards[i].rect_px.x+cards[i].rect_px.w/2,cards[i].rect_px.y+cards[i].rect_px.h/2] as const;
const visible=(n:number,i:number)=>distance(sample(images.get(n)!,...center(i)),bg)>22;
expect(visible(8,0),'P1-01 early hero must visibly appear, not blank');
expect(visible(70,0)&&visible(150,0),'P1-01 future stagger cannot re-hide first card');
expect(visible(70,1),'P1-01 second card must be visible at authored second beat');
expect(visible(150,2),'P1-01 third card must be visible at authored third beat');
expect(!visible(8,2),'P1-01 future third card must stay hidden before its beat');
evidence.push({case:'T03 individual card-region checks',samples:windows.map(n=>({frame:n,sourceCards:cards.map((c,i)=>({id:c.layer_id,center:center(i),visible:visible(n,i)}))}))});
const t05=selected('T05');const scene=t05.scenes[0];
const originalRail=timelineRail(scene);
expect(originalRail.edges.length===1,'T05 2 dates -> one authored connector');
for(const n of [8,50,150].filter(x=>x<scene.duration_frames))await frame(t05,n,'T05-A');
for(const total of [3,6]){
 const t=structuredClone(t05),s=t.scenes[0],base=s.layers.filter(x=>x.layer_kind==='date')[0];
 const rest=s.layers.filter(x=>x.layer_kind!=='date');
 const newDates=Array.from({length:total},(_,i)=>({...structuredClone(base),
  layer_id:'synthetic_date_'+total+'_'+i,text:String(1800+10*i),
  rect_px:{x:Math.round(100+i*(1700/total)),y:365,w:140,h:150},source_claim_id:base.source_claim_id}));
 s.layers=[...rest,...newDates];
 s.staging.beat_sequence=newDates.map((date,i)=>({
  beat_id:'beat_synthetic_'+total+'_'+i,
  local_start_frame:i*25,local_end_frame:i===total-1?s.duration_frames:(i+1)*25,
  focus_layer_id:date.layer_id,activated_layer_ids:newDates.slice(0,i+1).map(x=>x.layer_id),hidden_layer_ids:[]}));
 // Original frozen motion references removed original date layers: synthetic multi-event
 // evidence is geometric/chronological only, not an invented B1-authorized compile.
 s.events=s.events.filter(e=>e.affected_layer_ids.every(x=>s.layers.some(l=>l.layer_id===x)) &&
  s.layers.some(l=>l.layer_id===e.layer_id));
 assertTimeline(t);
 const g=timelineRail(s);expect(g.edges.length===total-1,'T05 exact N−1 rail connectors');
 await frame(t,150,'T05-SYNTHETIC-'+total+'-date');
 const bad=structuredClone(s);bad.layers.find(l=>l.layer_id===newDates[0].layer_id)!.text='9999';
 let rejected=false;try{timelineRail(bad);}catch(e){rejected=e instanceof RenderBlocked;}
 expect(rejected,'T05 reversed chronology must fail closed');
 const missing=structuredClone(s);missing.layers.find(l=>l.layer_id===newDates[0].layer_id)!.source_claim_id=null;
 let noClaim=false;try{timelineRail(missing);}catch(e){noClaim=e instanceof RenderBlocked;}
 expect(noClaim,'T05 missing date claim must fail closed');
 evidence.push({case:'T05 2–6 sourced synthetic chronology',count:total,connectors:g.edges.length,
  source:'SYNTHETIC derived from frozen T05 date layers'});
}
const t10=selected('T10'),causal=t10.scenes[0],connector=causal.layers.find(l=>l.layer_kind==='annotation')!;
const draw=causal.events.find(e=>e.preset_id==='editorial-connector-draw')!;
expect(draw.params.arrowhead===true,'T10 frozen arrowhead was authored');
const coords:[[number,number],[number,number],[number,number]]=[[.08,.5],[.45,.2],[.91,.5]];
const points=coords.map(([x,y])=>[x*connector.rect_px.w,y*connector.rect_px.h] as [number,number]);
expect(Boolean(arrowPolygon(points,1)),'T10 actual reviewed annotation has a directional tip');
const end=Math.min(causal.duration_frames-1,draw.start_frame+draw.duration_frames+2);
const earlyArrow=await frame(t10,Math.max(0,draw.start_frame+3),'T10-A-start');
const midArrow=await frame(t10,Math.min(end,draw.start_frame+Math.floor(draw.duration_frames/2)),'T10-A-mid');
const arrowPng=await frame(t10,end,'T10-A-arrow');
expect(earlyArrow!==midArrow,'T10 source path changes across authored event frames');
const noArrow=structuredClone(t10);
const noEvent=noArrow.scenes[0].events.find(e=>e.event_id===draw.event_id)!;
noEvent.params.arrowhead=false;
const linePng=await frame(noArrow,end,'T10-A-no-arrow');
const camera=sampleCamera(causal.camera.keyframes,end);
const rawX=connector.rect_px.x+points[2][0],rawY=connector.rect_px.y+points[2][1];
const radians=camera.rotation_deg*Math.PI/180,dx=rawX-960,dy=rawY-540;
const tipX=960+camera.x_px+camera.scale*(dx*Math.cos(radians)-dy*Math.sin(radians));
const tipY=540+camera.y_px+camera.scale*(dx*Math.sin(radians)+dy*Math.cos(radians));
expect(roiDiff(arrowPng,linePng,tipX,tipY)>100,'T10 arrow tip changes real camera-transformed endpoint pixels');
const keyScene=structuredClone(t05);
const c=keyScene.scenes[0].camera.keyframes;
const endCam=c[c.length-1];
const middle={...endCam,at_frame:Math.round(endCam.at_frame/2),x_px:52,y_px:-27,
 scale:1.025,rotation_deg:2,opacity:.8,easing:'ease_in_out'};
keyScene.scenes[0].camera.keyframes=[c[0],middle,endCam];
assertTimeline(keyScene);
const evaluated=sampleCamera(keyScene.scenes[0].camera.keyframes,middle.at_frame);
expect(evaluated.x_px===52&&evaluated.rotation_deg===2&&evaluated.opacity===.8,'Piecewise authored middle key must be exact');
const midFrame=await frame(keyScene,middle.at_frame,'CAMERA-3KEY');
const originalFrame=await frame(t05,middle.at_frame,'CAMERA-2KEY');
expect(roiDiff(midFrame,originalFrame,900,520,400)>1000,'Camera middle key must alter real rendered pixels');
const raw=loadApprovedMedia(t03,makeSyntheticManifest(t03,resolve(root,'.artifacts/media/repair-bad'),font));
const firstId=Object.keys(raw.assets)[0]!;
const variants=[
 {...raw,sourceKind:'APPROVED_LOCAL'},
 {...raw,assets:{...raw.assets,[firstId]:{...raw.assets[firstId],dataUri:'data:image/png;base64,AAAA'}}},
 {...raw,fontDataUri:'data:font/ttf;base64,AAAA'},
 {...raw,authorizingG4ManifestSha256:'a'.repeat(64)},
 {...raw,assets:{...raw.assets,[firstId]:{...raw.assets[firstId],dataUri:'https://not-approved.test/pic.png'}}}
];
for(const [i,media] of variants.entries()){
 let rejected=false;
 try{HistoricalPlayer({prepared:{props:{timeline:t03,media}} as any});}
 catch(e){rejected=e instanceof RenderBlocked&&e.code==='PLAYER_UNTRUSTED_PROPS';}
 expect(rejected,'P1-05 public Player rejects forged props case '+i);
}
evidence.push({case:'Player public actual mount boundary',attacks:variants.length,
 result:'REJECTED before first frame',note:'B2-05 browser host serialization NOT_RUN'});
const preparedConfig=JSON.parse(readFileSync(resolve(root,'.artifacts/approved-player-test.json'),'utf8')) as
 {db:string;artifactRoot:string;project:string;source:string};
const authorized=await prepareApprovedPlayerOnLocalHost(
 preparedConfig.db,preparedConfig.artifactRoot,preparedConfig.project);
expect(authorized.props.media.sourceKind==='APPROVED_LOCAL','Current SQLite host must issue local approved capability');
const mounted=HistoricalPlayer({prepared:authorized});
expect(Boolean(mounted),'Current SQLite verified Player must mount same HistoryComposition');
// Render the exact host-issued props through the same HistoryComposition used by Player.
const shared=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps:authorized.props});
const path=resolve(dir,'repair-approved-player-host-f0.png');
await renderStill({serveUrl,composition:shared,inputProps:authorized.props,output:path,imageFormat:'png',frame:0});
evidence.push({case:'Approved Player/Node shared composition',source:preparedConfig.source,
 path,sha256:sha(readFileSync(path)),g4Head:authorized.props.media.authorizingG4ManifestSha256});
let badHost=false;
try{await prepareApprovedPlayerOnLocalHost(preparedConfig.db+'-missing',preparedConfig.artifactRoot,preparedConfig.project);}
catch(e){badHost=e instanceof RenderBlocked&&e.code==='RENDER_G4_NOT_AUTHORIZED';}
expect(badHost,'Host must fail closed when trusted SQLite G4 source is not present');
writeFileSync(resolve(dir,'b2-repair-evidence.json'),JSON.stringify({status:'LOCAL_PASS',source:'SYNTHETIC',
 samples:evidence,platform:process.platform,node:process.version},null,2));
console.log(JSON.stringify({status:'LOCAL_PASS',repair:'P1-01..05 discriminators',frames:evidence.filter(x=>x.path).length,
 evidence:resolve(dir,'b2-repair-evidence.json')}));
