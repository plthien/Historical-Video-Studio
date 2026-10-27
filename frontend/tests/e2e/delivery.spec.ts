import {test,expect} from '@playwright/test';
import {createHash} from 'node:crypto';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';

test('full-flow delivery reload exposes exact QC-passed audiovisual export',async({page,request})=>{
 test.skip(process.env.HVS_B3_FIXTURE!=='1','Requires native B3 SQLite/Remotion fixture');
 await page.goto('/');
 await page.getByLabel('Project ID').fill('proj_001');
 await page.getByRole('button',{name:'Open existing project'}).click();
 await page.getByRole('button',{name:/Render & Delivery/}).click();
 await expect(page.getByText(/SUCCEEDED · 120\/120 frames · QC PASS/)).toBeVisible({timeout:30000});
 await expect(page.getByText(/G4 production authority/)).toBeVisible();
 await expect(page.getByText(/Status: APPROVED/).first()).toBeVisible();
 const media=page.locator('video');await expect(media).toBeVisible();
 await page.getByRole('button',{name:'Start server-issued view/listen review'}).click();
 const playToEnd=async(muted:boolean,volume:number)=>{
  await media.evaluate(async(element,state)=>{const video=element as HTMLVideoElement;
   video.pause();video.currentTime=0;video.muted=state.muted;video.volume=state.volume;await video.play();},
   {muted,volume});
  await expect.poll(()=>media.evaluate(v=>(v as HTMLVideoElement).ended),{timeout:15000}).toBe(true);
 };
 await playToEnd(true,1);
 await expect(page.getByLabel('review-progress')).toContainText(/listened 0\.00s/);
 await page.getByRole('button',{name:'Confirm complete video and audio review'}).click();
 await expect(page.getByRole('alert')).toContainText('G5_REVIEW_INCOMPLETE');
 await playToEnd(false,0);
 await expect(page.getByLabel('review-progress')).toContainText(/listened 0\.00s/);
 await media.evaluate(element=>{const video=element as HTMLVideoElement;video.pause();video.currentTime=2;});
 await expect(page.getByLabel('review-progress')).toContainText(/listened 0\.00s/);
 await playToEnd(false,1);
 await page.getByRole('button',{name:'Confirm complete video and audio review'}).click();
 await expect(page.getByText('Complete verified review completed.')).toBeVisible();
 await page.getByRole('button',{name:/Inspect source credits/}).click();
 await expect(page.getByText(/Inspect source credits \(1\)/)).toBeVisible();
 const mp4=page.getByRole('link',{name:'Download MP4'});await expect(mp4).toBeVisible();
 const response=await request.get(await mp4.getAttribute('href') as string);
 expect(response.status()).toBe(200);const bytes=await response.body();
 expect(bytes.length).toBeGreaterThan(1000);
 const dir=resolve(process.cwd(),'.artifacts','delivery');mkdirSync(dir,{recursive:true});
 writeFileSync(resolve(dir,'delivery.png'),await page.screenshot({fullPage:true}));
 writeFileSync(resolve(dir,'download.json'),JSON.stringify({sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length}));
});
