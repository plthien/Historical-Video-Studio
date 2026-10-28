import path from "node:path";
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
import {defineConfig} from "@playwright/test";
const b2Fixture=process.env.HVS_B2_FIXTURE==="1";
const parityProduction=process.env.HVS_PARITY_PRODUCTION==="1";
const b3Fixture=process.env.HVS_B3_FIXTURE==="1";
const apiPort=b3Fixture?8011:8000;
const uiPort=b3Fixture?5174:5173;
const b2Root=path.resolve(here,"..","renderer",".artifacts",
  process.env.HVS_PR10_FIXTURE==="mask"?"pr10-mask":
  process.env.HVS_PR10_FIXTURE==="numeric"?"pr10-numeric":
  process.env.HVS_PR10_FIXTURE==="typography"?"pr10-typography":
  process.env.HVS_B2_LONGFORM==="1"?"approved-player-test-longform":"approved-player-test");
const fullFlowConfig=process.env.HVS_FULL_FLOW_CONFIG
  ?JSON.parse(readFileSync(path.resolve(here,process.env.HVS_FULL_FLOW_CONFIG),"utf8")) as {db:string,artifactRoot:string}
  :null;

export default defineConfig({
  testDir: "./tests/e2e", timeout: 90_000, workers: 1,
  use: {baseURL: `http://127.0.0.1:${uiPort}`, browserName: "chromium",
        ...(b3Fixture?{channel:"msedge" as const}:{}),
        screenshot: "only-on-failure", trace: "retain-on-failure"},
  webServer: [
    {command: `.venv\\Scripts\\python.exe -m uvicorn backend.tools.e2e_voice_server:app --host 127.0.0.1 --port ${apiPort}`,
     cwd: path.resolve(here, ".."), url: `http://127.0.0.1:${apiPort}/api/v1/health`,
     reuseExistingServer: false, timeout: 60_000,
     env: {...process.env, HVS_DB: fullFlowConfig?.db??(b2Fixture?path.join(b2Root,"g4.sqlite"):path.resolve(here, ".e2e-data/state.sqlite")),
           HVS_MEDIA: fullFlowConfig?.artifactRoot??(b2Fixture?path.join(b2Root,"artifacts"):path.resolve(here, ".e2e-data/media"))}},
    {command: parityProduction?"npx vite preview --host 127.0.0.1 --port 5173 --strictPort":b3Fixture?"npm run dev -- --port 5174":"npm run dev", cwd: here, url: `http://127.0.0.1:${uiPort}`,
     reuseExistingServer: false, timeout: 60_000,
     env: {...process.env,VITE_API_ORIGIN:`http://127.0.0.1:${apiPort}/api/v1`}}
  ],
  reporter: [["list"], ["html", {open: "never"}]]
});
