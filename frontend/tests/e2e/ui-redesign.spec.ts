import {test,expect} from "@playwright/test";
import {mkdirSync,readFileSync,writeFileSync} from "node:fs";
import path from "node:path";

const output=path.resolve("frontend/.artifacts/ui-redesign");
const fixture=path.resolve("../contracts/examples/visual_cases/StoryPackage.visual_cases.synthetic.json");
const widths=[{width:1366,height:768},{width:1920,height:1080}];

async function measure(page:import("@playwright/test").Page,label:string){
  return page.evaluate(label=>{
    const sid=document.querySelector(".sidebar")?.getBoundingClientRect();
    const c=document.querySelector(".content-container")?.getBoundingClientRect();
    const header=document.querySelector(".topline")?.getBoundingClientRect();
    const buttons=[...document.querySelectorAll("button")].filter(el=>getComputedStyle(el).display!=="none");
    const right=Math.max(0,...buttons.map(el=>el.getBoundingClientRect().right));
    const snapshot={label,viewport:{width:innerWidth,height:innerHeight},
      sidebar_width:sid?.width??null,content_left:c?.left??null,
      header_right:header?.right??null,rightmost_control:right,
      doc_scroll_width:document.documentElement.scrollWidth,
      doc_client_width:document.documentElement.clientWidth,
      horizontal_overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+2,
      layout_version:"PR13_APPROVED_UI_REDESIGN_V2"};
    return snapshot;
  },label);
}
function checkGeometry(m:Awaited<ReturnType<typeof measure>>){
  expect(Math.abs((m.sidebar_width??0)-238)).toBeLessThanOrEqual(2);
  expect(m.content_left).toBeGreaterThanOrEqual(238);
  expect(m.rightmost_control).toBeLessThanOrEqual(m.viewport.width-16);
  expect(m.horizontal_overflow).toBe(false);
}

for(const size of widths){
  test(`PR13 redesigned State A/B real browser geometry ${size.width}x${size.height}`,async({browser})=>{
    mkdirSync(output,{recursive:true});
    const context=await browser.newContext({viewport:size,deviceScaleFactor:1});
    const page=await context.newPage();
    const errors:string[]=[];
    page.on("pageerror",e=>errors.push(String(e)));
    try{
      await page.goto("/");
      await expect(page.getByRole("region",{name:"project-home"})).toBeVisible();
      await expect(page.getByRole("region",{name:"new-project"})).toBeVisible();
      await expect(page.getByRole("region",{name:"recent-projects"})).toBeVisible();
      await expect(page.getByRole("button",{name:/Next valid action.*Complete/})).toHaveCount(0);
      await expect(page.locator(".gateboard")).toHaveCount(0);
      const a=await measure(page,"project-state-a");
      checkGeometry(a);
      await page.screenshot({path:path.join(output,`projects-A-${size.width}.png`),animations:"disabled"});
      const title="V2 maritime history "+size.width;
      await page.locator("#new-title").fill(title);
      await page.getByRole("button",{name:"Create project"}).click();
      await expect(page.locator(".flow-steps")).toBeVisible();
      await expect(page.locator(".gateboard .gate")).toHaveCount(5);
      await expect(page.locator(".topline")).toContainText(title);
      await expect(page.locator("#brief-topic")).toBeVisible();
      await page.locator("#brief-topic").fill("Old maritime trade routes");
      await page.locator("#brief-audience").fill("Adults interested in historical evidence");
      await page.locator("#brief-goals").fill("Treat route maps only as authorized period geometry");
      await page.getByRole("button",{name:"Save settings & continue"}).click();
      await expect(page.locator(".flow-steps button[aria-current=step]")).toContainText("ChatGPT Brief");
      await page.getByRole("button",{name:"Build versioned brief"}).click();
      await expect(page.locator("#brief-preview")).toContainText("StoryPackage.v1");
      const b=await measure(page,"project-state-b");
      checkGeometry(b);
      await page.screenshot({path:path.join(output,`projects-B-${size.width}.png`),animations:"disabled"});
      await page.locator(".flow-steps button").nth(0).click();
      await page.locator("#brief-topic").fill("Edited settings make brief obsolete");
      await page.locator(".flow-steps button").nth(1).click();
      await expect(page.getByText(/OUTDATED BRIEF/)).toBeVisible();
      await expect(page.getByRole("button",{name:"Copy brief"})).toBeDisabled();
      await page.locator(".flow-steps button").nth(0).click();
      await page.getByRole("button",{name:"Save settings & continue"}).click();
      await page.getByRole("button",{name:"Build versioned brief"}).click();
      await page.getByRole("button",{name:"Continue to import"}).click();
      const source=JSON.parse(readFileSync(fixture,"utf8")) as {project:{project_id:string}};
      const id=await page.locator(".flow-context .provenance-line").first().textContent();
      const match=id?.match(/proj_[a-zA-Z0-9_-]+/);
      expect(match).toBeTruthy();
      source.project.project_id=match![0];
      await page.locator("#story-json").fill(JSON.stringify(source));
      await page.getByRole("button",{name:"Validate & import StoryPackage"}).click();
      await expect(page.locator(".sidebar nav button[aria-current=page]")).toContainText("Story review");
      await expect(page.getByText(/Historical claims/)).toBeVisible();
      const s=await measure(page,"story-g1");
      checkGeometry(s);
      await page.screenshot({path:path.join(output,`story-G1-${size.width}.png`),animations:"disabled"});
      const otherStates=[] as Awaited<ReturnType<typeof measure>>[];
      for(const [index,workspace] of [
        [2,"voice-G2"],[3,"assets-G3"],[4,"storyboard-G4"],[5,"delivery-G5"]
      ] as const){
        await page.locator(".sidebar nav button").nth(index).click();
        await expect(page.locator(".sidebar nav button").nth(index)).toHaveAttribute("aria-current","page");
        await expect(page.locator(".content").first()).toBeVisible();
        const geometry=await measure(page,workspace);
        checkGeometry(geometry);
        otherStates.push(geometry);
        await page.screenshot({path:path.join(output,`${workspace}-${size.width}.png`),animations:"disabled"});
      }
      writeFileSync(path.join(output,`geometry-${size.width}.json`),
        JSON.stringify({design_authority:"PR13_APPROVED_UI_REDESIGN_V2",source:"REAL_COMPILED_CHROMIUM",
          measured:[a,b,s,...otherStates],errors,
          media_evidence:"BLOCKED_UNAPPROVED_FIXTURE: screenshots are genuine blocked G2–G5 workspaces, not populated media acceptance",
          human_visual_review:"NOT_RUN",synthetic_fixture:"SYNTHETIC_TEST_ONLY"},null,2));
      expect(errors).toEqual([]);
    }finally{await context.close();}
  });
}
