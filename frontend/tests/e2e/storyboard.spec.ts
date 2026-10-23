import {test,expect} from '@playwright/test';

test('storyboard-editor uses real persisted G4 scenes and native read-only Player',async({page})=>{
 test.skip(process.env.HVS_B2_FIXTURE!=='1','Requires native Windows controlled SQLite G4, never mocked HTTP fixtures');
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
 await page.getByLabel('Seek exact frame').fill('10');
 await expect(page.getByLabel('Seek exact frame')).toHaveValue('10');
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
 await page.getByRole('button',{name:'Reload persisted draft'}).click();
 await expect(variant).toHaveValue(target);
 await expect(layerX).toHaveValue(String(oldX+1));
});
