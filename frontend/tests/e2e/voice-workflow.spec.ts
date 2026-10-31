import {test,expect} from "@playwright/test";
import {startNewProject,importStoryFromEditor,openExistingProject} from "./project-workflow-helper";
import {readFileSync} from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
const root=path.dirname(fileURLToPath(import.meta.url));
const full=JSON.parse(readFileSync(path.resolve(root,
  "../../../contracts/examples/longform/StoryPackage.longform.synthetic.json"),"utf8"));

test("voice-workflow: two selected sections, one G2 approval and truthful alignment failure",async({page},info)=>{
  await page.goto("/");
  const project=await startNewProject(page,"A2 voice real-backend mocked-boundary check");
  const story=structuredClone(full);
  story.project.project_id=project;
  story.sections=story.sections.slice(0,2);
  story.visual_setups=story.visual_setups.slice(0,4);
  story.claims.forEach((c:{critical:boolean})=>{c.critical=false;});
  await importStoryFromEditor(page,story);
  await expect(page.getByRole("button",{name:"Approve G1"})).toBeEnabled();
  await page.getByRole("button",{name:"Approve G1"}).click();
  await expect(page.getByRole("status")).toContainText("G1 approved completed");
  await page.getByRole("navigation").getByRole("button",{name:/Voice Studio/i}).click();
  for(const section of ["sec_001","sec_002"]){
    await page.locator(".voice-section-rail button").filter({hasText:section}).click();
    const box=page.getByRole("article",{name:"Voice section "+section});
    await box.getByLabel("Voice ID "+section).fill("am_adam");
    await box.getByLabel("Speed "+section).fill("1.0");
    await box.getByRole("button",{name:"Regenerate"}).click();
    await expect(box.getByText(/Selected am_adam/)).toBeVisible({timeout:45000});
    await expect(box.locator("audio:visible")).toHaveCount(1);
  }
  const originalViewport=page.viewportSize()!;
  for(const viewport of [{width:1366,height:768},{width:1920,height:1080}]){
    await page.setViewportSize(viewport);
    await expect(page.locator(".voice-section-main audio:visible")).toHaveCount(1);
    await page.screenshot({path:info.outputPath(`pr13-g2-populated-selected-audio-${viewport.width}.png`),animations:"disabled"});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+2)).toBe(true);
  }
  await page.setViewportSize(originalViewport);
  await expect(page.getByRole("button",{name:"Approve G2"})).toBeEnabled({timeout:30000});
  await page.getByRole("button",{name:"Approve G2"}).click();
  await expect(page.getByText(/Final WAV: \d+ samples/)).toBeVisible({timeout:60000});
  await expect(page.locator(".voice-studio")).toContainText("PROVIDER_CREDENTIALS_MISSING",{timeout:60000});
  await expect(page.getByText(/G4 dependency: BLOCKED/)).toBeVisible();
  await expect(page.getByRole("button",{name:"Approve G2"})).toBeDisabled();
  await expect(page.getByRole("button",{name:/Assemble final WAV|^Align final WAV$/})).toHaveCount(0);
  await page.screenshot({path:info.outputPath("voice-g2-alignment-blocked.png")});
  await page.reload();
  await openExistingProject(page,project);
  await page.getByRole("navigation").getByRole("button",{name:/Voice Studio/i}).click();
  await expect(page.getByRole("article",{name:"Voice section sec_001"}).getByText(/Selected am_adam/)).toBeVisible();
  await expect(page.locator(".voice-studio")).toContainText("PROVIDER_CREDENTIALS_MISSING");
});
