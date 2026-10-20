import path from "node:path";
import {defineConfig} from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e", timeout: 90_000, workers: 1,
  use: {baseURL: "http://127.0.0.1:5173", browserName: "chromium"},
  webServer: [
    {command: ".venv\\Scripts\\python.exe -m uvicorn backend.app.api.server:app --host 127.0.0.1 --port 8000",
     cwd: path.resolve(__dirname, ".."), url: "http://127.0.0.1:8000/api/v1/health",
     reuseExistingServer: false, timeout: 60_000,
     env: {...process.env, HVS_DB: path.resolve(__dirname, ".e2e-data/state.sqlite"),
           HVS_MEDIA: path.resolve(__dirname, ".e2e-data/media")}},
    {command: "npm run dev", cwd: __dirname, url: "http://127.0.0.1:5173",
     reuseExistingServer: false, timeout: 60_000}
  ],
  reporter: [["list"], ["html", {open: "never"}]]
});
