import {test,expect} from "@playwright/test";
import {readFileSync} from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
const here=path.dirname(fileURLToPath(import.meta.url));
const fixture=JSON.parse(readFileSync(path.resolve(here,
  "../../../contracts/examples/longform/StoryPackage.longform.synthetic.json"),"utf8"));

test("asset-review: operator choice persists and never auto-approves G3",async({page},testInfo)=>{
  await page.goto("/");
  await page.getByLabel("Project title").fill("Historical asset review");
  await page.getByRole("button",{name:"Create project"}).click();
  await expect(page.getByRole("status")).toContainText("Project creation completed");
  const project=(await page.locator(".topline strong").innerText()).trim();
  const story=structuredClone(fixture);
  story.project.project_id=project;
  story.claims.forEach((c:{critical:boolean})=>{c.critical=false;});
  await page.getByLabel("StoryPackage JSON").fill(JSON.stringify(story));
  await page.getByRole("button",{name:"Import and validate story"}).click();
  await expect(page.getByRole("status")).toContainText("Story import completed");
  await page.getByRole("navigation").getByRole("button",{name:/Historical Assets/}).click();
  await expect(page.getByText("Historical sources · G3")).toBeVisible();
  await expect(page.locator(".asset-studio")).toContainText("ARCHIVE_ASSET_UNRESOLVED");
  await page.getByLabel("Explicit missing-source reason").fill("Need an owned image");
  await page.getByRole("button",{name:"Save explicit choice"}).click();
  await expect(page.locator(".asset-studio").getByRole("status")).toContainText("Save resolution completed");
  await expect(page.locator(".asset-studio")).toContainText("MANUAL_UPLOAD");
  await expect(page.getByRole("button",{name:"Approve complete G3 snapshot"})).toBeDisabled();
  await page.screenshot({path:testInfo.outputPath("g3-manual-choice.png")});
  await page.reload();
  await page.getByLabel("Project ID").fill(project);
  await page.getByRole("button",{name:"Open existing project"}).click();
  await page.getByRole("navigation").getByRole("button",{name:/Historical Assets/}).click();
  await expect(page.getByText("Resolution:")).toContainText("MANUAL_UPLOAD");
  await expect(page.getByRole("button",{name:"Approve complete G3 snapshot"})).toBeDisabled();
});


test("asset-review: zero requirements still needs an explicit G3 decision",async({page},testInfo)=>{
  await page.goto("/");
  await page.getByLabel("Project title").fill("No media editorial");
  await page.getByRole("button",{name:"Create project"}).click();
  await expect(page.getByRole("status")).toContainText("Project creation completed");
  const project=(await page.locator(".topline strong").innerText()).trim();
  const story=structuredClone(fixture);
  story.project.project_id=project;
  story.asset_requirements=[];
  story.sections.forEach((s:{asset_requirement_refs:string[]})=>{s.asset_requirement_refs=[];});
  story.visual_setups.forEach((s:{requirement_refs:string[]})=>{s.requirement_refs=[];});
  story.claims.forEach((c:{critical:boolean})=>{c.critical=false;});
  await page.getByLabel("StoryPackage JSON").fill(JSON.stringify(story));
  await page.getByRole("button",{name:"Import and validate story"}).click();
  await expect(page.getByRole("status")).toContainText("Story import completed");
  await page.getByRole("button",{name:"Approve G1"}).click();
  await expect(page.getByRole("status")).toContainText("G1 approved completed");
  await page.getByRole("navigation").getByRole("button",{name:/Historical Assets/}).click();
  await expect(page.locator(".asset-studio")).toContainText("No asset requirements in this StoryPackage");
  await expect(page.getByRole("button",{name:"Approve complete G3 snapshot"})).toBeEnabled();
  await expect(page.locator(".asset-studio")).toContainText("READY_FOR_REVIEW");
  await page.screenshot({path:testInfo.outputPath("zero-assets-g3-ready.png")});
  await page.getByRole("button",{name:"Approve complete G3 snapshot"}).click();
  await expect(page.locator(".asset-studio").getByRole("status")).toContainText("Approve G3 completed");
  await expect(page.locator(".asset-studio")).toContainText("G3 gate — APPROVED");
  await page.reload();
  await page.getByLabel("Project ID").fill(project);
  await page.getByRole("button",{name:"Open existing project"}).click();
  await page.getByRole("navigation").getByRole("button",{name:/Historical Assets/}).click();
  await expect(page.locator(".asset-studio")).toContainText("G3 gate — APPROVED");
});
