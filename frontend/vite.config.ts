import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

// The Player and sibling renderer source must resolve the SAME React and Remotion
// modules. Identical package versions in separate node_modules roots do not
// imply identical React hooks or Remotion context instances at browser runtime.
export default defineConfig({
  plugins: [react()],
  resolve: {dedupe: ["react", "react-dom", "remotion"]},
  server: {host: "127.0.0.1", port: 5173, strictPort: true},
});
