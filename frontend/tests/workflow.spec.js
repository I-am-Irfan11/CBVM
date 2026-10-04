import { test, expect } from "@playwright/test";

// The sign-in screen is a dummy entrance while DEMO_OPEN_ACCESS is enabled: it
// checks no credentials, so the suite just passes through it.
async function enterDemoConsole(page) {
  await page.getByRole("button", { name: "Enter GateLog" }).click();
}

test("registry, entry, exit, history, review, and live dashboard", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await enterDemoConsole(page);
  await expect(
    page.getByRole("heading", { name: "Campus at a glance." }),
  ).toBeVisible();
  await expect(page.getByText("Live updates connected")).toBeVisible();
  await page.getByRole("link", { name: "Vehicle registry" }).click();
  await page
    .getByRole("button", { name: "Register vehicle", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  const plate = `TN09ZZ${Math.floor(1000 + Math.random() * 9000)}`;
  await dialog.getByLabel("Registration number").fill(plate);
  await dialog.getByLabel("Owner name").fill("Browser Test Vehicle");
  await dialog.getByRole("button", { name: "Register vehicle" }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByLabel("Search vehicles").fill(plate);
  const row = page.getByRole("row").filter({ hasText: plate });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Entry", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Record entry" })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("link", { name: "Currently inside" }).click();
  await page
    .getByRole("row")
    .filter({ hasText: plate })
    .getByRole("button", { name: "Record exit" })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Record exit" })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: plate })).toHaveCount(0);
  await page.getByRole("link", { name: "Vehicle history" }).click();
  await page.getByLabel("History registration number").fill(plate);
  await page.getByRole("button", { name: "Find history" }).click();
  await expect(page.getByRole("row").filter({ hasText: plate })).toContainText(
    "Completed",
  );
  await page.getByRole("link", { name: "Live activity" }).click();
  await page.getByLabel("Detection scenario").selectOption("low_confidence");
  await page.getByRole("button", { name: "Run detection" }).click();
  await expect(page.getByRole("status")).toContainText("Sent to review");
  await page.getByRole("link", { name: /Review queue/ }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "TN O9 AB I234" }),
  ).toContainText("43%");
  await page.getByRole("button", { name: "Reject" }).first().click();
  await expect(page.getByRole("status")).toContainText("Review dismissed");
  expect(errors).toEqual([]);
});

test("dashboard fits a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await enterDemoConsole(page);
  await expect(
    page.getByRole("heading", { name: "Campus at a glance." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
