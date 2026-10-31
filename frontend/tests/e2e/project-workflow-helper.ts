/** Browser navigation helpers for the approved PR13 State A/B UI.
 * These only operate real controls. They never bypass backend gates, approvals,
 * saved settings, or source provenance.
 */
import {expect,type Page} from "@playwright/test";
import {readFileSync} from "node:fs";

const portProfile=JSON.parse(readFileSync(new URL("../../../config/ports.json",import.meta.url),"utf8")) as {
  backend_port:unknown
};
const canonicalPort=Number(portProfile.backend_port);
if(!Number.isInteger(canonicalPort)||canonicalPort<1||canonicalPort>65535)
  throw new Error("Invalid backend_port in config/ports.json");
const apiPort=process.env.HVS_E2E_API_PORT??
  (process.env.HVS_PARITY_PRODUCTION==="1"?String(canonicalPort):"8000");
if(!/^\d+$/.test(apiPort)||Number(apiPort)<1||Number(apiPort)>65535)
  throw new Error("Invalid HVS_E2E_API_PORT");
export const apiBase=`http://127.0.0.1:${apiPort}/api/v1`;

export async function openExistingProject(page:Page,id:string){
  // On reload, sessionStorage restores the selected project asynchronously.
  // If an ID is pending restoration, wait for that hydration before using the
  // selected-project control. Otherwise the transient landing form can vanish
  // between visibility and fill.
  await page.getByRole("navigation").getByRole("button",{name:"Project & ChatGPT import",exact:true}).click();
  const all=page.getByRole("button",{name:"All projects"});
  const lookup=page.locator("#project-lookup");
  const restoring=await page.evaluate(()=>sessionStorage.getItem("hvs.activeProjectId")!==null);
  if(restoring){await expect(all).toBeVisible();await all.click();}
  else if(await all.isVisible())await all.click();
  const details=page.locator("details").filter({has:lookup});
  await expect(details).toBeAttached();
  if(!(await details.evaluate(node=>(node as HTMLDetailsElement).open)))await details.locator("summary").click();
  await expect(lookup).toBeVisible();
  await lookup.fill(id);
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
