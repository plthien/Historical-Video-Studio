import {test,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';

test('pr10 source-authorized T06 multiline document and adversarial critical clipping in real Chromium',async({page,request})=>{
 test.skip(process.env.HVS_PR10_FIXTURE!=='typography',
    'Requires native Windows synthetic G1/G2/G3 approved T06 document project');
 const project='proj_pr10_typography';
 const uri='http://127.0.0.1:8000/api/v1/projects/'+project;
 const trusted=await request.get(uri+'/storyboard/preview');
 expect(trusted.status()).toBe(200);
 const authorized=await trusted.json();
 expect(authorized.props.media.sourceKind).toBe('APPROVED_LOCAL');
 const scene=authorized.props.timeline.scenes[0];
 expect(scene.template_id).toBe('T06');
 const excerpt=scene.layers.find((l:any)=>typeof l.text==='string'&&l.text.includes('SYNTHETIC DOCUMENT'));
 expect(excerpt).toBeDefined();
 expect(excerpt.text.includes('\n')).toBeTruthy();
 await page.goto('/');
 await page.getByLabel('Project ID').fill(project);
 await page.getByRole('button',{name:'Open existing project'}).click();
 await page.getByRole('button',{name:/Motion Storyboard/}).click();
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 const stage=page.getByTestId('player-stage');
 const final=scene.start_frame+scene.duration_frames-1;
 await page.getByLabel('Seek exact frame').fill(String(final));
 await expect(stage.locator(`[data-global-frame="${final}"][data-scene-id="${scene.scene_id}"]`)).toBeVisible();
 await page.evaluate(()=>document.fonts.ready);
 const measured=await stage.locator('[data-layer][data-claim] > span').evaluateAll(elements=>{
   return elements.map(item=>{
     const el=item as HTMLElement,outer=el.parentElement as HTMLElement;
     const bounds=outer.getBoundingClientRect();
     const frame=outer.closest('[data-testid="player-stage"]')?.getBoundingClientRect();
     const rects:{left:number;right:number;top:number;bottom:number}[]=[];
     const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
     let node=walker.nextNode() as Text|null;
     while(node){
       const raw=node.textContent??'';
       for(let i=0;i<raw.length;i++){
         if(!raw[i]?.trim())continue;
         const range=document.createRange();
         range.setStart(node,i);range.setEnd(node,i+1);
         for(const r of Array.from(range.getClientRects())){
           if(r.width>0&&r.height>0)rects.push({left:r.left,right:r.right,top:r.top,bottom:r.bottom});
         }
       }
       node=walker.nextNode() as Text|null;
     }
     return {id:outer.dataset.layer??'',text:el.textContent??'',
       font:getComputedStyle(el).fontFamily,visible:getComputedStyle(outer).opacity!=='0',
       glyphCount:rects.length,lines:new Set(rects.map(r=>Math.round(r.top*2)/2)).size,
       clipped:rects.some(r=>r.left<bounds.left-1||r.right>bounds.right+1||
                           r.top<bounds.top-1||r.bottom>bounds.bottom+1||
                           !frame||r.left<frame.left-1||r.right>frame.right+1||
                           r.top<frame.top-1||r.bottom>frame.bottom+1)};
   });
 });
 const target=measured.find(x=>x.visible&&x.id===excerpt.layer_id);
 expect(target,'T06 source-backed excerpt must be displayed').toBeDefined();
 expect(target!.text).toBe(excerpt.text);
 expect(target!.font.toLowerCase()).toContain(String(authorized.props.media.fontFamily).toLowerCase());
 expect(target!.glyphCount).toBeGreaterThan(50);
 expect(target!.lines).toBeGreaterThanOrEqual(2);
 expect(target!.lines).toBeLessThanOrEqual(excerpt.text_layout.max_lines);
 expect(target!.clipped).toBe(false);
 const span=stage.locator(`[data-layer="${excerpt.layer_id}"] > span`).first();
 const initialStyle=await span.getAttribute('style');
 await span.evaluate(el=>{
   const node=el as HTMLElement;
   node.style.whiteSpace='nowrap';node.style.width='1px';node.style.minWidth='1px';node.style.overflow='hidden';
 });
 const attacked=await span.evaluate(el=>{
   const parent=el.parentElement as HTMLElement;
   const bounds=parent.getBoundingClientRect();
   const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
   let node=walker.nextNode() as Text|null;
   while(node){
     const raw=node.textContent??'';
     for(let i=0;i<raw.length;i++){
       if(!raw[i]?.trim())continue;
       const range=document.createRange();range.setStart(node,i);range.setEnd(node,i+1);
       if(Array.from(range.getClientRects()).some(rect=>rect.right>bounds.right+1))return true;
     }
     node=walker.nextNode() as Text|null;
   }
   return false;
 });
 expect(attacked,'intentional overflow must be discovered by actual Chromium glyph rectangles').toBe(true);
 await span.evaluate((el,style)=>(el as HTMLElement).setAttribute('style',style??''),initialStyle);
 const shot=await stage.screenshot();
 const dir=resolve(process.cwd(),'.artifacts','pr10');
 mkdirSync(dir,{recursive:true});
 const filename=resolve(dir,'t06-source-multiline-chromium.png');
 writeFileSync(filename,shot);
 writeFileSync(resolve(dir,'g05-t06-typography.json'),JSON.stringify({
   scope:'SYNTHETIC_OPERATOR_APPROVED_G1_G3_NOT_REAL_ARCHIVAL_RIGHTS',
   sourceOriginalSha256s:Object.values(authorized.props.media.assets).map((x:any)=>x.originalSha256),
   g4Head:authorized.draft_manifest_sha256,
   fontSha256:authorized.props.media.fontSha256,
   sourceClaimId:excerpt.source_claim_id,originalSourceText:excerpt.text,
   frame:final,excerpt:target,adversarialClippingDetected:attacked,
   screenshotSha256:createHash('sha256').update(shot).digest('hex')},null,2));
});
