import {test,expect} from '@playwright/test';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import path from 'node:path';
// Playwright executes ESM directly: importing a package directory is rejected
// by Node on Windows.  Keep the test on the renderer's pinned packages rather
// than introducing a duplicate browser-render stack in frontend.
import {bundle} from '../../../renderer/node_modules/@remotion/bundler/dist/index.js';
import {renderStill,selectComposition} from '../../../renderer/node_modules/@remotion/renderer/dist/index.js';
import {PNG} from 'pngjs';
import type {HistoryProps} from '../../../renderer/remotion/HistoryComposition';

const root=path.resolve(import.meta.dirname,'../../..');
const output=path.join(root,'frontend','.artifacts','parity');
const hash=(input:string|Buffer)=>createHash('sha256').update(input).digest('hex');

test('storyboard-editor real browser Player vs Node renderStill same immutable frame',async({page,request})=>{
 test.skip(process.env.HVS_B2_FIXTURE!=='1','Requires Windows SQLite controlled G4 approval fixture and both Chromium runtimes');
 test.setTimeout(180_000);
 const response=await request.get('http://127.0.0.1:8000/api/v1/projects/proj_001/storyboard/preview');
 expect(response.ok()).toBeTruthy();
 const approved=await response.json() as {status:string;draft_manifest_sha256:string;props:HistoryProps};
 expect(approved.status).toBe('G4_DRAFT_VIEW_ONLY');
 const props=approved.props;
 expect(props.media.sourceKind).toBe('APPROVED_LOCAL');
 const identity={timeline:hash(JSON.stringify(props.timeline)),font:props.media.fontSha256,
   sources:Object.values(props.media.assets).map(x=>[x.assetId,x.originalSha256]),
   composition:'HistoricalTimelineV1',fps:30,manifest:approved.draft_manifest_sha256};
 const fatalErrors:string[]=[];
 page.on('pageerror',e=>fatalErrors.push(e.message));
 page.on('console',m=>{if(m.type()==='error'&&/Invalid hook call|useContext|HistoryComposition|React/i.test(m.text()))fatalErrors.push(m.text());});
 const serveUrl=await bundle({entryPoint:path.join(root,'renderer','remotion','entry.tsx')});
 const composition=await selectComposition({serveUrl,id:'HistoricalTimelineV1',inputProps:props});
 mkdirSync(output,{recursive:true});
 await page.setViewportSize({width:2400,height:1450});
 await page.goto('/');
 await page.getByLabel('Project ID').fill('proj_001');
 await page.getByRole('button',{name:'Open existing project'}).click();
 await page.getByRole('button',{name:/Motion Storyboard/}).click();
 await expect(page.getByText(/Scenes \(2\)/)).toBeVisible();
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 await expect(page.getByTestId('player-stage')).toBeVisible({timeout:30000});
 const stage=page.getByTestId('player-stage');
 await stage.evaluate(el=>{el.style.width='1920px';el.style.height='1080px';});
 const transitionFrames=props.timeline.scenes.flatMap(scene=>scene.events.flatMap(event=>[
   Math.max(0,scene.start_frame+event.start_frame-1),scene.start_frame+event.start_frame,
   scene.start_frame+event.start_frame+Math.floor(event.duration_frames/2),
   Math.min(props.timeline.total_frames-1,scene.start_frame+event.start_frame+event.duration_frames),
   Math.min(props.timeline.total_frames-1,scene.start_frame+event.start_frame+event.duration_frames+1),
 ]));
 const boundaries=props.timeline.scenes.flatMap(scene=>[scene.start_frame,
   Math.min(props.timeline.total_frames-1,scene.start_frame+scene.duration_frames-1)]);
 const samples=[...new Set([...transitionFrames,...boundaries])].sort((a,b)=>a-b).slice(0,14);
 expect(samples.length).toBeGreaterThan(2);
 const evidence=[];
 for(const frame of samples){
  await page.getByLabel('Seek exact frame').fill(String(frame));
  // Seek input state is not visual evidence.  Wait for the shared Composition
  // to report the requested frame before capturing a Player pixel.
  const owningScene=props.timeline.scenes.find(s=>frame>=s.start_frame&&frame<s.start_frame+s.duration_frames);
  expect(owningScene,'every sampled global frame must have one owning scene').toBeDefined();
  await expect(stage.locator(`[data-global-frame="${frame}"][data-scene-id="${owningScene!.scene_id}"]`)).toBeVisible({timeout:10000});
  expect(fatalErrors,'shared Browser Player must not throw runtime errors').toEqual([]);
  // Stage wrappers can round to 1081 CSS pixels. Capture the actual shared
  // Composition element with auto-scroll, not its responsive stage wrapper or
  // page viewport clip (which can truncate the image below the visible fold).
  const renderedSurface=stage.locator(`[data-global-frame="${frame}"][data-scene-id="${owningScene!.scene_id}"]`);
  const bounds=await renderedSurface.boundingBox();
  expect(bounds,'Composition surface must be mounted').not.toBeNull();
  expect(Math.abs(bounds!.width-1920)).toBeLessThan(1.01);
  expect(Math.abs(bounds!.height-1080)).toBeLessThan(1.01);
  const screenshot=PNG.sync.read(await renderedSurface.screenshot({scale:'css'}));
  // The Chromium screenshot may ceil a fractional CSS surface by one pixel.
  // Trim that raster overhang only; never rescale Composition pixels or raise thresholds.
  expect(screenshot.width).toBeGreaterThanOrEqual(1920);
  expect(screenshot.width).toBeLessThanOrEqual(1921);
  expect(screenshot.height).toBeGreaterThanOrEqual(1080);
  expect(screenshot.height).toBeLessThanOrEqual(1081);
  const browserPNG=new PNG({width:1920,height:1080});
  PNG.bitblt(screenshot,browserPNG,0,0,1920,1080,0,0);
  const file=path.join(output,'node-f'+frame+'.png');
  await renderStill({serveUrl,composition,inputProps:props,frame,output:file,imageFormat:'png'});
  const nodePNG=PNG.sync.read(readFileSync(file));
  expect(browserPNG.width).toBe(1920);expect(browserPNG.height).toBe(1080);
  expect(nodePNG.width).toBe(browserPNG.width);expect(nodePNG.height).toBe(browserPNG.height);
  let total=0,big=0,count=0,variation=new Set<number>();
  for(let y=0;y<1080;y+=2)for(let x=0;x<1920;x+=2){
   const i=4*(y*1920+x);
   const delta=Math.abs(browserPNG.data[i]-nodePNG.data[i])+
     Math.abs(browserPNG.data[i+1]-nodePNG.data[i+1])+
     Math.abs(browserPNG.data[i+2]-nodePNG.data[i+2]);
   total+=delta/3;big+=delta>90?1:0;count++;
   variation.add(browserPNG.data[i]);
  }
  const meanDiff=total/count,pixelMismatch=big/count;
  expect(variation.size).toBeGreaterThan(3);
  expect(meanDiff,'Mean browser vs Node RGB difference').toBeLessThan(20);
  expect(pixelMismatch,'Fraction >30 RGB error per channel').toBeLessThan(0.14);
  const browserFile=path.join(output,'browser-f'+frame+'.png');
  writeFileSync(browserFile,PNG.sync.write(browserPNG));
  evidence.push({frame,width:1920,height:1080,meanDiff,pixelMismatch,nodeFile:file,browserFile,
   sceneId:owningScene!.scene_id,
   nodeSha256:hash(readFileSync(file)),
   browserSha256:hash(readFileSync(browserFile))});
 }
 expect(fatalErrors,'no uncaught browser runtime failures').toEqual([]);
 writeFileSync(path.join(output,'b2-player-node-parity.json'),JSON.stringify({status:'LOCAL_PASS',
  source:'SYNTHETIC_SQLITE_APPROVAL_FIXTURE_NOT_REAL_RIGHTS',identity,evidence,
  bounds:{meanDiffLt:20,pixelMismatchLt:0.14}},null,2));
});
