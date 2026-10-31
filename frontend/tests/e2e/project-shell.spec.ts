import {test, expect} from "@playwright/test";
import {apiBase,startNewProject,openExistingProject,selectImportStep,importStoryFromEditor} from "./project-workflow-helper";
import {readFileSync} from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

const fixture = JSON.parse(readFileSync(path.resolve(here,
  "../../../contracts/examples/longform/StoryPackage.longform.synthetic.json"), "utf8"));

test("project-shell: six destinations, real import and G1 human review", async ({page}, testInfo) => {
  await page.goto("/");
  for (const name of ["Project & ChatGPT", "Story Review", "Voice Studio",
    "Historical Assets", "Motion Storyboard", "Render & Delivery"]) {
    await page.getByRole("navigation").getByRole("button", {name: new RegExp("^" + name, "i")}).click();
    await expect(page.locator(".content[aria-label] h2")).toContainText(new RegExp(name.split(" / ")[0], "i"));
  }
  await page.getByRole("navigation").getByRole("button", {name: /Project & ChatGPT/}).click();
  const id = await startNewProject(page,"Sarajevo Documentary");
  const story = structuredClone(fixture);
  story.project.project_id = id;
  story.claims.forEach((c: {critical: boolean}, i: number) => {c.critical = i === 0;});
  await importStoryFromEditor(page,story);
  await expect(page.getByText("CLAIM_CRITICAL_UNRESOLVED:claim_001").first()).toBeVisible();
  await page.getByLabel("Evidence review note").first().fill("Reviewed the archival research lead and documented uncertainty");
  await page.getByRole("button", {name: "Record reviewed"}).first().click();
  await expect(page.getByRole("status")).toContainText("Claim claim_001 review completed");
  await expect(page.getByRole("button", {name: "Approve G1"})).toBeEnabled();
  await page.getByRole("button", {name: "Approve G1"}).click();
  await expect(page.getByRole("status")).toContainText("G1 approved completed");
  await page.reload();
  await openExistingProject(page,id);
  await expect(page.locator(".topline strong")).toContainText("Revision");
  await expect(page.locator(".gateboard")).toContainText("APPROVED");
  await page.screenshot({path: testInfo.outputPath("g1-approved.png")});
  // A saved evidence change invalidates the old G1 head without changing the story SHA.
  await page.getByRole("navigation").getByRole("button", {name: /Story review/i}).click();
  await page.getByLabel("Evidence review note").first().fill("Corrected archival interpretation");
  await page.getByRole("button", {name: "Record reviewed"}).first().click();
  await expect(page.getByRole("status")).toContainText("Claim claim_001 review completed");
  await expect(page.locator(".gateboard")).toContainText("READY_FOR_REVIEW");
  await page.getByRole("button", {name: "Approve G1"}).click();
  await expect(page.getByRole("status")).toContainText("G1 approved completed");
  await expect(page.locator(".gateboard")).toContainText("APPROVED");
  // Source-only edits must retain the existing saved note, invalidate G1 and allow reapproval.
  await page.getByLabel("Additional source URL (optional)").first().fill("https://www.loc.gov/item/002");
  await page.getByRole("button", {name: "Record reviewed"}).first().click();
  await expect(page.getByRole("status")).toContainText("Claim claim_001 review completed");
  await expect(page.locator(".gateboard")).toContainText("READY_FOR_REVIEW");
  await page.getByRole("button", {name: "Approve G1"}).click();
  await expect(page.locator(".gateboard")).toContainText("APPROVED");

  await expect(page.getByRole("navigation").getByRole("button", {name: /Voice Studio/})).toBeVisible();
  await page.getByRole("navigation").getByRole("button", {name: /Voice Studio/}).click();
  await expect(page.getByRole("article", {name:"Voice section sec_001"})).toBeVisible();
  await page.screenshot({path: testInfo.outputPath("voice-workspace-enabled.png")});
});

test("project-shell: malformed JSON and stale revision are visible", async ({page,request}) => {
  await page.goto("/");
  const id = await startNewProject(page,"Conflict Documentary");
  await selectImportStep(page);
  await page.locator("#story-json").fill("this is not JSON");
  await page.getByRole("button", {name: "Validate & import StoryPackage"}).click();
  await expect(page.getByRole("alert")).toBeVisible();
  const story = structuredClone(fixture);
  story.project.project_id = id;
  story.claims.forEach((c: {critical: boolean}) => {c.critical = false;});
  await page.locator("#story-json").fill(JSON.stringify(story));
  await page.getByRole("button", {name: "Validate & import StoryPackage"}).click();
  await expect(page.locator(".sidebar nav button[aria-current=page]")).toContainText("Story review");
  await expect(page.getByRole("button", {name: "Approve G1"})).toBeEnabled();
  const result = await request.post(`${apiBase}/projects/${id}/story/claims/claim_001/review`, {
    headers: {"Idempotency-Key": crypto.randomUUID()},
    data: {expected_revision: 1, status: "REVIEWED", evidence_note: "Independent operator edit"}});
  expect(result.status()).toBe(200);
  await page.getByRole("button", {name: "Approve G1"}).click();
  await expect(page.getByRole("alert")).toContainText("APPROVAL_REVISION_CONFLICT");
  await expect(page.locator(".topline strong")).toContainText("Revision 2");
});

