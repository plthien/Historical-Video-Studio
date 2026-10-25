import {test,expect} from '@playwright/test';
import {PNG} from 'pngjs';
import {existsSync,renameSync,mkdirSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import type {Motion,ResolvedMedia,Scene} from '../../../renderer/remotion/schema';

test('storyboard-editor uses real persisted G4 scenes and native read-only Player',async({page,request})=>{
 test.skip(process.env.HVS_B2_FIXTURE!=='1','Requires native Windows controlled SQLite G4, never mocked HTTP fixtures');
 const fatalErrors:string[]=[];
 page.on('pageerror',e=>fatalErrors.push(e.message));
 page.on('console',m=>{if(m.type()==='error'&&/Invalid hook call|useContext|HistoryComposition|React/i.test(m.text()))fatalErrors.push(m.text());});
 await page.goto('/');
 await page.getByLabel('Project ID').fill('proj_001');
 await page.getByRole('button',{name:'Open existing project'}).click();
 await expect(page.getByText('proj_001',{exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:/Motion Storyboard/}).click();
 await expect(page.getByText(/Scenes \(2\)/)).toBeVisible({timeout:25000});
 await expect(page.getByRole('listbox',{name:'Storyboard scenes'}).getByRole('option')).toHaveCount(2);
 const initialPreviewResponse=page.waitForResponse(response=>response.url().endsWith('/storyboard/preview'));
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 const initialPreview=await (await initialPreviewResponse).json();
 await expect(page.getByLabel('Read-only local Remotion Player')).toBeVisible({timeout:30000});
 await expect(page.getByText(/G4 DRAFT · VIEW ONLY/)).toBeVisible();
 // A visible Player wrapper or updated seek input is NOT a rendered frame.
 const stage=page.getByTestId('player-stage');
 await expect(stage.locator('[data-global-frame="0"][data-scene-id]')).toBeVisible({timeout:30000});
 const first=PNG.sync.read(await stage.screenshot());
 // Native fixture contains real copied G3-authorized synthetic source bytes.
 // Temporarily hide exactly one original to exercise HTTP 424 through actual
 // browser UI and Windows SQLite host, then always restore before other edits.
 const approvedAssets:ResolvedMedia['assets']=initialPreview.props.media.assets;
 const candidate=Object.values(approvedAssets)[0];
 expect(candidate,'preview fixture must have an approved synthetic original').toBeDefined();
 const originalSha=candidate!.originalSha256;
 const root=resolve(process.cwd(),'..'); // npm --prefix frontend executes Playwright with frontend cwd
 // Actual Chromium GDI-font glyph measurement at a fully authored scene
 // frame. A screenshot or DOM node existing is not a no-clipping proof.
 const finalScene=initialPreview.props.timeline.scenes[0] as Scene;
 const typographyFrame=finalScene.start_frame+finalScene.duration_frames-1;
 await page.getByLabel('Seek exact frame').fill(String(typographyFrame));
 await expect(stage.locator(`[data-global-frame="${typographyFrame}"][data-scene-id]`)).toBeVisible();
 await page.evaluate(()=>document.fonts.ready);
 const measureCritical=async()=>stage.locator('[data-layer][data-claim] > span').evaluateAll(elements=>
   elements.map(element=>{
     const span=element as HTMLElement;
     const layer=span.parentElement as HTMLElement;
     const bounds=layer.getBoundingClientRect();
     const glyphs:{left:number;right:number;top:number;bottom:number}[]=[];
     const walker=document.createTreeWalker(span,NodeFilter.SHOW_TEXT);
     let node=walker.nextNode() as Text|null;
     while(node){
       const raw=node.textContent??'';
       let offset=0;
       for(const char of Array.from(raw)){
         const width=char.length;
         if(char.trim()){
           const range=document.createRange();
           range.setStart(node,offset);range.setEnd(node,offset+width);
           for(const rect of Array.from(range.getClientRects()))
             if(rect.width>0&&rect.height>0)glyphs.push({left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom});
         }
         offset+=width;
       }
       node=walker.nextNode() as Text|null;
     }
     const visible=getComputedStyle(layer).opacity!=='0'&&glyphs.length>0;
     const clipped=visible&&glyphs.some(rect=>rect.left<bounds.left-1||
       rect.right>bounds.right+1||rect.top<bounds.top-1||rect.bottom>bounds.bottom+1);
     const lines=[...new Set(glyphs.map(rect=>Math.round(rect.top*2)/2))].length;
     return {layerId:layer.dataset.layer??'',claimId:layer.dataset.claim??'',
       text:span.textContent??'',font:getComputedStyle(span).fontFamily,
       fontSize:getComputedStyle(span).fontSize,visible,clipped,lines,glyphCount:glyphs.length,
       bounds:{x:bounds.x,y:bounds.y,width:bounds.width,height:bounds.height}};
   }));
 const measured=await measureCritical();
 const authoredText=new Map(finalScene.layers.filter(layer=>layer.text!==null&&layer.source_claim_id)
  .map(layer=>[layer.layer_id,layer]));
 const critical=measured.filter(item=>item.visible&&authoredText.has(item.layerId));
 expect(critical.length,'at least one visible source-backed text layer must be glyph-measured').toBeGreaterThan(0);
 for(const item of critical){
   const source=authoredText.get(item.layerId)!;
   expect(item.text,'frozen critical source text must not be truncated/changed').toBe(source.text);
   expect(item.clipped,'critical glyph extends outside its authored viewport').toBeFalsy();
   expect(item.lines,'critical glyph line count exceeds authorial max_lines')
    .toBeLessThanOrEqual(source.text_layout!.max_lines);
 }
 const typographyDir=resolve(process.cwd(),'.artifacts','typography');
 mkdirSync(typographyDir,{recursive:true});
 const typographyShot=await stage.screenshot();
 writeFileSync(resolve(typographyDir,'critical-source-chromium.png'),typographyShot);
 writeFileSync(resolve(typographyDir,'critical-typography.json'),JSON.stringify({
   projectId:initialPreview.props.timeline.project_id,frame:typographyFrame,
   fontSha256:initialPreview.props.media.fontSha256,
   screenshotSha256:createHash('sha256').update(typographyShot).digest('hex'),
   rows:critical.map(row=>({...row,expectedMaxLines:authoredText.get(row.layerId)!.text_layout!.max_lines}))
 },null,2));
 // Adversarial browser layout: an impossible width must be detected by the
 // exact glyph-rect discriminator, NOT made to pass by WebKit line-clamp.
 const targetLayer=stage.locator(`[data-layer="${critical[0].layerId}"] > span`).first();
 const previousStyle=await targetLayer.getAttribute('style');
 await targetLayer.evaluate(element=>{
   const node=element as HTMLElement;
   node.style.width='2px';node.style.minWidth='2px';node.style.maxWidth='2px';
   node.style.whiteSpace='nowrap';node.style.overflow='hidden';
 });
 const distorted=await measureCritical();
 const violated=distorted.find(item=>item.layerId===critical[0].layerId);
 expect(violated?.clipped,'intentional critical clipping must be discovered').toBeTruthy();
 await targetLayer.evaluate((element,css)=>{
   (element as HTMLElement).setAttribute('style',css??'');
 },previousStyle);
 await page.getByLabel('Seek exact frame').fill('0');
 await expect(stage.locator('[data-global-frame="0"][data-scene-id]')).toBeVisible();
 const originalFile=resolve(root,'renderer','.artifacts','approved-player-test',
   'artifacts','sha256',originalSha.slice(0,2),originalSha.slice(2));
 const withheldFile=originalFile+'.temporarily-withheld-b2-e2e';
 expect(existsSync(originalFile),'fixture must resolve the exact immutable original').toBeTruthy();
 await page.getByRole('button',{name:'Reload persisted draft'}).click();
 try{
  renameSync(originalFile,withheldFile);
  await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
  await expect(page.getByRole('alert')).toContainText('424 PLAYER_PREVIEW_UNAVAILABLE',{timeout:30000});
  await expect(page.getByLabel('Read-only local Remotion Player')).toHaveCount(0);
 }finally{
  renameSync(withheldFile,originalFile);
 }
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 await expect(page.getByLabel('Read-only local Remotion Player')).toBeVisible({timeout:30000});
 const samples=new Set<number>();
 for(let i=0;i<first.data.length;i+=128)samples.add(first.data[i]);
 expect(samples.size,'the actual Player frame is not blank').toBeGreaterThan(3);
 await page.getByLabel('Seek exact frame').fill('10');
 await expect(stage.locator('[data-global-frame="10"][data-scene-id]')).toBeVisible({timeout:10000});
 const beforeFocus=PNG.sync.read(await stage.screenshot());
 expect(fatalErrors,'browser Player must not throw React hook or runtime errors').toEqual([]);
 const focus=page.getByLabel('Authorized focus movement');
 const currentCameraMode=initialPreview.props.timeline.scenes[0].camera.mode;
 const targetFocus=currentCameraMode==='pull_out'?'overview_to_detail':'detail_to_overview';
 await focus.selectOption(targetFocus);
 await page.getByRole('button',{name:/Save staging/}).click();
 await expect(page.getByRole('status').filter({hasText:'Save authored G4 beat staging completed'}))
  .toBeVisible({timeout:30000});
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 await expect(stage.locator('[data-global-frame="0"][data-scene-id]')).toBeVisible({timeout:30000});
 await page.getByLabel('Seek exact frame').fill('10');
 await expect(stage.locator('[data-global-frame="10"][data-scene-id]')).toBeVisible({timeout:10000});
 const focused=PNG.sync.read(await stage.screenshot());
 expect(focused.data.equals(beforeFocus.data),'authorized focus edit must change actual Player pixels').toBeFalsy();
 // G4 camera scalar PATCH must recompile camera keys, change actual pixels,
 // and survive SQLite-backed host preview/reload; no DOM-only success is enough.
 const cameraEvent=initialPreview.props.timeline.scenes[0].events.find((event:Motion)=>event.preset_id==='camera-push');
 expect(cameraEvent,'native fixture requires an authored camera-push event').toBeDefined();
 const cameraFrame=initialPreview.props.timeline.scenes[0].start_frame+
  cameraEvent!.start_frame+Math.min(cameraEvent!.duration_frames-1,
    Math.max(1,Math.floor(cameraEvent!.duration_frames/2)));
 await page.getByLabel('Seek exact frame').fill(String(cameraFrame));
 await expect(stage.locator(`[data-global-frame="${cameraFrame}"][data-scene-id]`)).toBeVisible();
 const beforeCamera=PNG.sync.read(await stage.screenshot());
 const currentCamera=await request.get('http://127.0.0.1:8000/api/v1/projects/proj_001/storyboard/timeline');
 expect(currentCamera.ok()).toBeTruthy();
 const currentCameraTrack=(await currentCamera.json()).timeline.scenes[0].camera.keyframes;
 await page.getByLabel('Authored motion event').selectOption(cameraEvent!.event_id);
 await page.getByLabel('Authorized scalar presentation parameter').selectOption('to_scale');
 const scalar=page.getByLabel('Motion parameter value');
 const oldScalar=Number(await scalar.inputValue());
 const newScalar=oldScalar<=1.15?oldScalar+0.02:oldScalar-0.02;
 await scalar.fill(String(newScalar));
 await page.getByRole('button',{name:/Save motion/}).click();
 await expect(page.getByRole('status').filter({hasText:'Save motion parameter completed'}))
  .toBeVisible({timeout:30000});
 const persistedCamera=await request.get('http://127.0.0.1:8000/api/v1/projects/proj_001/storyboard/timeline');
 expect(persistedCamera.ok()).toBeTruthy();
 const cameraRevision=(await persistedCamera.json() as {timeline:typeof initialPreview.props.timeline}).timeline.scenes[0];
 expect(cameraRevision.events.find((e:Motion)=>e.event_id===cameraEvent!.event_id)?.params.to_scale).toBeCloseTo(newScalar);
 expect(cameraRevision.camera.keyframes).not.toEqual(currentCameraTrack);
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 await page.getByLabel('Seek exact frame').fill(String(cameraFrame));
 await expect(stage.locator(`[data-global-frame="${cameraFrame}"][data-scene-id]`)).toBeVisible();
 const afterCamera=PNG.sync.read(await stage.screenshot());
 let changedCameraPixels=0;
 for(let i=0;i<beforeCamera.data.length;i+=4){
  if(Math.abs(beforeCamera.data[i]-afterCamera.data[i])+
     Math.abs(beforeCamera.data[i+1]-afterCamera.data[i+1])+
     Math.abs(beforeCamera.data[i+2]-afterCamera.data[i+2])>12)changedCameraPixels++;
 }
 expect(changedCameraPixels,'registered camera scalar must move actual Chromium Player pixels').toBeGreaterThan(30);
 const variant=page.getByLabel('Registered presentation variant');
 const original=await variant.inputValue();
 const target=original==='A'?'B':'A';
 await variant.selectOption(target);
 await page.getByRole('button',{name:/Save G4 revision/}).click();
 await expect(page.getByRole('status').filter({hasText:'Save storyboard variant completed'})).toBeVisible({timeout:25000});
 await expect(variant).toHaveValue(target);
 const layerX=page.getByLabel('X (pixels)');
 const oldX=Number(await layerX.inputValue());
 await layerX.fill(String(oldX+1));
 await page.getByRole('button',{name:/Save position/}).click();
 await expect(page.getByRole('status').filter({hasText:'Save layer position completed'}))
  .toBeVisible({timeout:30000});
 await expect(layerX).toHaveValue(String(oldX+1));
 const widthInput=page.getByLabel('Width (pixels)');
 if(await widthInput.isEnabled()){
  const originalWidth=Number(await widthInput.inputValue());
  const targetWidth=originalWidth>1?originalWidth-1:originalWidth+1;
  await widthInput.fill(String(targetWidth));
  await page.getByRole('button',{name:/Save size/}).click();
  await expect(page.getByRole('status').filter({hasText:'Save media dimensions completed'}))
   .toBeVisible({timeout:30000});
  await expect(widthInput).toHaveValue(String(targetWidth));
 }
 await page.getByRole('button',{name:'Reload persisted draft'}).click();
 await expect(variant).toHaveValue(target);
 await expect(layerX).toHaveValue(String(oldX+1));
 // Hold an authentic host preview response, commit a concurrent SQLite G4
 // revision, then release the old bytes. The editor must never display them.
 await page.getByRole('button',{name:'Reload persisted draft'}).click();
 await expect(page.getByLabel('Read-only local Remotion Player')).toHaveCount(0);
 let releasePreview!:()=>void;
 let previewResolved!:()=>void;
 const previewReady=new Promise<void>(resolve=>{previewResolved=resolve;});
 const release=new Promise<void>(resolve=>{releasePreview=resolve;});
 await page.route('**/storyboard/preview',async route=>{
  const response=await route.fetch();
  previewResolved();
  await release;
  await route.fulfill({response});
 });
 const oldPreview=page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 await previewReady;
 const current=await request.get('http://127.0.0.1:8000/api/v1/projects/proj_001/storyboard/scenes?offset=0&limit=1');
 expect(current.ok()).toBeTruthy();
 const body=await current.json();
 const concurrentScene=body.scenes[0];
 const concurrentVariant=concurrentScene.variant_id==='C'?'A':'C';
 const concurrent=await request.patch(
  'http://127.0.0.1:8000/api/v1/projects/proj_001/storyboard/scenes/'+concurrentScene.scene_id,{
   headers:{'Idempotency-Key':'browser-preview-race-001'},
   data:{expected_revision:body.project_revision,scene_id:concurrentScene.scene_id,
    changes:{variant_id:concurrentVariant}}
  });
 expect(concurrent.ok(),await concurrent.text()).toBeTruthy();
 releasePreview();
 await oldPreview;
 await expect(page.getByRole('alert')).toContainText('G4_DRAFT_STALE');
 await expect(page.getByLabel('Read-only local Remotion Player')).toHaveCount(0);
 // Browser UI 409 must be caused by an actual already committed SQLite
 // revision, not a mocked conflict response. A stale G4 edit cannot commit.
 const afterConcurrent=await request.get('http://127.0.0.1:8000/api/v1/projects/proj_001/storyboard/scenes?offset=0&limit=1');
 expect(afterConcurrent.ok()).toBeTruthy();
 const afterConcurrentRevision=(await afterConcurrent.json()).project_revision as number;
 const staleX=Number(await layerX.inputValue());
 await layerX.fill(String(staleX>2?staleX-1:staleX+1));
 await page.getByRole('button',{name:/Save position/}).click();
 await expect(page.getByRole('alert')).toContainText('409 REVISION_CONFLICT');
 const afterStale=await request.get('http://127.0.0.1:8000/api/v1/projects/proj_001/storyboard/scenes?offset=0&limit=1');
 expect((await afterStale.json()).project_revision).toBe(afterConcurrentRevision);
 // The refreshed editor must expose a real unsupported G4 operation as 422
 // without creating a new immutable draft revision.
 const currentOperation=await page.getByLabel('Selected authored staging operation').inputValue();
 const rejectedOperation=currentOperation==='exit'?'reposition':'exit';
 await page.getByLabel('Selected authored staging operation').selectOption(rejectedOperation);
 await page.getByRole('button',{name:/Save staging/}).click();
 await expect(page.getByRole('alert')).toContainText('422 STAGING_OPERATION_UNSUPPORTED');
 const afterInvalid=await request.get('http://127.0.0.1:8000/api/v1/projects/proj_001/storyboard/scenes?offset=0&limit=1');
 expect((await afterInvalid.json()).project_revision).toBe(afterConcurrentRevision);
 await page.getByLabel('Selected authored staging operation').selectOption(currentOperation);
 expect(fatalErrors,'no fatal browser errors during edit/reload').toEqual([]);
});
