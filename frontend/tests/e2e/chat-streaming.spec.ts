import { test, expect } from "@playwright/test";
import {
  installAbortableStreamMock,
  installIncrementalStreamMock,
} from "./helpers/stream-mocks";

test.describe("chat streaming UX", () => {
  test("renders streamed assistant text incrementally", async ({ page }) => {
    await installIncrementalStreamMock(page);

    await page.goto("/");
    const input = page.getByPlaceholder("Analyze market trends, compare sectors...");
    await input.fill("check streaming");
    await input.press("Enter");

    await expect(page.getByText("Planning research strategy...")).toBeVisible();
    await expect(page.getByText(/Hello/)).toBeVisible();
    await expect(page.getByText(/Hello from stream/)).toBeVisible();
    await expect(page.getByText("Methodology")).toBeVisible();
  });

  test("stop button aborts in-flight stream and exits loading state", async ({ page }) => {
    await installAbortableStreamMock(page);

    await page.goto("/");
    const input = page.getByPlaceholder("Analyze market trends, compare sectors...");
    await input.fill("stop test");
    await input.press("Enter");

    const stopButton = page.getByTitle("Stop generating");
    await expect(stopButton).toBeVisible();
    await stopButton.click();

    await expect(page.getByTitle("Stop generating")).toBeHidden();
    await expect(input).toBeEnabled();
  });
});
