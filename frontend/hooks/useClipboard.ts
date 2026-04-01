"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseClipboardOptions {
  resetAfterMs?: number;
}

export function useClipboard(options: UseClipboardOptions = {}) {
  const { resetAfterMs = 2000 } = options;
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const copyText = useCallback(
    async (value: string) => {
      await navigator.clipboard.writeText(value);
      setCopied(true);

      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }

      timerRef.current = setTimeout(() => {
        setCopied(false);
        timerRef.current = null;
      }, resetAfterMs);
    },
    [resetAfterMs],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  return { copied, copyText };
}
