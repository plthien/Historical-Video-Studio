import {test,expect} from '@playwright/test';
import {PNG} from 'pngjs';

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
 await page.getByRole('button',{name:'Load real read-only Remotion Player'}).click();
 await expect(page.getByLabel('Read-only local Remotion Player')).toBeVisible({timeout:30000});
 await expect(page.getByText(/G4 DRAFT · VIEW ONLY/)).toBeVisible();
 // A visible Player wrapper or updated seek input is NOT a rendered frame.
 const stage=page.getByTestId('player-stage');
 await expect(stage.locator('[data-global-frame="0"][data-scene-id]')).toBeVisible({timeout:30000});
 const first=PNG.sync.read(await stage.screenshot());
 const samples=new Set<number>();
 for(let i=0;i<first.data.length;i+=128)samples.add(first.data[i]);
 expect(samples.size,'the actual Player frame is not blank').toBeGreaterThan(3);
 await page.getByLabel('Seek exact frame').fill('10');
 await expect(stage.locator('[data-global-frame="10"][data-scene-id]')).toBeVisible({timeout:10000});
 const beforeFocus=PNG.sync.read(await stage.screenshot());
 expect(fatalErrors,'browser Player must not throw React hook or runtime errors').toEqual([]);
 const focus=page.getByLabel('Authorized focus movement');
 const originalFocus=await focus.inputValue();
 const targetFocus=originalFocus==='overview_to_detail'?'detail_to_overview':'overview_to_detail';
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
 expect(fatalErrors,'no fatal browser errors during edit/reload').toEqual([]);
});
