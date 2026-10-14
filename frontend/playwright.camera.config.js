import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "camera.spec.js",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:5174",
    channel: process.env.PW_BROWSER_CHANNEL || "chrome",
  },
  webServer: {
    command: "npm run dev -- --port 5174",
    url: "http://127.0.0.1:5174",
    reuseExistingServer: true,
  },
});
