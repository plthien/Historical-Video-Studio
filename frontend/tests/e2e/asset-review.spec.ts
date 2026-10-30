import {apiBase,startNewProject,openExistingProject,importStoryFromEditor,selectImportStep} from "./project-workflow-helper";
import {test,expect} from "@playwright/test";
import {readFileSync} from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {execFileSync} from "node:child_process";
const here=path.dirname(fileURLToPath(import.meta.url));
const fixture=JSON.parse(readFileSync(path.resolve(here,
  "../../../contracts/examples/longform/StoryPackage.longform.synthetic.json"),"utf8"));
const isolatedFlow=process.env.HVS_FULL_FLOW_CONFIG
  ?JSON.parse(readFileSync(path.resolve(here,"../..",process.env.HVS_FULL_FLOW_CONFIG),"utf8")) as {db:string,artifactRoot:string}
  :null;

test("asset-review: operator choice persists and never auto-approves G3",async({page},testInfo)=>{
  await page.goto("/");
  const project=await startNewProject(page,"Historical asset review");
  const story=structuredClone(fixture);
  story.project.project_id=project;
  story.claims.forEach((c:{critical:boolean})=>{c.critical=false;});
  await importStoryFromEditor(page,story);
  await page.getByRole("navigation").getByRole("button",{name:/Historical Assets/}).click();
  await expect(page.getByText("Historical sources · G3")).toBeVisible();
  await expect(page.locator(".asset-studio")).toContainText("ARCHIVE_ASSET_UNRESOLVED");
  await page.getByLabel("Explicit missing-source reason").fill("Need an owned image");
  await page.getByRole("button",{name:"Save explicit choice"}).click();
  await expect(page.locator(".asset-studio .notice.success")).toContainText("Save resolution completed");
  await expect(page.locator(".asset-studio")).toContainText("MANUAL_UPLOAD");
  await expect(page.getByRole("button",{name:"Approve complete G3 snapshot"})).toBeDisabled();
  await page.screenshot({path:testInfo.outputPath("g3-manual-choice.png")});
  await page.reload();
  await openExistingProject(page,project);
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
  await expect(page.locator(".asset-studio .notice.success")).toContainText("Manual upload completed");
  await expect(page.locator(".asset-original-preview")).toBeVisible();
  await expect(page.locator(".asset-original-preview")).toHaveJSProperty("naturalWidth",1);
  const article=page.locator(".asset-studio article.claim").filter({hasText:"Original media fixture"});
  const originalViewport=page.viewportSize()!;
  for(const viewport of [{width:1366,height:768},{width:1920,height:1080}]){
    await page.setViewportSize(viewport);
    await expect(page.locator(".asset-original-preview")).toBeVisible();
    await article.scrollIntoViewIfNeeded();
    await page.screenshot({path:testInfo.outputPath(`pr13-g3-populated-approved-original-candidate-${viewport.width}.png`),animations:"disabled"});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+2)).toBe(true);
  }
  await page.setViewportSize(originalViewport);

  await expect(page.locator(".asset-studio")).toContainText("Synthetic context");
  await expect(page.locator(".asset-studio")).toContainText("Test fixture only");
  const requirementSelect=page.getByLabel("Asset requirement");
  const original=await requirementSelect.inputValue();
  const options=await requirementSelect.locator("option").evaluateAll(nodes=>
    nodes.map(n=>(n as HTMLOptionElement).value));
  expect(options.length).toBeGreaterThan(1);
  await page.locator(".asset-studio input[type=checkbox]").first().check();
  await article.locator("textarea").nth(0).fill("Reviewed rights");
  await article.locator("textarea").nth(1).fill("Reviewed period");
  await page.getByRole("button",{name:"Stage selected for batch"}).click();
  await expect(page.locator(".asset-studio")).toContainText("1 staged;");
  const second=options.find(value=>value!==original)!;
  await requirementSelect.selectOption(second);
  // C01-A/B: navigation never discards A's exact review draft.
  await expect(page.locator(".asset-studio")).toContainText("1 staged;");
  await page.getByLabel("Explicit missing-source reason").fill("Second source requires an owned image");
  await page.getByRole("button",{name:"Save explicit choice"}).click();
  await expect(page.locator(".asset-studio .notice.success")).toContainText("Save resolution completed");
  await expect(page.locator(".asset-studio")).toContainText("1 staged;");
  await page.locator(".asset-studio input[type=file]").setInputFiles({
    name:"second-original.png",mimeType:"image/png",buffer:png
  });
  await page.locator(".asset-studio input[placeholder='Title']").fill("Second original");
  await page.locator(".asset-studio textarea[placeholder='Origin and historical context']").fill("Second period");
  await page.locator(".asset-studio textarea[placeholder='Rights evidence']").fill("Separate license");
  await page.getByRole("button",{name:"Upload original candidate"}).click();
  await expect(page.locator(".asset-studio .notice.success")).toContainText("Manual upload completed");
  const secondArticle=page.locator(".asset-studio article.claim").filter({hasText:"Second original"});
  await expect(secondArticle.locator(".asset-original-preview")).toHaveJSProperty("naturalWidth",1);
  await secondArticle.locator("input[type=checkbox]").check();
  await secondArticle.locator("textarea").nth(0).fill("Second reviewed rights");
  await secondArticle.locator("textarea").nth(1).fill("Second reviewed period");
  await page.getByRole("button",{name:"Stage selected for batch"}).click();
  await expect(page.locator(".asset-studio")).toContainText("2 staged;");
  const payloads:unknown[]=[];
  page.on("request",req=>{
    if(req.url().includes("/assets/batch-approve") && req.method()==="POST")
      payloads.push(req.postDataJSON());
  });
  await page.getByRole("button",{name:/Approve 2 selected\/staged source/}).click();
  await expect(page.locator(".asset-studio .notice.success")).toContainText("Approved 2 requirement(s)");
  expect(payloads).toHaveLength(1);
  const batch=payloads[0] as {reviews:{requirement_id:string}[]};
  expect(new Set(batch.reviews.map(r=>r.requirement_id))).toEqual(new Set([original,second]));
  await expect(page.locator(".asset-studio")).not.toContainText("2 staged;");
  await expect(page.getByRole("button",{name:"Approve complete G3 snapshot"})).toBeDisabled();
  // C01-C/G: repeated staging has one slot per requirement, manual removal works,
  // and changing only A's resolution prunes A while keeping still-valid B.
  await secondArticle.locator("input[type=checkbox]").check();
  await secondArticle.locator("textarea").nth(0).fill("Second reviewed rights");
  await secondArticle.locator("textarea").nth(1).fill("Second reviewed period");
  await page.getByRole("button",{name:"Stage selected for batch"}).click();
  await requirementSelect.selectOption(original);
  const firstArticle=page.locator(".asset-studio article.claim").filter({hasText:"Original media fixture"});
  await expect(firstArticle.locator(".asset-original-preview")).toHaveJSProperty("naturalWidth",1);
  await firstArticle.locator("input[type=checkbox]").check();
  await firstArticle.locator("textarea").nth(0).fill("Reviewed rights again");
  await firstArticle.locator("textarea").nth(1).fill("Reviewed period again");
  await page.getByRole("button",{name:"Stage selected for batch"}).click();
  await expect(page.locator(".asset-studio")).toContainText("2 staged;");
  await page.getByRole("button",{name:"Remove staged "+original}).click();
  await expect(page.locator(".asset-studio")).toContainText("1 staged;");
  await firstArticle.locator("input[type=checkbox]").check();
  await firstArticle.locator("textarea").nth(0).fill("Reviewed rights again");
  await firstArticle.locator("textarea").nth(1).fill("Reviewed period again");
  await page.getByRole("button",{name:"Stage selected for batch"}).click();
  await expect(page.locator(".asset-studio")).toContainText("2 staged;");
  await page.getByLabel("Operator choice").selectOption("MANAGED_FALLBACK");
  await page.getByRole("button",{name:"Save explicit choice"}).click();
  await expect(page.locator(".asset-studio").getByRole("alert")).toContainText("Outdated staged review");
  await expect(page.locator(".asset-studio")).toContainText("1 staged;");
  await expect(page.getByRole("button",{name:"Remove staged "+original})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Remove staged "+second})).toBeVisible();
  // No preview may be treated as visually reviewed if its bytes fail to load.
  await page.route("**/original-preview**",route=>route.abort("failed"));
  await requirementSelect.selectOption(original);
  await expect(page.locator(".asset-studio").getByText("Original image could not be loaded.",{exact:false})).toBeVisible();
  await expect(page.getByRole("button",{name:"Retry original preview"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Stage selected for batch"})).toBeDisabled();
  await expect(page.getByRole("button",{name:"Approve complete G3 snapshot"})).toBeDisabled();
});


test("asset-review: zero requirements still needs an explicit G3 decision",async({page},testInfo)=>{
  await page.goto("/");
  const project=await startNewProject(page,"No media editorial");
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
  await importStoryFromEditor(page,story);
  await page.getByRole("button",{name:"Approve G1"}).click();
  await expect(page.getByRole("status")).toContainText("G1 approved completed");
  await page.getByRole("navigation").getByRole("button",{name:/Historical Assets/}).click();
  await expect(page.locator(".asset-studio")).toContainText("No asset requirements in this StoryPackage");
  await expect(page.getByRole("button",{name:"Approve complete G3 snapshot"})).toBeEnabled();
  await expect(page.locator(".asset-studio")).toContainText("READY_FOR_REVIEW");
  await page.screenshot({path:testInfo.outputPath("zero-assets-g3-ready.png")});
  await page.getByRole("button",{name:"Approve complete G3 snapshot"}).click();
  await expect(page.locator(".asset-studio .notice.success")).toContainText("Approve G3 completed");
  await expect(page.locator(".asset-studio")).toContainText("G3 gate — APPROVED");
  await page.reload();
  await openExistingProject(page,project);
  await page.getByRole("navigation").getByRole("button",{name:/Historical Assets/}).click();
  await expect(page.locator(".asset-studio")).toContainText("G3 gate — APPROVED");
});


// V4: small shared local-server fixture for independent scope/race/conflict evidence.
const baseApi=process.env.HVS_B3_FIXTURE==="1"?"http://127.0.0.1:8011/api/v1":apiBase;
const tinyPng=Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMwSpkGAAH4AS3k7SvZAAAAAElFTkSuQmCC","base64");
async function createAssetProject(page: import("@playwright/test").Page,title:string,initialVisit=true){
  if(initialVisit)await page.goto("/");
  const previousId=(await page.locator(".topline strong").count())?
    (await page.locator(".topline strong").innerText()).split(" · ")[0]:"";
  const id=await startNewProject(page,title);
  if(previousId)expect(id).not.toBe(previousId);
  const story=structuredClone(fixture);
  story.project.project_id=id;
  story.claims.forEach((c:{critical:boolean})=>{c.critical=false});
  await importStoryFromEditor(page,story);
  await page.getByRole("navigation").getByRole("button",{name:/Historical Assets/}).click();
  await expect(page.getByLabel("Asset requirement")).toBeVisible();
  await expect.poll(()=>page.getByLabel("Asset requirement").locator("option").count()).toBeGreaterThan(1);
  const options=await page.getByLabel("Asset requirement").locator("option")
    .evaluateAll(nodes=>nodes.map(node=>(node as HTMLOptionElement).value));
  return {id,story,requirements:options};
}
async function stageVerified(page:import("@playwright/test").Page,rid:string,title:string) {
  await page.getByLabel("Asset requirement").selectOption(rid);
  await page.getByLabel("Explicit missing-source reason").fill("Verified rights for "+title);
  await page.getByRole("button",{name:"Save explicit choice"}).click();
  await expect(page.locator(".asset-studio .notice.success")).toContainText("Save resolution completed");
  await page.locator(".asset-studio input[type=file]").setInputFiles({
    name:title.replaceAll(" ","-")+".png",mimeType:"image/png",buffer:tinyPng
  });
  await page.locator(".asset-studio input[placeholder='Title']").fill(title);
  await page.locator(".asset-studio textarea[placeholder='Origin and historical context']").fill("Synthetic historical suitability");
  await page.locator(".asset-studio textarea[placeholder='Rights evidence']").fill("Synthetic license check");
  await page.getByRole("button",{name:"Upload original candidate"}).click();
  await expect(page.locator(".asset-studio .notice.success")).toContainText("Manual upload completed");
  const article=page.locator(".asset-studio article.claim").filter({hasText:title});
  await expect(article.locator(".asset-original-preview")).toHaveJSProperty("naturalWidth",1);
  await article.locator("input[type=checkbox]").check();
  await article.locator("textarea").nth(0).fill("Explicit license review for "+title);
  await article.locator("textarea").nth(1).fill("Explicit period review for "+title);
  await page.getByRole("button",{name:"Stage selected for batch"}).click();
  await expect(page.getByRole("button",{name:"Remove staged "+rid})).toBeVisible();
}
async function assetState(page:import("@playwright/test").Page,id:string) {
  const reply=await page.request.get(baseApi+"/projects/"+id+"/assets/requirements");
  expect(reply.ok()).toBeTruthy();
  return reply.json() as Promise<{project_revision:number;requirements:{
    requirement_id:string;approved_asset_id:string|null;approval_record_id:string|null}[]}>;
}
async function incrementClaimRevision(page:import("@playwright/test").Page,id:string,tag:string){
  const current=await assetState(page,id);
  const response=await page.request.post(baseApi+"/projects/"+id+"/story/claims/claim_001/review",{
    headers:{"Idempotency-Key":crypto.randomUUID()},
    data:{expected_revision:current.project_revision,status:"REVIEWED",
      evidence_note:"External concurrency "+tag,source_url:null}});
  expect(response.status(),await response.text()).toBe(200);
}

function approvalLedger(projectId:string) {
  const root=path.resolve(here,"../../..");
  const fixtureDb=path.join(root,"renderer",".artifacts","approved-player-test","g4.sqlite");
  const database=isolatedFlow?.db??(process.env.HVS_B2_FIXTURE==="1"?fixtureDb:path.join(root,"frontend",".e2e-data","state.sqlite"));
  const script=[
    "import json,sqlite3,sys",
    "con=sqlite3.connect(sys.argv[2])",
    "pid=sys.argv[1]",
    "heads=con.execute('SELECT requirement_id,approval_id FROM asset_approval_heads WHERE project_id=? ORDER BY requirement_id',(pid,)).fetchall()",
    "events=con.execute('SELECT requirement_id,approval_id FROM asset_approval_events WHERE project_id=? ORDER BY requirement_id',(pid,)).fetchall()",
    "print(json.dumps({'heads':heads,'events':events}))"
  ].join("\n");
  const result=execFileSync(path.join(root,".venv","Scripts","python.exe"),
    ["-c",script,projectId,database],{cwd:root,encoding:"utf8"});
  return JSON.parse(result.trim()) as {heads:[string,string][];events:[string,string][]};
}

// C01-B/D: normal in-place refresh and true P -> Q project isolation.
test("asset-review V4: refresh preserves valid draft, second project cannot see it",async({page})=>{
  const P=await createAssetProject(page,"V4 project P isolated");
  const A=P.requirements[0];
  await stageVerified(page,A,"P-only original");
  const own=await page.request.get(baseApi+"/projects/"+P.id+"/assets/"+A+"/candidates");
  const ownerCandidate=(await own.json()).candidates.find((c:{title:string})=>c.title==="P-only original");
  expect(ownerCandidate.original_sha256).toBeTruthy();
  await page.getByLabel("Asset requirement").selectOption(P.requirements[1]);
  await page.getByLabel("Asset requirement").selectOption(A);
  await page.getByRole("button",{name:"Refresh project"}).click();
  await expect(page.getByRole("button",{name:"Remove staged "+A})).toBeVisible();
  await incrementClaimRevision(page,P.id,"unrelated");
  await page.getByRole("button",{name:"Refresh project"}).click();
  await expect(page.getByRole("button",{name:"Remove staged "+A})).toBeVisible();
  const Q=await createAssetProject(page,"V4 project Q isolated",false);
  expect(Q.id).not.toEqual(P.id);
  expect(Q.requirements).toContain(A); // Intentionally overlapping canonical requirement IDs.
  await expect(page.getByRole("button",{name:"Remove staged "+A})).toHaveCount(0);
  await expect(page.locator(".asset-studio")).not.toContainText("P-only original");
  const qResult=await page.request.get(baseApi+"/projects/"+Q.id+"/assets/"+A+"/candidates");
  expect((await qResult.json()).candidates).toHaveLength(0);
  expect((await assetState(page,P.id)).requirements.every(r=>r.approval_record_id===null)).toBe(true);
  expect((await assetState(page,Q.id)).requirements.every(r=>r.approval_record_id===null)).toBe(true);
  expect(approvalLedger(P.id)).toEqual({heads:[],events:[]});
  expect(approvalLedger(Q.id)).toEqual({heads:[],events:[]});
  const attempted:unknown[]=[];
  page.on("request",request=>{if(request.url().includes("/assets/batch-approve"))attempted.push(request.postDataJSON())});
  await expect(page.getByRole("button",{name:/Approve \d+ selected\/staged source/})).toBeDisabled();
  expect(attempted).toHaveLength(0);
});

// C01-E: a late candidate response for A must not replace B's actual displayed original.
test("asset-review V4: out-of-order A candidate response cannot overwrite selected B",async({page})=>{
  const P=await createAssetProject(page,"V4 async candidates");
  const [A,B]=P.requirements;
  await stageVerified(page,A,"Async source A");
  await stageVerified(page,B,"Async source B");
  const aJson=await (await page.request.get(baseApi+"/projects/"+P.id+"/assets/"+A+"/candidates")).json();
  const bJson=await (await page.request.get(baseApi+"/projects/"+P.id+"/assets/"+B+"/candidates")).json();
  const idA=aJson.candidates.find((c:{title:string})=>c.title==="Async source A").candidate_id as string;
  const idB=bJson.candidates.find((c:{title:string})=>c.title==="Async source B").candidate_id as string;
  expect(idA).not.toBe(idB);
  let letAProceed=()=>{};
  let signalAEntered=()=>{};
  const holdA=new Promise<void>(resolve=>{letAProceed=resolve});
  const aEntered=new Promise<void>(resolve=>{signalAEntered=resolve});
  await page.route("**/assets/"+A+"/candidates",async route=>{
    signalAEntered();
    await holdA;
    await route.continue();
  });
  const select=page.getByLabel("Asset requirement");
  // Start the delayed A request only after the route has been installed.
  await select.selectOption(A);
  await aEntered;
  await select.selectOption(B);
  await expect(page.locator(".asset-studio article.claim").filter({hasText:"Async source B"})).toBeVisible();
  const releasedA=page.waitForResponse(r=>r.url().includes("/assets/"+A+"/candidates")&&r.request().method()==="GET");
  letAProceed();
  await releasedA; // assert AFTER the delayed response reached the browser.
  await expect(page.getByAltText("Verified original candidate "+idA)).toHaveCount(0);
  await expect(page.getByAltText("Verified original candidate "+idB)).toBeVisible();
  await expect(page.locator(".asset-studio article.claim").filter({hasText:"Async source A"})).toHaveCount(0);
  await expect(select).toHaveValue(B);
  await expect(page.locator(".asset-studio article.claim").filter({hasText:"Async source B"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Remove staged "+A})).toBeVisible();
  await expect(page.getByRole("button",{name:"Remove staged "+B})).toBeVisible();
});

// C01-F: both local preflight and server commit-time revisions reject atomically.
// A request captured via Playwright route goes to the REAL backend after an independent edit.
test("asset-review V4 batch: revision conflict never commits partial batch or retries itself",async({page})=>{
  const P=await createAssetProject(page,"V4 concurrent review");
  const [A,B]=P.requirements;
  await stageVerified(page,A,"Conflict source A");
  await stageVerified(page,B,"Conflict source B");
  const batchReqs:{reviews:{requirement_id:string}[]}[]=[];
  const batchStatuses:number[]=[];
  page.on("request",r=>{if(r.url().includes("/assets/batch-approve")&&r.method()==="POST")batchReqs.push(r.postDataJSON())});
  page.on("response",r=>{if(r.url().includes("/assets/batch-approve"))batchStatuses.push(r.status())});
  const start=(await assetState(page,P.id)).project_revision;
  await incrementClaimRevision(page,P.id,"before preflight");
  await page.getByRole("button",{name:/Approve 2 selected\/staged source/}).click();
  await expect(page.locator(".asset-studio").getByRole("alert")).toContainText("REVISION_CONFLICT");
  expect(batchReqs).toHaveLength(0);
  expect((await assetState(page,P.id)).requirements.every(r=>r.approval_record_id===null)).toBe(true);
  expect(approvalLedger(P.id)).toEqual({heads:[],events:[]});
  await expect(page.getByRole("button",{name:"Remove staged "+A})).toBeVisible();
  await expect(page.getByRole("button",{name:"Remove staged "+B})).toBeVisible();
  expect((await assetState(page,P.id)).project_revision).toBeGreaterThan(start);
  let releaseCommit=()=>{}, enteredCommit=()=>{};
  const pendingCommit=new Promise<void>(resolve=>{releaseCommit=resolve});
  const requestReached=new Promise<void>(resolve=>{enteredCommit=resolve});
  await page.route("**/assets/batch-approve",async route=>{
    enteredCommit();
    await pendingCommit;
    await route.continue();
  });
  await page.getByRole("button",{name:/Approve 2 selected\/staged source/}).click();
  await requestReached;
  expect(batchReqs).toHaveLength(1);
  expect(new Set(batchReqs[0].reviews.map(r=>r.requirement_id))).toEqual(new Set([A,B]));
  await incrementClaimRevision(page,P.id,"between preflight and commit");
  releaseCommit();
  await expect(page.locator(".asset-studio").getByRole("alert")).toContainText("REVISION_CONFLICT");
  await expect.poll(()=>batchStatuses[0]).toBe(409);
  const rejected=await assetState(page,P.id);
  expect(rejected.requirements.every(r=>r.approval_record_id===null)).toBe(true);
  expect(approvalLedger(P.id)).toEqual({heads:[],events:[]});
  await expect(page.getByRole("button",{name:"Remove staged "+A})).toBeVisible();
  await expect(page.getByRole("button",{name:"Remove staged "+B})).toBeVisible();
  expect(batchReqs).toHaveLength(1); // no silent retry
  await page.unroute("**/assets/batch-approve");
  await page.getByRole("button",{name:/Approve 2 selected\/staged source/}).click();
  await expect(page.locator(".asset-studio .notice.success")).toContainText("Approved 2 requirement(s)");
  expect(batchReqs).toHaveLength(2);
  expect((await assetState(page,P.id)).requirements.filter(r=>r.approval_record_id!==null)).toHaveLength(2);
  expect(new Set(approvalLedger(P.id).heads.map(row=>row[0]))).toEqual(new Set([A,B]));
  expect(approvalLedger(P.id).events).toHaveLength(2);
});


// C02-F: test-owned SQLite fixture. This does NOT impersonate a successful
// provider request: owner mock-HTTP tests separately establish pre-submit proof.
function jobSql(action:"seed"|"read",projectId:string,state:string,errorCode:string,jobId="") {
  const root=path.resolve(here,"../../..");
  const python=path.join(root,".venv","Scripts","python.exe"); // Windows-only repo test contract.
  const fixtureRoot=path.join(root,"renderer",".artifacts","approved-player-test");
  const database=isolatedFlow?.db??(process.env.HVS_B2_FIXTURE==="1"?path.join(fixtureRoot,"g4.sqlite"):path.join(root,"frontend",".e2e-data","state.sqlite"));
  const media=isolatedFlow?.artifactRoot??(process.env.HVS_B2_FIXTURE==="1"?path.join(fixtureRoot,"artifacts"):path.join(root,"frontend",".e2e-data","media"));
  const script=[
    "import json,sys,uuid",
    "from pathlib import Path",
    "from backend.app.projects.storage import ProjectStore",
    "from backend.app.jobs.queue import JobQueue",
    "db=Path(sys.argv[6])",
    "store=ProjectStore(db,Path(sys.argv[7]))",
    "q=JobQueue(store)",
    "if sys.argv[1]=='seed':",
    "    job=q.submit(sys.argv[2],'glabs_image','v4fixture-'+uuid.uuid4().hex,{},store.revision(sys.argv[2]))",
    "    with store._transaction() as con:",
    "        con.execute('UPDATE jobs SET state=?,error_code=? WHERE job_id=?',(sys.argv[3],sys.argv[4],job['job_id']))",
    "    print(json.dumps(q.get(job['job_id'])))",
    "else:",
    "    print(json.dumps(q.get(sys.argv[5])))"
  ].join("\n");
  const output=execFileSync(python,["-c",script,action,projectId,state,errorCode,jobId,database,media],{
    cwd:root,encoding:"utf8"
  });
  return JSON.parse(output.trim()) as {job_id:string;project_id:string;state:string;
    provider_task_id:string|null;cancel_requested:number;error_code:string|null};
}

test("asset-review V4 queue: jobs UI reflects persisted safe cancel versus uncertain review",async({page})=>{
  await page.goto("/");
  const id=await startNewProject(page,"V4 safe cancel UI");
  const other=await page.request.post(baseApi+"/projects",{
    data:{title:"V4 foreign job scope",language:"en",style_id:"HistoryEditorialPaper.v1"}});
  expect(other.status()).toBe(201);
  const foreignId=(await other.json()).project_id as string;
  expect(foreignId).not.toBe(id);
  const safe=jobSql("seed",id,"FAILED_RETRYABLE","GLABS_PROVIDER_IDENTITY_STALE");
  const unknown=jobSql("seed",id,"BLOCKED_REVIEW","GLABS_UNCERTAIN_SUBMISSION");
  expect(safe.provider_task_id).toBeNull();
  expect(unknown.provider_task_id).toBeNull();
  const wrongProject=await page.request.post(baseApi+"/projects/"+foreignId+"/jobs/"+safe.job_id+"/cancel",{
    headers:{"Idempotency-Key":crypto.randomUUID()}});
  expect(wrongProject.ok()).toBe(false);
  expect(jobSql("read",id,"","",safe.job_id).state).toBe("FAILED_RETRYABLE");
  const resultSafe=await page.request.get(baseApi+"/projects/"+id+"/jobs");
  expect(resultSafe.status()).toBe(200);
  expect((await resultSafe.json()).map((x:{job_id:string})=>x.job_id))
    .toEqual(expect.arrayContaining([safe.job_id,unknown.job_id]));
  await page.locator(".jobs-drawer summary").click();
  await page.getByRole("button",{name:"Refresh jobs"}).click();
  const jobList=page.locator("details.jobs-drawer");
  const safeRow=jobList.locator("li").filter({hasText:safe.job_id});
  const unknownRow=jobList.locator("li").filter({hasText:unknown.job_id});
  await expect(safeRow).toContainText("FAILED_RETRYABLE");
  await expect(unknownRow).toContainText("BLOCKED_REVIEW");
  await safeRow.getByRole("button",{name:"Request cancellation"}).click();
  await expect(safeRow).toContainText("CANCELLED");
  await expect(safeRow.getByRole("button",{name:/Retry/})).toHaveCount(0);
  const cancelled=jobSql("read",id,"","",safe.job_id);
  expect(cancelled).toMatchObject({state:"CANCELLED",provider_task_id:null,
    cancel_requested:1,error_code:"GLABS_PROVIDER_IDENTITY_STALE"});
  const firstCancel=await page.request.post(
    baseApi+"/projects/"+id+"/jobs/"+safe.job_id+"/cancel",
    {headers:{"Idempotency-Key":crypto.randomUUID()}});
  expect(firstCancel.status()).toBe(200);
  expect((await firstCancel.json()).state).toBe("CANCELLED");
  const forbidden=await page.request.post(baseApi+"/projects/"+id+"/jobs/"+safe.job_id+"/retry",{
    headers:{"Idempotency-Key":crypto.randomUUID()}});
  expect(forbidden.ok()).toBe(false);
  expect((await forbidden.json()).code).toBe("JOB_RETRY_FORBIDDEN");
  await unknownRow.getByRole("button",{name:"Request cancellation"}).click();
  await expect(unknownRow.getByRole("button",{name:"Reconcile cancellation with provider"})).toBeVisible();
  await expect(page.getByRole("status").first()).toContainText("Cancel request");
  await expect(unknownRow).toContainText("BLOCKED_REVIEW");
  await expect(unknownRow).toContainText("GLABS_UNCERTAIN_SUBMISSION");
  await expect(unknownRow).toContainText("Restore original webhook credentials");
  const uncertain=jobSql("read",id,"","",unknown.job_id);
  expect(uncertain).toMatchObject({state:"BLOCKED_REVIEW",provider_task_id:null,
    cancel_requested:1,error_code:"GLABS_UNCERTAIN_SUBMISSION"});
  await expect(jobList).not.toContainText("remote stop succeeded");
  await page.reload();
  await openExistingProject(page,id);
  await expect(page.locator("details.jobs-drawer"))
    .toContainText(safe.job_id+" — glabs_image: CANCELLED");
  await expect(page.locator("details.jobs-drawer"))
    .toContainText(unknown.job_id+" — glabs_image: BLOCKED_REVIEW");
  const fresh=await page.request.get(baseApi+"/projects/"+id+"/jobs");
  const jobs=await fresh.json() as {job_id:string;state:string;cancel_requested:number;provider_task_id:string|null}[];
  expect(jobs.find(j=>j.job_id===safe.job_id)).toMatchObject({state:"CANCELLED",cancel_requested:1,provider_task_id:null});
  expect(jobs.find(j=>j.job_id===unknown.job_id)).toMatchObject({state:"BLOCKED_REVIEW",cancel_requested:1,provider_task_id:null});
});


test("asset-review V4: importing changed StoryPackage globally invalidates old staged source identities",async({page})=>{
  const P=await createAssetProject(page,"V4 immutable story change");
  const [A,B]=P.requirements;
  await stageVerified(page,A,"Old story A");
  await stageVerified(page,B,"Old story B");
  await expect(page.locator(".asset-studio")).toContainText("2 staged;");
  const updated=structuredClone(P.story);
  updated.project.title=updated.project.title+" revised";
  const revision=(await assetState(page,P.id)).project_revision;
  const changed=await page.request.post(baseApi+"/projects/"+P.id+"/story/import?expected_revision="+revision,{
    headers:{"Idempotency-Key":crypto.randomUUID()},data:updated});
  expect(changed.status(),await changed.text()).toBe(200);
  await page.getByRole("button",{name:"Refresh project"}).click();
  await expect(page.getByRole("button",{name:"Remove staged "+A})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Remove staged "+B})).toHaveCount(0);
  await expect(page.locator(".asset-studio")).toContainText("Outdated staged review");
  await expect(page.getByRole("button",{name:/Approve \d+ selected\/staged source/})).toBeDisabled();
  const state=await assetState(page,P.id);
  expect(state.requirements.every(r=>r.approval_record_id===null)).toBe(true);
});
