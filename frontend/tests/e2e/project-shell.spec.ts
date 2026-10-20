import {test, expect} from "@playwright/test";
import {readFileSync} from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

const fixture = JSON.parse(readFileSync(path.resolve(here,
  "../../../contracts/examples/longform/StoryPackage.longform.synthetic.json"), "utf8"));

test("project-shell: six destinations, real import and G1 human review", async ({page}) => {
  await page.goto("/");
  for (const name of ["Project & ChatGPT Import", "Story Review", "Voice Studio",
    "Historical Assets", "Motion Storyboard", "Render & Delivery"]) {
    await page.getByRole("navigation").getByRole("button", {name: new RegExp(name.split(" ")[0])}).click();
    await expect(page.locator(".content[aria-label] h2")).toContainText(new RegExp(name.split(" / ")[0], "i"));
  }
  await page.getByRole("navigation").getByRole("button", {name: /Project & ChatGPT/}).click();
  await page.getByLabel("Project title").fill("Sarajevo Documentary");
  await page.getByRole("button", {name: "Create project"}).click();
  await expect(page.getByRole("status")).toContainText("Project creation completed");
  const id = (await page.locator(".topline strong").innerText()).trim();
  const story = structuredClone(fixture);
  story.project.project_id = id;
  story.claims.forEach((c: {critical: boolean}, i: number) => {c.critical = i === 0;});
  await page.getByLabel("StoryPackage JSON").fill(JSON.stringify(story));
  await page.getByRole("button", {name: "Import and validate story"}).click();
  await expect(page.getByRole("status")).toContainText("Story import completed");
  await expect(page.getByText("CLAIM_CRITICAL_UNRESOLVED:claim_001").first()).toBeVisible();
  await page.getByLabel("Evidence review note").first().fill("Reviewed the archival research lead and documented uncertainty");
  await page.getByRole("button", {name: "Record reviewed"}).first().click();
  await expect(page.getByRole("status")).toContainText("Claim claim_001 review completed");
  await expect(page.getByRole("button", {name: "Approve G1"})).toBeEnabled();
  await page.getByRole("button", {name: "Approve G1"}).click();
  await expect(page.getByRole("status")).toContainText("G1 approved completed");
  await page.reload();
  await page.getByLabel("Project ID").fill(id);
  await page.getByRole("button", {name: "Open existing project"}).click();
  await expect(page.getByText("Revision:")).toBeVisible();
  await expect(page.locator(".gateboard")).toContainText("APPROVED");
  await expect(page.getByRole("navigation").getByRole("button", {name: /Voice Studio/})).toBeVisible();
  await page.getByRole("navigation").getByRole("button", {name: /Voice Studio/}).click();
  await expect(page.getByText("Not available in A1")).toBeVisible();
});

test("project-shell: malformed JSON and stale revision are visible", async ({page,request}) => {
  await page.goto("/");
  await page.getByLabel("Project title").fill("Conflict Documentary");
  await page.getByRole("button", {name: "Create project"}).click();
  const id = (await page.locator(".topline strong").innerText()).trim();
  await page.getByLabel("StoryPackage JSON").fill("this is not JSON");
  await page.getByRole("button", {name: "Import and validate story"}).click();
  await expect(page.getByRole("alert")).toBeVisible();
  const story = structuredClone(fixture);
  story.project.project_id = id;
  story.claims.forEach((c: {critical: boolean}) => {c.critical = false;});
  await page.getByLabel("StoryPackage JSON").fill(JSON.stringify(story));
  await page.getByRole("button", {name: "Import and validate story"}).click();
  await expect(page.getByRole("button", {name: "Approve G1"})).toBeEnabled();
  const result = await request.post(`http://127.0.0.1:8000/api/v1/projects/${id}/story/claims/claim_001/review`, {
    headers: {"Idempotency-Key": crypto.randomUUID()},
    data: {expected_revision: 1, status: "REVIEWED", evidence_note: "Independent operator edit"}});
  expect(result.status()).toBe(200);
  await page.getByRole("button", {name: "Approve G1"}).click();
  await expect(page.getByRole("alert")).toContainText("APPROVAL_REVISION_CONFLICT");
  await expect(page.getByText("Revision: 2")).toBeVisible();
});
