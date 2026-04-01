import type { Page } from "@playwright/test";

export async function installIncrementalStreamMock(page: Page) {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;

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
}

export async function installAbortableStreamMock(page: Page) {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;

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
}
