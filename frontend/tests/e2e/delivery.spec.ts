import {test,expect} from '@playwright/test';
import {createHash} from 'node:crypto';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';

test('delivery reload exposes exact QC-passed audiovisual export',async({page,request})=>{
 test.skip(process.env.HVS_B3_FIXTURE!=='1','Requires native B3 SQLite/Remotion fixture');
 await page.goto('/');
 await page.getByLabel('Project ID').fill('proj_001');
 await page.getByRole('button',{name:'Open existing project'}).click();
 await page.getByRole('button',{name:/Render & Delivery/}).click();
 await expect(page.getByText(/SUCCEEDED · 120\/120 frames · QC PASS/)).toBeVisible({timeout:30000});
 await expect(page.getByText(/G4 production authority/)).toBeVisible();
 await expect(page.getByText(/Status: APPROVED/).first()).toBeVisible();
 const media=page.locator('video');await expect(media).toBeVisible();
 await media.evaluate(async element=>{const video=element as HTMLVideoElement;video.muted=false;await video.play();});
 await expect.poll(()=>media.evaluate(v=>(v as HTMLVideoElement).currentTime),{timeout:15000}).toBeGreaterThan(.25);
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
