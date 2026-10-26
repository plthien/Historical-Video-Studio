import path from "node:path";
import {fileURLToPath} from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
import {defineConfig} from "@playwright/test";
const b2Fixture=process.env.HVS_B2_FIXTURE==="1";
const b2Root=path.resolve(here,"..","renderer",".artifacts",
  process.env.HVS_PR10_FIXTURE==="mask"?"pr10-mask":
  process.env.HVS_PR10_FIXTURE==="numeric"?"pr10-numeric":
  process.env.HVS_PR10_FIXTURE==="typography"?"pr10-typography":
  process.env.HVS_B2_LONGFORM==="1"?"approved-player-test-longform":"approved-player-test");

export default defineConfig({
  testDir: "./tests/e2e", timeout: 90_000, workers: 1,
  use: {baseURL: "http://127.0.0.1:5173", browserName: "chromium", screenshot: "only-on-failure", trace: "retain-on-failure"},
  webServer: [
    {command: ".venv\\Scripts\\python.exe -m uvicorn backend.tools.e2e_voice_server:app --host 127.0.0.1 --port 8000",
     cwd: path.resolve(here, ".."), url: "http://127.0.0.1:8000/api/v1/health",
     reuseExistingServer: false, timeout: 60_000,
     env: {...process.env, HVS_DB: b2Fixture?path.join(b2Root,"g4.sqlite"):path.resolve(here, ".e2e-data/state.sqlite"),
           HVS_MEDIA: b2Fixture?path.join(b2Root,"artifacts"):path.resolve(here, ".e2e-data/media")}},
    {command: "npm run dev", cwd: here, url: "http://127.0.0.1:5173",
     reuseExistingServer: false, timeout: 60_000}
  ],
  reporter: [["list"], ["html", {open: "never"}]]
});
