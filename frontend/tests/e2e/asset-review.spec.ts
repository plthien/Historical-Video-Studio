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

  // F03: the UI must display the backend-verified original, not a search thumbnail.
  const png=Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMwSpkGAAH4AS3k7SvZAAAAAElFTkSuQmCC","base64");
  await page.locator(".asset-studio input[type=file]").setInputFiles({
    name:"verified-original.png",mimeType:"image/png",buffer:png
  });
  await page.locator(".asset-studio input[placeholder='Title']").fill("Original media fixture");
  await page.locator(".asset-studio textarea[placeholder='Origin and historical context']").fill("Synthetic context");
  await page.locator(".asset-studio textarea[placeholder='Rights evidence']").fill("Test fixture only");
  await page.getByRole("button",{name:"Upload original candidate"}).click();
  await expect(page.locator(".asset-studio").getByRole("status")).toContainText("Manual upload completed");
  await expect(page.locator(".asset-original-preview")).toBeVisible();
  await expect(page.locator(".asset-original-preview")).toHaveJSProperty("naturalWidth",1);
  await expect(page.locator(".asset-studio")).toContainText("Synthetic context");
  await expect(page.locator(".asset-studio")).toContainText("Test fixture only");
  const requirementSelect=page.getByLabel("Asset requirement");
  const original=await requirementSelect.inputValue();
  const options=await requirementSelect.locator("option").evaluateAll(nodes=>
    nodes.map(n=>(n as HTMLOptionElement).value));
  expect(options.length).toBeGreaterThan(1);
  await page.locator(".asset-studio input[type=checkbox]").first().check();
  await page.getByText("Rights/license evidence (required)").locator("..").locator("textarea").first().fill("Reviewed rights");
  await page.getByText("Period, geography, exactness evidence (required)").locator("..").locator("textarea").first().fill("Reviewed period");
  await page.getByRole("button",{name:"Stage selected for batch"}).click();
  await expect(page.locator(".asset-studio")).toContainText("1 staged;");
  await requirementSelect.selectOption(options.find(value=>value!==original)!);
  await expect(page.locator(".asset-studio")).not.toContainText("1 staged;");
  await page.route("**/original-preview**",route=>route.abort("failed"));
  await requirementSelect.selectOption(original);
  await expect(page.getByRole("alert")).toContainText("Original image could not be loaded");
  await expect(page.getByRole("button",{name:"Retry original preview"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Stage selected for batch"})).toBeDisabled();
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
  story.visual_setups=story.visual_setups.slice(0,1);
  const setup=story.visual_setups[0];
  setup.requirement_refs=[];
  setup.preferred_template="T08";
  const direction=setup.direction;
  direction.asset_slots=[];
  direction.historical_map_requirement_id=null;
  const textId=direction.on_screen_text[0].text_id;
  direction.visual_beats.forEach((beat: {
    focus_ref:string;relationships:unknown[];staging:unknown[];
    continuity:{carry_refs:string[]};
  })=>{
    beat.focus_ref=textId;beat.relationships=[];
    beat.staging=[{ref:textId,operation:"enter",after_ref:null,motion_hint:"none",priority:1}];
    beat.continuity.carry_refs=[];
  });
  direction.reveal_plan.forEach((beat:{target_role:string})=>{beat.target_role="headline";});
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
