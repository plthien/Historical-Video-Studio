import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";
import {readFileSync} from "node:fs";

// One checked-in source of truth for developer-facing BE and FE ports.
// Playwright may explicitly override Vite's port for isolated test servers.
const ports = JSON.parse(readFileSync(new URL("../config/ports.json", import.meta.url), "utf8")) as {
  backend_port: number;
  frontend_port: number;
};
for (const [name, port] of Object.entries(ports)) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`Invalid ${name} in config/ports.json`);
  }
}

// The Player and sibling renderer source must resolve the SAME React and Remotion
// modules. Identical package versions in separate node_modules roots do not
// imply identical React hooks or Remotion context instances at browser runtime.
export default defineConfig({
  plugins: [react()],
  resolve: {dedupe: ["react", "react-dom", "remotion"]},
  server: {host: "127.0.0.1", port: ports.frontend_port, strictPort: true},
  preview: {host: "127.0.0.1", port: ports.frontend_port, strictPort: true},
  define: {
    __HVS_DEFAULT_API_ORIGIN__: JSON.stringify(`http://127.0.0.1:${ports.backend_port}/api/v1`),
  },
});
