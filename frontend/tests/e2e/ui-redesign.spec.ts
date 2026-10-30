import {test,expect} from "@playwright/test";
import {mkdirSync,readFileSync,writeFileSync} from "node:fs";
import path from "node:path";
import {execFileSync} from "node:child_process";
import {apiBase,openExistingProject} from "./project-workflow-helper";

const output=path.resolve(".artifacts/ui-redesign");
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
    await context.grantPermissions(["clipboard-read","clipboard-write"]);
    const page=await context.newPage();
    const errors:string[]=[];
    const failedRequests:string[]=[];
    page.on("pageerror",e=>errors.push(String(e)));
    page.on("requestfailed",r=>failedRequests.push(`${r.method()} ${r.url()} ${r.failure()?.errorText}`));
    try{
      await page.goto("/");
      const build=await page.request.get("/build-info.json");
      expect(build.ok()).toBe(true);
      const info=await build.json() as {schema_version:string;source_commit:string;bundle_sha256:string;input_sha256:string};
      const head=execFileSync("git",["rev-parse","HEAD"],{cwd:path.resolve("..")}).toString().trim();
      expect(info.schema_version).toBe("HVSFrontendBuild.v1");
      expect(info.source_commit).toBe(head);
      expect(info.bundle_sha256).toMatch(/^[0-9a-f]{64}$/);
      const backendProbe=await page.evaluate(async base=>{
        const health=await fetch(base+"/health");
        const projects=await fetch(base+"/projects");
        return {health_status:health.status,health:await health.json(),
          projects_status:projects.status,projects:await projects.json()};
      },apiBase);
      expect(backendProbe.health_status).toBe(200);
      expect(backendProbe.health).toMatchObject({status:"ready",scope:"A1"});
      expect(backendProbe.projects_status).toBe(200);
      expect(Array.isArray(backendProbe.projects)).toBe(true);
      writeFileSync(path.join(output,`source-head-${size.width}.json`),
        JSON.stringify({design_authority:"PR13_APPROVED_UI_REDESIGN_V2",head,
          base_sha:"d368088dba5713b3b4b51b635f585585bd8baf9a",
          frontend_bundle_sha256:info.bundle_sha256,
          frontend_input_sha256:info.input_sha256,
          packaged_build_commit:info.source_commit,api_origin:apiBase,
          preview_url:page.url(),backend_health_url:apiBase+"/health",
          health_status:backendProbe.health_status,projects_status:backendProbe.projects_status},null,2));

      await expect(page.getByRole("region",{name:"project-home"})).toBeVisible();
      await expect(page.getByRole("region",{name:"new-project"})).toBeVisible();
      await expect(page.getByRole("region",{name:"recent-projects"})).toBeVisible();
      await expect(page.getByRole("button",{name:/Next valid action.*Complete/})).toHaveCount(0);
      await expect(page.locator(".gateboard")).toHaveCount(0);
      const a=await measure(page,"project-state-a");
      checkGeometry(a);
      await page.screenshot({path:path.join(output,`projects-A-${size.width}.png`),animations:"disabled"});
      const title="V3 maritime history "+size.width;
      await page.locator("#new-title").fill(title);
      const createdResponse=page.waitForResponse(response=>
        response.url()===apiBase+"/projects"&&response.request().method()==="POST");
      await page.getByRole("button",{name:"Create project"}).click();
      const created=await createdResponse;
      expect(created.status()).toBe(201);
      const createdBody=await created.json() as {project_id:string,project_revision:number};
      expect(createdBody.project_id).toMatch(/^proj_/);
      expect(createdBody.project_revision).toBe(0);
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
      await expect(page.locator("#brief-preview")).toHaveValue(/StoryPackage.v1/);
      await expect(page.getByText(/HVS-EXTERNAL-STORY-BRIEF\.v3 · CURRENT/)).toBeVisible();
      const preview=await page.locator("#brief-preview").inputValue();
      await page.getByRole("button",{name:"Copy brief"}).click();
      // Windows clipboard transport canonicalizes LF to CRLF; the prompt text is otherwise exact.
      expect((await page.evaluate(()=>navigator.clipboard.readText())).replace(/\r\n/g,"\n")).toBe(preview);
      const [download]=await Promise.all([
        page.waitForEvent("download"),
        page.getByRole("button",{name:"Download .md"}).click(),
      ]);
      expect(readFileSync(await download.path(),"utf8")).toBe(preview);
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
      expect(match![0]).toBe(createdBody.project_id);
      await page.locator("#story-json").fill("{");
      await page.getByRole("button",{name:"Validate & import StoryPackage"}).click();
      await expect(page.getByRole("alert")).toContainText("JSON_SYNTAX_INVALID");
      source.project.project_id=match![0];
      await page.locator("#story-json").fill(JSON.stringify(source));
      await page.getByRole("button",{name:"Validate & import StoryPackage"}).click();
      await expect(page.locator(".sidebar nav button[aria-current=page]")).toContainText("Story review");
      await expect(page.getByText(/Historical claims/)).toBeVisible();
      const s=await measure(page,"story-g1");
      checkGeometry(s);
      await page.screenshot({path:path.join(output,`story-G1-${size.width}.png`),animations:"disabled"});
      const revisionBeforeReload=await page.locator(".topline strong").innerText();
      await page.reload();
      await openExistingProject(page,createdBody.project_id);
      expect(await page.locator(".topline strong").innerText()).toBe(revisionBeforeReload);
      await page.getByRole("navigation").getByRole("button",{name:"Story review (G1)",exact:true}).click();
      await expect(page.getByText(/Historical claims/)).toBeVisible();
      writeFileSync(path.join(output,`production-handshake-${size.width}.json`),JSON.stringify({
        source_commit:info.source_commit,bundle_sha256:info.bundle_sha256,input_sha256:info.input_sha256,
        preview_url:page.url(),api_origin:apiBase,health_status:backendProbe.health_status,
        projects_status:backendProbe.projects_status,create_status:created.status(),
        project_id:createdBody.project_id,created_revision:createdBody.project_revision,
        reopened_revision_text:revisionBeforeReload
      },null,2));
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
          measured:[a,b,s,...otherStates],errors,failedRequests,
          media_evidence:"BLOCKED_UNAPPROVED_FIXTURE: screenshots are genuine blocked G2–G5 workspaces, not populated media acceptance",
          human_visual_review:"NOT_RUN",synthetic_fixture:"SYNTHETIC_TEST_ONLY"},null,2));
      writeFileSync(path.join(output,`visual-review-ledger-${size.width}.json`),
        JSON.stringify({design_authority:"PR13_APPROVED_UI_REDESIGN_V2",
          measurement:"BROWSER_BOUNDING_BOXES_PASS_SUBJECT_TO_TEST",
          screenshot_count:7,
          visual_human_review:"NOT_RUN",
          actual_g4_player:"BLOCKED_UNAPPROVED_FIXTURE",
          actual_g5_media:"BLOCKED_UNAPPROVED_FIXTURE",
          verdict:"FAIL_UNTIL_POPULATED_REAL_PLAYER_AND_MEDIA_REVIEW",
          notes:"Screenshots show real SQLite project and truthful blocked downstream states; they are not fake populated media."},null,2));
      expect(errors).toEqual([]);
      expect(failedRequests).toEqual([]);
    }finally{await context.close();}
  });
}

test("project creation stays truthful when the canonical backend request is unavailable",async({page,request})=>{
  const beforeResponse=await request.get(apiBase+"/projects");
  expect(beforeResponse.status()).toBe(200);
  const before=await beforeResponse.json() as unknown[];
  await page.goto("/");
  await expect(page.getByRole("region",{name:"new-project"})).toBeVisible();
  await page.route(apiBase+"/projects",async route=>{
    if(route.request().method()==="POST")await route.abort("connectionfailed");
    else await route.continue();
  });
  await page.locator("#new-title").fill("Must not become a fake project");
  await page.getByRole("button",{name:"Create project"}).click();
  await expect(page.getByRole("alert")).toContainText("Failed to fetch");
  await expect(page.getByRole("region",{name:"project-home"})).toBeVisible();
  await expect(page.locator(".gateboard")).toHaveCount(0);
  await page.unroute(apiBase+"/projects");
  const afterResponse=await request.get(apiBase+"/projects");
  expect(afterResponse.status()).toBe(200);
  expect((await afterResponse.json() as unknown[]).length).toBe(before.length);
});
