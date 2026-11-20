import { Box, measureElement, type DOMElement } from 'ink';
import { useEffect, useRef, useState, type ReactNode } from 'react';

export interface ClippedTailProps {
  /** The most rows the live draft may take. Longer drafts show their last `maxRows` rows. */
  maxRows: number;
  children: ReactNode;
}

/**
 * Keeps a streaming draft inside the terminal. Ink redraws the whole live region on every
 * frame, so a region taller than the screen would scroll and leave debris in scrollback.
 * The child is measured after layout; when it is taller than `maxRows` the box is fixed to
 * `maxRows`, bottom-aligned, with the head clipped. A short draft takes only its own height.
 */
export function ClippedTail({ maxRows, children }: ClippedTailProps) {
  const ref = useRef<DOMElement>(null);
  const [measured, setMeasured] = useState(0);
  useEffect(() => {
    if (ref.current === null) return;
    const { height } = measureElement(ref.current);
    if (height !== measured) setMeasured(height);
  });
  const clipped = measured > maxRows;
  return (
    <Box
      flexDirection="column"
      flexShrink={0}
      overflow="hidden"
      justifyContent="flex-end"
      height={clipped ? maxRows : undefined}
    >
      <Box ref={ref} flexDirection="column" flexShrink={0}>
        {children}
      </Box>
    </Box>
  );
}
