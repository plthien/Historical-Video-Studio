/** Browser navigation helpers for the approved PR13 State A/B UI.
 * These only operate real controls. They never bypass backend gates, approvals,
 * saved settings, or source provenance.
 */
import {expect,type Page} from "@playwright/test";

export async function openExistingProject(page:Page,id:string){
  const all=page.getByRole("button",{name:"All projects"});
  if(await all.count())await all.click();
  await page.getByText("Open by exact Project ID").click();
  await page.locator("#project-lookup").fill(id);
  await page.getByRole("button",{name:"Open ID",exact:true}).click();
  await expect(page.locator(".topline strong")).toContainText(id);
}
export async function selectImportStep(page:Page){
  await page.locator(".flow-steps button").nth(2).click();
  await expect(page.locator("#story-json")).toBeVisible();
}
export async function importStoryFromEditor(page:Page,story:unknown){
  await selectImportStep(page);
  await page.locator("#story-json").fill(JSON.stringify(story));
  await page.getByRole("button",{name:"Validate & import StoryPackage"}).click();
  await expect(page.locator(".sidebar nav button[aria-current=page]")).toContainText("Story review");
}
export async function startNewProject(page:Page,name:string){
  const all=page.getByRole("button",{name:"All projects"});
  if(await all.count())await all.click();
  await page.locator("#new-title").fill(name);
  await page.getByRole("button",{name:"Create project"}).click();
  await expect(page.locator(".flow-steps")).toBeVisible();
  const text=await page.locator(".topline strong").innerText();
  const id=text.split(" · ")[0].trim();
  expect(id).toMatch(/^proj_/);
  return id;
}
