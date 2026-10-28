import {openExistingProject} from "./project-workflow-helper";
import {test,expect} from '@playwright/test';
import {createHash} from 'node:crypto';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';

test('full-flow delivery reload exposes exact QC-passed audiovisual export',async({page,request},testInfo)=>{
 test.skip(process.env.HVS_B3_FIXTURE!=='1','Requires native B3 SQLite/Remotion fixture');
 const configPath=process.env.HVS_FULL_FLOW_CONFIG;
 const project=configPath
  ?(JSON.parse(readFileSync(resolve(process.cwd(),configPath),'utf8')) as {project:string}).project
  :'proj_001';
 await page.goto('/');
 await openExistingProject(page,project);
 await page.getByRole('button',{name:/Render & Delivery/}).click();
 await expect(page.getByText(/SUCCEEDED · 120\/120 frames · QC PASS/)).toBeVisible({timeout:30000});
 await expect(page.getByText(/G4 production authority/)).toBeVisible();
 await expect(page.getByText(/Status: APPROVED/).first()).toBeVisible();
 const media=page.locator('video');await expect(media).toBeVisible();
 const originalViewport=page.viewportSize()!;
 for(const dimensions of [{width:1366,height:768},{width:1920,height:1080}]){
   await page.setViewportSize(dimensions);
   await expect(media).toBeVisible();
   await page.screenshot({path:testInfo.outputPath(`pr13-g5-populated-actual-video-${dimensions.width}.png`),animations:"disabled"});
   const metrics=await page.evaluate(()=>{
     const video=document.querySelector('video')!.getBoundingClientRect();
     return {overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+2,
             width:video.width,height:video.height,viewport:innerWidth};
   });
   expect(metrics.overflow).toBe(false);
   expect(metrics.width).toBeGreaterThan(200);
   expect(metrics.width).toBeLessThan(metrics.viewport);
 }
 await page.setViewportSize(originalViewport);
 const start=page.getByRole('button',{name:'Start server-issued view/listen review'});
 if(await start.isEnabled()){
  await start.click();
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
 }else{
  await expect(page.getByText(/G5 status:/).locator('..')).toContainText('APPROVED');
 }
 await page.getByRole('button',{name:/Inspect source credits/}).click();
 await expect(page.getByText(/Inspect source credits \(1\)/)).toBeVisible();
 const mp4=page.getByRole('link',{name:'Download MP4'});await expect(mp4).toBeVisible();
 const response=await request.get(await mp4.getAttribute('href') as string);
 expect(response.status()).toBe(200);const bytes=await response.body();
 expect(bytes.length).toBeGreaterThan(1000);
 const dir=resolve(process.cwd(),'.artifacts','delivery');mkdirSync(dir,{recursive:true});
 writeFileSync(resolve(dir,'delivery.png'),await page.screenshot({fullPage:true}));
 writeFileSync(resolve(dir,'download.json'),JSON.stringify({project_id:project,
  sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length}));
});
