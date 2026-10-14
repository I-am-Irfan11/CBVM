import { test, expect } from "@playwright/test";

test.use({
  launchOptions: {
    args: [
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
    ],
  },
});

async function openCamera(page) {
  page.on("pageerror", (error) => {
    throw error;
  });
  await page.route("**/camera-test", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: `<div id="root"></div><script type="module">
        import RefreshRuntime from '/@react-refresh';
        RefreshRuntime.injectIntoGlobalHook(window);
        window.$RefreshReg$ = () => {};
        window.$RefreshSig$ = () => (type) => type;
        window.__vite_plugin_react_preamble_installed__ = true;
        const { default: DemoControls } = await import('/src/components/DemoControls.jsx');
        import React from '/node_modules/.vite/deps/react.js';
        import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
        ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(DemoControls, {
          mockAi: false, notify: () => {}, refresh: () => {}
        }));
      </script>`,
    }),
  );
  await page.route("**/api/anpr/status", (route) =>
    route.fulfill({ json: { ready: true } }),
  );
  await page.goto("/camera-test");
  await page.getByRole("button", { name: "Enable camera" }).click();
}

test("manual shutter stays usable during automatic OCR and queues the captured photo", async ({
  page,
}) => {
  let releaseScan;
  const blockedScan = new Promise((resolve) => {
    releaseScan = resolve;
  });
  let autoStarted = false;
  let manualRequests = 0;
  await page.route("**/api/anpr/detect?**", async (route) => {
    if (route.request().url().includes("manual_capture=true")) {
      manualRequests++;
      expect(route.request().postDataBuffer().length).toBeGreaterThan(0);
    } else {
      autoStarted = true;
      await blockedScan;
    }
    await route.fulfill({ json: { results: [] } });
  });
  await openCamera(page);
  await expect.poll(() => autoStarted).toBe(true);
  const shutter = page.getByRole("button", { name: "Capture plate now" });
  await expect(shutter).toBeEnabled();
  await shutter.click();
  await expect(page.getByAltText("Last captured plate image")).toBeVisible();
  await expect(
    page.getByText("1 photo(s) captured and waiting for OCR."),
  ).toBeVisible();
  releaseScan();
  await expect.poll(() => manualRequests).toBe(1);
  await expect(
    page.getByText(/No plate was recognized in this frame/),
  ).toBeVisible();
});

test("repeated automatic misses direct the user to the manual shutter", async ({
  page,
}) => {
  await page.route("**/api/anpr/detect?**", (route) =>
    route.fulfill({ json: { results: [] } }),
  );
  await openCamera(page);
  await expect(
    page.getByText(
      "No plate detected yet. Move closer or use Capture plate now.",
    ),
  ).toBeVisible({ timeout: 10000 });
  await expect(
    page.getByRole("button", { name: "Capture plate now" }),
  ).toBeEnabled();
});
