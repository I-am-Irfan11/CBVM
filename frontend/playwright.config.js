import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:5173",
    browserName: "chromium",
    channel: process.env.PW_BROWSER_CHANNEL || "msedge",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command:
        "..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_MODE: "memory",
        USE_MOCK_AI: "true",
        RUN_VIDEO_WORKER: "false",
        SEED_ON_STARTUP: "true",
        JWT_SECRET_KEY: "test-only-not-a-deployment-secret-1234567890",
        SEED_ADMIN_PASSWORD: "TestOnly-password-123!",
        SEED_SECURITY_PASSWORD: "TestOnly-password-123!",
        SEED_DEPARTMENT_PASSWORD: "TestOnly-password-123!",
      },
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