test("project-shell: optional G1 source URLs normalize at the submission boundary", async ({page}) => {
  await page.goto("/");
  const id = await startNewProject(page,"Source URL normalization");
  const story = structuredClone(fixture);
  story.project.project_id = id;
  story.claims.forEach((c: {critical: boolean}) => {c.critical = false;});
  await importStoryFromEditor(page,story);

  const claim = page.locator(".claim").first();
  const note = "Evidence note must survive every source URL edit";
  await claim.getByLabel("Human evidence review note").fill(note);

  async function submit(button: "Record reviewed" | "Record verified", expectedSource: string | null) {
    const requestPromise = page.waitForRequest(request =>
      request.method() === "POST" && request.url().includes(`/projects/${id}/story/claims/claim_001/review`));
    const responsePromise = page.waitForResponse(response =>
      response.request().method() === "POST" && response.url().includes(`/projects/${id}/story/claims/claim_001/review`));
    await claim.getByRole("button", {name: button}).click();
    const [request,response] = await Promise.all([requestPromise,responsePromise]);
    const body = request.postDataJSON() as {source_url: string | null; expected_revision: number};
    expect(body.source_url).toBe(expectedSource);
    expect(response.status()).toBe(200);
    const result = await response.json() as {project_revision: number};
    expect(result.project_revision).toBeGreaterThanOrEqual(body.expected_revision);
    await expect(page.getByRole("status")).toContainText("Claim claim_001 review completed");
    await page.reload();
    await openExistingProject(page,id);
    await page.getByRole("navigation").getByRole("button", {name: /Story review/i}).click();
    await expect(page.locator(".claim").first()).toBeVisible();
    await expect(claim.getByLabel("Human evidence review note")).toHaveValue(note);
    await expect(claim.getByLabel("Additional source URL (optional)")).toHaveValue(expectedSource ?? "");
    return result.project_revision;
  }

  // T01: untouched optional input; T02: type then explicitly clear it.
  await submit("Record reviewed", null);
  await claim.getByLabel("Additional source URL (optional)").fill("https://example.org/temporary");
  await claim.getByLabel("Additional source URL (optional)").fill("");
  await submit("Record reviewed", null);

  // T03: whitespace-only; T04: trimmed HTTPS; T05: trimmed HTTP; T06: whitespace around URL.
  await claim.getByLabel("Additional source URL (optional)").fill(" \t ");
  await submit("Record reviewed", null);
  await claim.getByLabel("Additional source URL (optional)").fill("  https://www.loc.gov/item/001  ");
  await submit("Record verified", "https://www.loc.gov/item/001");
  await claim.getByLabel("Additional source URL (optional)").fill("  http://example.org/source  ");
  await submit("Record reviewed", "http://example.org/source");
  await claim.getByLabel("Additional source URL (optional)").fill("\thttps://example.org/trim\n");
  await submit("Record verified", "https://example.org/trim");

  // T07: clear an existing persisted URL; T08/T09 exercise both buttons.
  await claim.getByLabel("Additional source URL (optional)").fill("");
  const clearedRevision = await submit("Record reviewed", null);
  await claim.getByLabel("Additional source URL (optional)").fill(" https://example.org/reviewed ");
  await submit("Record reviewed", "https://example.org/reviewed");
  const verifiedRevision = await submit("Record verified", "https://example.org/reviewed");
  expect(verifiedRevision).toBeGreaterThanOrEqual(clearedRevision);

  // T10: malformed nonempty input is still rejected by the backend and cannot commit.
  await claim.getByLabel("Additional source URL (optional)").fill("not-a-url");
  const invalidRequestPromise = page.waitForRequest(request =>
    request.method() === "POST" && request.url().includes(`/projects/${id}/story/claims/claim_001/review`));
  const invalidResponsePromise = page.waitForResponse(response =>
    response.request().method() === "POST" && response.url().includes(`/projects/${id}/story/claims/claim_001/review`));
  await claim.getByRole("button", {name: "Record reviewed"}).click();
  const [invalidRequest,invalidResponse] = await Promise.all([invalidRequestPromise,invalidResponsePromise]);
  expect((invalidRequest.postDataJSON() as {source_url: string}).source_url).toBe("not-a-url");
  expect(invalidResponse.status()).toBe(422);
  expect((await invalidResponse.json()).code).toBe("CLAIM_SOURCE_INVALID");
  await expect(page.getByRole("alert")).toContainText("CLAIM_SOURCE_INVALID");

  await page.reload();
  await openExistingProject(page,id);
  await page.getByRole("navigation").getByRole("button", {name: /Story review/i}).click();
  await expect(page.locator(".claim").first()).toBeVisible();
  const persistedClaim = page.locator(".claim").first();
  await expect(persistedClaim.getByLabel("Human evidence review note")).toHaveValue(note);
  await expect(persistedClaim.getByLabel("Additional source URL (optional)")).toHaveValue("https://example.org/reviewed");
  const projectResponse = await page.request.get(`${apiBase}/projects/${id}`);
  expect(projectResponse.status()).toBe(200);
  expect((await projectResponse.json() as {project_revision: number}).project_revision).toBe(verifiedRevision);
});
