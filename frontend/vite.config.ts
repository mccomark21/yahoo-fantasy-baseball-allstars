import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base keeps asset + data paths correct on GitHub Pages
// (served from /<repo>/) without hardcoding the repo name.
export default defineConfig({
  base: "./",
  plugins: [react()],
});
