import {openExistingProject} from "./project-workflow-helper";
import {test,expect} from '@playwright/test';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {bundle} from '../../../renderer/node_modules/@remotion/bundler/dist/index.js';
import {renderStill,selectComposition} from '../../../renderer/node_modules/@remotion/renderer/dist/index.js';
import {PNG} from 'pngjs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';

const sha=(buf:Buffer)=>createHash('sha256').update(buf).digest('hex');
test('pr10 reviewed-asset-picker changes real Chromium T02 A/B and preserves long critical text',async({page,request})=>{
 test.skip(process.env.HVS_PR10_FIXTURE!=='mask','Uses an independently G3-approved synthetic T02 source project on native Windows');
 const project='proj_pr10_mask';
 const uri='http://127.0.0.1:8000/api/v1/projects/'+project;
 const gateBefore=(await (await request.get(uri+'/gates')).json()) as {gate_id:string;state:string;dependency_fingerprint:string}[];
 await page.goto('/');
 await openExistingProject(page,project);
 await expect(page.getByText(project,{exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:/Motion Storyboard/}).click();
 await expect(page.getByLabel('Scene inspector')).toBeVisible();
 const layerPicker=page.getByLabel('Layer to reposition');
 const layerOptions=await layerPicker.locator('option').all();
 let portrait='';
 for(const item of layerOptions){
   const text=await item.textContent();
   if(text?.includes('portrait')){portrait=await item.getAttribute('value')??'';break;}
 }
 expect(portrait).not.toBe('');
 await layerPicker.selectOption(portrait);
 const picker=page.getByLabel('Eligible approved source');
 await expect(picker).toBeVisible({timeout:15000});
 const choices=await picker.locator('option').evaluateAll(items=>items.map(x=>({
   value:(x as HTMLOptionElement).value,text:x.textContent??''
 })));
 expect(choices).toHaveLength(2);
 const current=await picker.inputValue();
 const candidateB=choices.find(x=>x.value!==current)!.value;
 const scenePage=await (await request.get(uri+'/storyboard/scenes')).json();
 const scene=scenePage.scenes[0];
 const frame=scene.start_frame+scene.duration_frames-1;
 const seek=async()=>{
  const stage=page.getByTestId('player-stage');
  await page.getByLabel('Seek exact frame').fill(String(frame));
  await expect(stage.locator('[data-global-frame="'+frame+'"][data-scene-id]')).toBeVisible({timeout:20000});
  return stage;
 };
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 const stage=await seek();
 // Compare exactly the same fixed 1920x1080 Chromium composition viewport
 // across cold reloads; editor panel CSS must not rescale a raster baseline.
 const fixedViewport=async()=>{
   await stage.evaluate(el=>{const node=el as HTMLElement;
     node.style.width='1920px';node.style.height='1080px';});
 };
 await fixedViewport();
 await page.evaluate(()=>document.fonts.ready);
 const authoredCanvas=()=>stage.locator('[data-global-frame="'+frame+'"][data-scene-id="'+scene.scene_id+'"]');
 const a=await authoredCanvas().screenshot();
 await picker.selectOption(candidateB);
 await page.getByRole('button',{name:'Save A/B source (G4/G5 stale)'}).click();
 await expect(page.getByRole('status').filter({hasText:'Save reviewed A/B original'})).toBeVisible();
 const serverB=await (await request.get(uri+'/storyboard/scenes')).json();
 expect(serverB.scenes[0].layers.find((l:any)=>l.layer_id===portrait)?.asset_id).toBe(candidateB);
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 await seek();
 await fixedViewport();
 await page.evaluate(()=>document.fonts.ready);
 const b=await authoredCanvas().screenshot();
 expect(sha(a),'B must render different real Chromium pixels from A').not.toBe(sha(b));
 // G09 for selected B/T02: exact same current host-issued props in both
 // real Browser Player and Node Remotion. No mock/PNG color-only shortcut.
 const bAuthority=await (await request.get(uri+'/storyboard/preview')).json();
 const propsB=bAuthority.props;
 expect(propsB.media.sourceKind).toBe('APPROVED_LOCAL');
 expect(propsB.media.assets[candidateB].originalSha256).toMatch(/^[a-f0-9]{64}$/);
 const originalStageStyle=await stage.getAttribute('style');
 await stage.evaluate(el=>{(el as HTMLElement).style.width='1920px';(el as HTMLElement).style.height='1080px';});
 const rendered=stage.locator('[data-global-frame="'+frame+'"][data-scene-id="'+scene.scene_id+'"]');
 await expect(rendered).toBeVisible();
 const actualPNG=PNG.sync.read(await rendered.screenshot({scale:'css'}));
 expect(actualPNG.width).toBeGreaterThanOrEqual(1920);
 expect(actualPNG.height).toBeGreaterThanOrEqual(1080);
 const browserPNG=new PNG({width:1920,height:1080});
 PNG.bitblt(actualPNG,browserPNG,0,0,1920,1080,0,0);
 const bundled=await bundle({entryPoint:resolve(process.cwd(),'..','renderer','remotion','entry.tsx')});
 const composition=await selectComposition({serveUrl:bundled,id:'HistoricalTimelineV1',inputProps:propsB});
 const parityDir=resolve(process.cwd(),'.artifacts','pr10');
 mkdirSync(parityDir,{recursive:true});
 const nodeFile=resolve(parityDir,'chromium-selected-B-node.png');
 await renderStill({serveUrl:bundled,composition,inputProps:propsB,output:nodeFile,
                    frame,imageFormat:'png'});
 const nodePNG=PNG.sync.read(readFileSync(nodeFile));
 expect(nodePNG.width).toBe(1920);expect(nodePNG.height).toBe(1080);
 let totalDifference=0,significant=0,count=0;
 for(let y=0;y<1080;y+=2)for(let x=0;x<1920;x+=2){
   const offset=4*(y*1920+x);
   const delta=Math.abs(browserPNG.data[offset]-nodePNG.data[offset])+
     Math.abs(browserPNG.data[offset+1]-nodePNG.data[offset+1])+
     Math.abs(browserPNG.data[offset+2]-nodePNG.data[offset+2]);
   totalDifference+=delta/3;significant+=delta>90?1:0;count++;
 }
 const parity={meanDiff:totalDifference/count,pixelMismatch:significant/count,
               sourceG4Head:bAuthority.draft_manifest_sha256,
               sourceBOriginalSha256:propsB.media.assets[candidateB].originalSha256,
               nodeSha256:sha(readFileSync(nodeFile)),
               browserSha256:sha(PNG.sync.write(browserPNG))};
 expect(parity.meanDiff,'Current G3 B/T02 Player vs Node RGB mismatch').toBeLessThan(20);
 expect(parity.pixelMismatch,'Current G3 B/T02 Player vs Node large-pixel mismatch').toBeLessThan(0.14);
 writeFileSync(resolve(parityDir,'chromium-selected-B-browser.png'),PNG.sync.write(browserPNG));
 await stage.evaluate((el,style)=>(el as HTMLElement).setAttribute('style',style??''),originalStageStyle);
 const gatesAfter=(await (await request.get(uri+'/gates')).json()) as typeof gateBefore;
 for(const name of ['G1','G2','G3']){
   const before=gateBefore.find(x=>x.gate_id===name)!;
   const after=gatesAfter.find(x=>x.gate_id===name)!;
   expect(after.state,'A/B must not modify upstream '+name).toBe(before.state);
   expect(after.dependency_fingerprint).toBe(before.dependency_fingerprint);
 }
 await page.reload();
 await openExistingProject(page,project);
 await page.getByRole('button',{name:/Motion Storyboard/}).click();
 await expect(page.getByLabel('Scene inspector')).toBeVisible();
 await page.getByLabel('Layer to reposition').selectOption(portrait);
 await expect(page.getByLabel('Eligible approved source')).toHaveValue(candidateB);
 const afterReload=page.getByLabel('Eligible approved source');
 await afterReload.selectOption(current);
 await page.getByRole('button',{name:'Save A/B source (G4/G5 stale)'}).click();
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 await seek();
 await fixedViewport();
 await page.evaluate(()=>document.fonts.ready);
 const returned=await authoredCanvas().screenshot();
 expect(sha(returned),'Cold reopened A must restore exactly authored A pixels').toBe(sha(a));
 const critical=await page.getByTestId('player-stage').locator('[data-layer][data-claim] > span').evaluateAll(elements=>
   elements.map(x=>{
     const el=x as HTMLElement,parent=el.parentElement as HTMLElement;
     const rect=parent.getBoundingClientRect();
     const glyphs:DOMRect[]=[];
     const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
     let node=walker.nextNode() as Text|null;
     while(node){
       const text=node.textContent??'';
       for(let i=0;i<text.length;i++){
         if(!text[i]?.trim())continue;
         const range=document.createRange();
         range.setStart(node,i);range.setEnd(node,i+1);
         glyphs.push(...Array.from(range.getClientRects()));
       }
       node=walker.nextNode() as Text|null;
     }
     return {layerId:parent.dataset.layer??'',text:el.textContent??'',
             font:getComputedStyle(el).fontFamily,
             visible:getComputedStyle(parent).opacity!=='0',glyphCount:glyphs.length,
             clipped:glyphs.some(g=>g.left<rect.left-1||g.right>rect.right+1||
                                    g.top<rect.top-1||g.bottom>rect.bottom+1),
             lines:new Set(glyphs.map(g=>Math.round(g.top*2)/2)).size};
   }));
 const long=critical.filter(x=>x.visible&&x.text.length>=65);
 for(const row of long){
   const authored=scene.layers.find((x:any)=>x.layer_id===row.layerId);
   expect(row.text).toBe(authored?.text);
 }
 expect(long.length,'Chromium must measure real source-backed long T02 captions').toBeGreaterThan(0);
 expect(long.every(x=>x.glyphCount>50&&!x.clipped&&x.lines<=3)).toBeTruthy();
 // Browser adversarial proof: an overlong caption in a 1-pixel line box must
 // visibly extend beyond authored glyph bounds, even if CSS hides the ink.
 const longLayerId=long[0]!.layerId;
 const textNode=page.getByTestId('player-stage').locator(`[data-layer="${longLayerId}"] > span`).first();
 const originalStyle=await textNode.getAttribute('style');
 await textNode.evaluate(node=>{
   const el=node as HTMLElement;
   el.style.width='1px';el.style.minWidth='1px';el.style.maxWidth='1px';
   el.style.whiteSpace='nowrap';el.style.overflow='hidden';
 });
 const actualOverflow=await textNode.evaluate(node=>{
   const element=node as HTMLElement,parent=element.parentElement as HTMLElement;
   const bounds=parent.getBoundingClientRect();
   const walker=document.createTreeWalker(element,NodeFilter.SHOW_TEXT);
   let text=walker.nextNode() as Text|null;
   while(text){
     for(let offset=0;offset<(text.textContent??'').length;offset++){
       if(!(text.textContent??'')[offset]?.trim())continue;
       const range=document.createRange();
       range.setStart(text,offset);range.setEnd(text,offset+1);
       for(const rect of Array.from(range.getClientRects())){
         if(rect.right>bounds.right+1||rect.left<bounds.left-1)return true;
       }
     }
     text=walker.nextNode() as Text|null;
   }
   return false;
 });
 expect(actualOverflow,'adversarial critical caption clipping must be detected').toBe(true);
 await textNode.evaluate((node,style)=>{(node as HTMLElement).setAttribute('style',style??'');},originalStyle);
 // Direct attacker attempt to select arbitrary original cannot pass the G4 source gate.
 const state=await (await request.get(uri+'/storyboard/scenes')).json();
 const forbidden=await request.patch(uri+'/storyboard/scenes/'+scene.scene_id,{
   data:{expected_revision:state.project_revision,scene_id:scene.scene_id,
         changes:{layer_edits:[{layer_id:portrait,approved_asset_id:'assetcand_forged_external'}]}},
   headers:{'Idempotency-Key':'PR10-forged-source-negative'}});
 expect([409,422,424]).toContain(forbidden.status());
 const directory=resolve(process.cwd(),'.artifacts','pr10');
 mkdirSync(directory,{recursive:true});
 const shots=[{name:'A',png:a},{name:'B',png:b},{name:'A-return',png:returned}];
 for(const row of shots)writeFileSync(resolve(directory,'chromium-'+row.name+'.png'),row.png);
 writeFileSync(resolve(directory,'g06-browser-a-b-a.json'),JSON.stringify({
   scope:'SYNTHETIC_G3_OPERATOR_APPROVAL_NOT_REAL_ARCHIVAL_RIGHTS',project,
   scene:scene.scene_id,frame,choiceA:current,choiceB:candidateB,
   sourceGatesPreserved:['G1','G2','G3'],
   screenshots:shots.map(x=>({name:x.name,sha256:sha(x.png)})),
   typography:long,parity,typographyAdversarialClippingDetected:actualOverflow,
   negativeStatus:forbidden.status()},null,2));
});
