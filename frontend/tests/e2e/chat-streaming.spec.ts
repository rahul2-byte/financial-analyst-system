import { test, expect } from "@playwright/test";

test.describe("chat streaming UX", () => {
  test("renders streamed assistant text incrementally", async ({ page }) => {
    await page.addInitScript(() => {
      const originalFetch = window.fetch.bind(window);

      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

        if (url.includes("/api/chat")) {
          const encoder = new TextEncoder();
          const chunks = [
            'data: {"event":"status","data":{"message":"Planning research strategy..."}}\n\n',
            'data: {"event":"token","data":{"content":"Hel"}}\n\n',
            'data: {"event":"token","data":{"content":"lo "}}\n\n',
            'data: {"event":"token","data":{"content":"from "}}\n\n',
            'data: {"event":"token","data":{"content":"stream"}}\n\n',
            "data: [DONE]\n\n",
          ];

          const stream = new ReadableStream<Uint8Array>({
            start(controller) {
              let index = 0;
              const emit = () => {
                if (index >= chunks.length) {
                  controller.close();
                  return;
                }
                controller.enqueue(encoder.encode(chunks[index]));
                index += 1;
                setTimeout(emit, 90);
              };
              emit();
            },
          });

          return new Response(stream, {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          });
        }

        return originalFetch(input, init);
      };
    });

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
    await page.addInitScript(() => {
      const originalFetch = window.fetch.bind(window);

      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

        if (url.includes("/api/chat")) {
          const encoder = new TextEncoder();
          const signal = init?.signal;

          const stream = new ReadableStream<Uint8Array>({
            start(controller) {
              const timer = setInterval(() => {
                if (signal?.aborted) {
                  clearInterval(timer);
                  controller.close();
                  return;
                }
                controller.enqueue(
                  encoder.encode('data: {"event":"token","data":{"content":"chunk "}}\n\n'),
                );
              }, 75);

              signal?.addEventListener(
                "abort",
                () => {
                  clearInterval(timer);
                  controller.close();
                },
                { once: true },
              );
            },
          });

          return new Response(stream, {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          });
        }

        return originalFetch(input, init);
      };
    });

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
