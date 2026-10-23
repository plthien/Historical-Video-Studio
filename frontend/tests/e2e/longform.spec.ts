import {test,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import path from 'node:path';
import {performance} from 'node:perf_hooks';

test('longform-storyboard 61 scene real SQLite pagination preview edit and reopen',async({page})=>{
 test.skip(process.env.HVS_B2_LONGFORM!=='1','Requires native Windows B1-compiled 61-scene SQLite source; no mock API');
 test.setTimeout(180_000);
 const metrics:{action:string;elapsedMs:number;maxMs:number}[]=[];
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
 await measure('middle page',15000,async()=>{
  await page.getByRole('button',{name:'Next 24'}).click();
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
 const totalFrames=await page.evaluate(()=>{
   const control=document.querySelector<HTMLInputElement>('#g4-seek');
   return Number(control?.max||0);
 });
 await measure('seek end',7000,async()=>{
  await page.getByLabel('Seek exact frame').fill(String(Math.max(0,totalFrames-1)));
  await expect(page.getByLabel('Seek exact frame')).toHaveValue(String(Math.max(0,totalFrames-1)));
 });
 const destination=path.resolve(import.meta.dirname,'../../.artifacts/longform');
 mkdirSync(destination,{recursive:true});
 writeFileSync(path.join(destination,'b2-61-scene-ui-metrics.json'),
  JSON.stringify({status:'LOCAL_PASS',projectScenes:61,
   source:'SYNTHETIC_SQLITE_APPROVAL_FIXTURE_NOT_REAL_RIGHTS',
   pageLimit:24,retainedSelection:selected,metrics},null,2));
});
