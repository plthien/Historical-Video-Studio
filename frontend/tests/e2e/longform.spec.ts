import {test,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import path from 'node:path';
import {performance} from 'node:perf_hooks';
import {PNG} from 'pngjs';

test('longform-storyboard 61 scene real SQLite pagination preview edit and reopen',async({page})=>{
 test.skip(process.env.HVS_B2_LONGFORM!=='1','Requires native Windows B1-compiled 61-scene SQLite source; no mock API');
 test.setTimeout(180_000);
 const metrics:{action:string;elapsedMs:number;maxMs:number}[]=[];
 const fatalErrors:string[]=[];
 page.on('pageerror',e=>fatalErrors.push(e.message));
 page.on('console',m=>{if(m.type()==='error'&&/Invalid hook call|useContext|HistoryComposition|React/i.test(m.text()))fatalErrors.push(m.text());});
 async function measure(action:string,maxMs:number,fn:()=>Promise<void>){
   const start=performance.now();
   await fn();
   const elapsedMs=performance.now()-start;
   metrics.push({action,elapsedMs,maxMs});
   expect(elapsedMs,action+' exceeded declared UX budget').toBeLessThan(maxMs);
 }
 await measure('open',25000,async()=>{
  await page.goto('/');
  await page.getByLabel('Project ID').fill('proj_001');
  await page.getByRole('button',{name:'Open existing project'}).click();
  await expect(page.getByText('proj_001',{exact:true}).first()).toBeVisible();
  await page.getByRole('button',{name:/Motion Storyboard/}).click();
  await expect(page.getByText(/Scenes \(61\)/)).toBeVisible({timeout:20000});
 });
 const list=page.getByRole('listbox',{name:'Storyboard scenes'});
 await expect(list.getByRole('option')).toHaveCount(24);
 const firstPageFirstOption=await list.getByRole('option').first().textContent();
 await measure('middle page',15000,async()=>{
  await page.getByRole('button',{name:'Next 24'}).click();
  await expect(list.getByRole('option').first()).not.toHaveText(firstPageFirstOption!);
  await expect(list.getByRole('option')).toHaveCount(24);
  await list.getByRole('option').nth(6).click();
  await expect(list.getByRole('option').nth(6)).toHaveAttribute('aria-selected','true');
 });
 await measure('last page',15000,async()=>{
  await page.getByRole('button',{name:'Next 24'}).click();
  await expect(list.getByRole('option')).toHaveCount(13);
  await list.getByRole('option').last().click();
  await expect(list.getByRole('option').last()).toHaveAttribute('aria-selected','true');
 });
 const last=list.getByRole('option').last();
 const selected=await last.textContent();
 const variant=page.getByLabel('Registered presentation variant');
 const before=await variant.inputValue();
 const next=before==='A'?'B':'A';
 await measure('save last scene',60000,async()=>{
  await variant.selectOption(next);
  await page.getByRole('button',{name:/Save G4 revision/}).click();
  await expect(page.getByRole('status').filter({hasText:'Save storyboard variant completed'})).toBeVisible({timeout:45000});
  await expect(variant).toHaveValue(next);
 });
 await measure('reload last scene',30000,async()=>{
  await page.getByRole('button',{name:'Reload persisted draft'}).click();
  await expect(list.getByRole('option').last()).toHaveAttribute('aria-selected','true');
  await expect(list.getByRole('option').last()).toContainText(selected!.split(' · ')[0]);
  await expect(variant).toHaveValue(next);
 });
 await measure('host preview',60000,async()=>{
  await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
  await expect(page.getByTestId('player-stage')).toBeVisible({timeout:45000});
  await expect(page.getByText(/G4 DRAFT · VIEW ONLY/)).toBeVisible();
 });
 const stage=page.getByTestId('player-stage');
 async function proveRenderedOwner(action:string,selectedOption:import('@playwright/test').Locator){
  const caption=(await selectedOption.textContent())??'';
  const sceneId=caption.split(' · ')[0].trim();
  const match=caption.match(/frame (\d+)–(\d+)/);
  expect(match,'each scene option must expose its exact compiled frame range').not.toBeNull();
  const frame=Number(match![1]);
  await measure(action,7000,async()=>{
    await page.getByLabel('Seek exact frame').fill(String(frame));
    await expect(stage.locator(`[data-global-frame="${frame}"][data-scene-id="${sceneId}"]`))
     .toBeVisible({timeout:6500});
  });
  const png=PNG.sync.read(await stage.screenshot());
  expect(png.width).toBeGreaterThan(100);
  const sample=new Set<number>();
  for(let i=0;i<png.data.length;i+=128)sample.add(png.data[i]);
  expect(sample.size,'Player must show actual scene pixels, not an empty wrapper').toBeGreaterThan(3);
  return {sceneId,frame};
 }
 const lastRendered=await proveRenderedOwner('render last scene',last);
 await measure('navigate back to middle',15000,async()=>{
  await page.getByRole('button',{name:'Previous 24'}).click();
  await expect(list.getByRole('option')).toHaveCount(24);
  await list.getByRole('option').nth(6).click();
 });
 const middleRendered=await proveRenderedOwner('render middle scene',list.getByRole('option').nth(6));
 const middleFirstOption=await list.getByRole('option').first().textContent();
 await measure('navigate back to first',15000,async()=>{
  await page.getByRole('button',{name:'Previous 24'}).click();
  await expect(list.getByRole('option').first()).not.toHaveText(middleFirstOption!);
  await expect(list.getByRole('option')).toHaveCount(24);
  await list.getByRole('option').first().click();
 });
 const firstRendered=await proveRenderedOwner('render first scene',list.getByRole('option').first());
 const totalFrames=await page.evaluate(()=>{
  const control=document.querySelector<HTMLInputElement>('#g4-seek');
  return Number(control?.max||0);
 });
 await measure('seek end boundary',7000,async()=>{
  await page.getByLabel('Seek exact frame').fill(String(Math.max(0,totalFrames)));
  await expect(stage.locator(`[data-global-frame="${Math.max(0,totalFrames)}"][data-scene-id="${lastRendered.sceneId}"]`))
   .toBeVisible({timeout:6500});
 });
 expect(fatalErrors,'no browser runtime errors during multi-page seeks').toEqual([]);
 const destination=path.resolve(import.meta.dirname,'../../.artifacts/longform');
 mkdirSync(destination,{recursive:true});
 writeFileSync(path.join(destination,'b2-61-scene-ui-metrics.json'),
  JSON.stringify({status:'LOCAL_PASS',projectScenes:61,
   source:'SYNTHETIC_SQLITE_APPROVAL_FIXTURE_NOT_REAL_RIGHTS',
   pageLimit:24,retainedSelection:selected,renderedScenes:[firstRendered,middleRendered,lastRendered],fatalErrors,metrics},null,2));
});
