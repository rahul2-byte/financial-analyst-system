/**
 * Markdown → Ink tree. `render(text, width)` lexes with `marked` and lays the blocks
 * out at a fixed column width. The input is already sanitized (sanitize.ts); this
 * module does not sanitize again.
 *
 * Covered: headings (h1/h2 ledger bold, h3 paper bold, h4+ dim bold), citation chips for
 * `[n]` and `[citations: …]`, paragraphs with bold/italic/strike/inline code,
 * fenced code on graphite, ordered and unordered lists (nested, task items), tables
 * with rule-coloured box lines fitted to the width, blockquotes behind a dim bar,
 * links as `text (host)`, and horizontal rules.
 *
 * Prose (headings, paragraphs, list and quote text) is word-wrapped here, not by Ink:
 * each line is its own row, so Ink never re-wraps it and no stray spaces appear at the
 * break points or at the edges of styled runs.
 */
import type { ReactNode } from 'react';
import { Box, Text } from 'ink';
import { lexer, type Token, type Tokens } from 'marked';
import { color } from './theme.js';
import { displayWidth, hardWrap, hostOf, padEnd, wrapWords } from './format.js';

const BULLET = '•';

/** Plain text of inline tokens: used for table cells, where styling is not kept. */
function plainInline(tokens: readonly Token[] | undefined, fallback = ''): string {
  if (!tokens || tokens.length === 0) return fallback;
  return tokens
    .map((token) => {
      switch (token.type) {
        case 'link': {
          const link = token as Tokens.Link;
          const label = plainInline(link.tokens, link.text);
          const host = hostOf(link.href);
          return host && label !== host && !label.includes(host) ? `${label} (${host})` : label || host || link.href;
        }
        case 'codespan':
        case 'escape':
        case 'text':
        case 'strong':
        case 'em':
        case 'del':
          return plainInline((token as Tokens.Generic).tokens, (token as Tokens.Generic).text ?? '');
        case 'br':
          return ' ';
        default:
          return (token as Tokens.Generic).text ?? (token as Tokens.Generic).raw ?? '';
      }
    })
    .join('');
}

/** Inline emphasis on one run of prose. Only what differs from the line's base style. */
export interface InlineStyle {
  bold?: boolean;
  italic?: boolean;
  strike?: boolean;
  code?: boolean;
  /** Colour override: the dim `(host)` suffix on links. */
  color?: string;
  /** Citation chip: ledger on graphite, never split across lines. */
  chip?: boolean;
  /** Background override, used by the report rows. */
  backgroundColor?: string;
}

/** A run of prose sharing one inline style. `hardBreak` marks a `<br>` line break. */
export interface Segment {
  text: string;
  style: InlineStyle;
  hardBreak?: boolean;
}

/** Inline tokens flattened, in reading order, into styled segments. */
export function flattenInline(
  tokens: readonly Token[] | undefined,
  style: InlineStyle = {},
  out: Segment[] = [],
): Segment[] {
  for (const token of tokens ?? []) {
    const generic = token as Tokens.Generic;
    switch (token.type) {
      case 'strong':
        flattenInline(generic.tokens, { ...style, bold: true }, out);
        break;
      case 'em':
        flattenInline(generic.tokens, { ...style, italic: true }, out);
        break;
      case 'del':
        flattenInline(generic.tokens, { ...style, strike: true }, out);
        break;
      case 'codespan':
        // No padding inside the span: spaces here would double up with the prose either side.
        out.push({ text: generic.text ?? '', style: { ...style, code: true } });
        break;
      case 'link':
      case 'image': {
        const link = token as Tokens.Link | Tokens.Image;
        const label = token.type === 'link' ? (link as Tokens.Link).tokens : undefined;
        if (label && label.length > 0) flattenInline(label, style, out);
        else out.push({ text: link.text, style });
        const host = hostOf(link.href ?? '');
        const plainLabel = plainInline(label, link.text);
        if (host !== null && !plainLabel.includes(host)) {
          out.push({ text: ` (${host})`, style: { ...style, color: color('dim') } });
        }
        break;
      }
      case 'br':
        out.push({ text: '', style, hardBreak: true });
        break;
      case 'text':
        if (generic.tokens) flattenInline(generic.tokens, style, out);
        else pushWithChips(generic.text ?? '', style, out);
        break;
      default:
        pushWithChips(generic.text ?? generic.raw ?? '', style, out);
    }
  }
  return out;
}

/** `[citations: c2, c3]` / `[citation: c1]` (any id), bare ids `[c2]`, or bare numbers: `[3]`, `[1, 2]`. */
const CITATION = /\[citations?:\s*([A-Za-z0-9_-]+(?:\s*,\s*[A-Za-z0-9_-]+)*)\]|\[(\d+(?:\s*,\s*\d+)*)\]|\[(c\d+(?:\s*,\s*c\d+)*)\]/gi;

/**
 * Plain text with citation markers turned into one chip per source number. A bare id such as
 * `c2` has no mapping to the Sources list here, so it is dropped (with the space before it)
 * rather than shown raw.
 */
function pushWithChips(text: string, style: InlineStyle, out: Segment[]): void {
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const index = match.index ?? 0;
    const ids = (match[1] ?? match[2] ?? match[3] ?? '').split(/\s*,\s*/).filter((id) => /^\d+$/.test(id));
    const before = text.slice(last, index);
    const kept = ids.length > 0 ? before : before.replace(/\s+$/, '');
    if (kept !== '') out.push({ text: kept, style });
    ids.forEach((id, position) => {
      if (position > 0) out.push({ text: ' ', style });
      out.push({ text: `[${id}]`, style: { ...style, chip: true } });
    });
    last = index + match[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), style });
}

/**
 * Inline Markdown (one or more short paragraphs) as styled segments, for report rows.
 * Block structure is not kept: paragraphs are joined with a hard break.
 */
export function inlineSegments(text: string): Segment[] {
  const out: Segment[] = [];
  for (const token of lexer(text)) {
    if (token.type === 'space') continue;
    if (out.length > 0) out.push({ text: '', style: {}, hardBreak: true });
    const generic = token as Tokens.Generic;
    if (generic.tokens) flattenInline(generic.tokens, {}, out);
    else pushWithChips(generic.text ?? generic.raw ?? '', {}, out);
  }
  return out;
}

/** A styled stretch of one output line. */
export interface Piece {
  text: string;
  style: InlineStyle;
}

/** Whitespace is a break opportunity; a word is a run of pieces with no whitespace between. */
type Item =
  | { kind: 'space'; style: InlineStyle }
  | { kind: 'word'; pieces: Piece[]; width: number }
  | { kind: 'break' };

function sameStyle(a: InlineStyle, b: InlineStyle): boolean {
  return (
    !!a.bold === !!b.bold &&
    !!a.italic === !!b.italic &&
    !!a.strike === !!b.strike &&
    !!a.code === !!b.code &&
    !!a.chip === !!b.chip &&
    a.color === b.color &&
    a.backgroundColor === b.backgroundColor
  );
}

/**
 * Greedy word wrap of styled segments to `width` columns, measured with `displayWidth`.
 * Whitespace runs collapse to one space; a space at a line break is dropped; a word
 * wider than `width` is broken by column. Every returned line is at most `width` wide
 * and neither starts nor ends with a space.
 */
export function wrapSegments(segments: readonly Segment[], width: number): Piece[][] {
  const limit = Math.max(1, Math.floor(width));

  const items: Item[] = [];
  let current: Piece[] = [];
  const endWord = (): void => {
    if (current.length === 0) return;
    const text = current.map((piece) => piece.text).join('');
    items.push({ kind: 'word', pieces: current, width: displayWidth(text) });
    current = [];
  };
  for (const segment of segments) {
    if (segment.hardBreak) {
      endWord();
      items.push({ kind: 'break' });
      continue;
    }
    for (const part of segment.text.split(/(\s+)/)) {
      if (part === '') continue;
      if (/^\s/.test(part)) {
        endWord();
        items.push({ kind: 'space', style: segment.style });
      } else {
        current.push({ text: part, style: segment.style });
      }
    }
  }
  endWord();

  const lines: Piece[][] = [];
  let line: Piece[] = [];
  let lineWidth = 0;
  let pendingSpace: InlineStyle | null = null;
  const append = (text: string, style: InlineStyle): void => {
    const last = line[line.length - 1];
    if (last && sameStyle(last.style, style)) last.text += text;
    else line.push({ text, style });
  };
  const flush = (): void => {
    lines.push(line);
    line = [];
    lineWidth = 0;
  };

  for (const item of items) {
    if (item.kind === 'break') {
      flush();
      pendingSpace = null;
      continue;
    }
    if (item.kind === 'space') {
      // A space only matters between two words on the same line.
      if (line.length > 0) pendingSpace = item.style;
      continue;
    }

    const gap = pendingSpace !== null && line.length > 0 ? 1 : 0;
    if (lineWidth + gap + item.width <= limit) {
      if (gap === 1 && pendingSpace !== null) append(' ', pendingSpace);
      for (const piece of item.pieces) append(piece.text, piece.style);
      lineWidth += gap + item.width;
    } else {
      if (line.length > 0) flush();
      if (item.width <= limit) {
        for (const piece of item.pieces) append(piece.text, piece.style);
        lineWidth = item.width;
      } else {
        // Hard-break an overlong word by column; a single glyph wider than the line
        // still gets its own line.
        for (const piece of item.pieces) {
          for (const char of Array.from(piece.text)) {
            const w = displayWidth(char);
            if (lineWidth + w > limit && line.length > 0) flush();
            append(char, piece.style);
            lineWidth += w;
          }
        }
      }
    }
    pendingSpace = null;
  }
  if (line.length > 0) lines.push(line);
  return lines;
}

/** One styled piece as Ink: plain pieces inherit the line's colour and weight. */
export function renderPiece(piece: Piece, index: number): ReactNode {
  const { text, style } = piece;
  if (
    !style.bold &&
    !style.italic &&
    !style.strike &&
    !style.code &&
    !style.chip &&
    style.color === undefined &&
    style.backgroundColor === undefined
  ) {
    return text;
  }
  const boxed = style.code || style.chip;
  return (
    <Text
      key={index}
      color={style.chip ? color('ledger') : style.code ? color('paper') : style.color}
      backgroundColor={style.backgroundColor ?? (boxed ? color('graphite') : undefined)}
      bold={style.bold}
      italic={style.italic}
      strikethrough={style.strike}
    >
      {text}
    </Text>
  );
}

/**
 * Prose laid out line by line. Each line is one `<Text>` row already at most `width`
 * wide, with `wrap="truncate-end"` as a guard so Ink never re-wraps it.
 */
function renderProse(
  segments: readonly Segment[],
  width: number,
  key: string,
  base: { color?: string; bold?: boolean },
): ReactNode {
  const lines = wrapSegments(segments, width);
  if (lines.length === 0) return null;
  return (
    <Box key={key} flexDirection="column" width={width}>
      {lines.map((pieces, row) => (
        <Text key={`${key}-${row}`} wrap="truncate-end" color={base.color} bold={base.bold}>
          {pieces.map((piece, index) => renderPiece(piece, index))}
        </Text>
      ))}
    </Box>
  );
}

/** Fit column widths into `available` by shrinking the widest column one step at a time. */
export function fitColumns(natural: readonly number[], available: number): number[] {
  const widths = natural.map((w) => Math.max(1, w));
  let total = widths.reduce((sum, w) => sum + w, 0);
  while (total > available) {
    let widest = 0;
    for (let i = 1; i < widths.length; i++) {
      if ((widths[i] ?? 0) > (widths[widest] ?? 0)) widest = i;
    }
    if ((widths[widest] ?? 0) <= 1) break;
    widths[widest] = (widths[widest] ?? 1) - 1;
    total -= 1;
  }
  return widths;
}

function renderTable(token: Tokens.Table, width: number, key: string): ReactNode {
  const headers = token.header.map((cell) => plainInline(cell.tokens, cell.text));
  const rows = token.rows.map((row) => row.map((cell) => plainInline(cell.tokens, cell.text)));
  const cols = headers.length;
  if (cols === 0) return null;

  const natural = headers.map((header, c) =>
    Math.max(displayWidth(header), ...rows.map((row) => displayWidth(row[c] ?? ''))),
  );
  // Chrome: outer bars (cols + 1) plus one space either side of each cell (2 * cols).
  const widths = fitColumns(natural, Math.max(cols, width - (3 * cols + 1)));

  const rule = color('rule');
  const edge = (left: string, join: string, right: string): string =>
    left + widths.map((w) => '─'.repeat(w + 2)).join(join) + right;
  /** `│ a │ b │` from already-padded cells: one space either side of each cell. */
  const tableLine = (cells: readonly string[]): string =>
    '│' + cells.map((cell) => ` ${cell} `).join('│') + '│';

  // Each content line is one whole string, so every bar lands in the same column on every
  // row. Splitting a row into several <Text> nodes lets Ink drop the padding spaces.
  const renderRow = (cells: readonly string[], rowKey: string, isHeader: boolean): ReactNode[] => {
    const wrapped = widths.map((w, c) => wrapWords(cells[c] ?? '', w));
    const height = Math.max(1, ...wrapped.map((lines) => lines.length));
    const lines: ReactNode[] = [];
    for (let line = 0; line < height; line++) {
      const text = tableLine(widths.map((w, c) => padEnd(wrapped[c]?.[line] ?? '', w)));
      lines.push(
        <Text key={`${rowKey}-${line}`} color={color('paper')} bold={isHeader}>
          {text}
        </Text>,
      );
    }
    return lines;
  };

  const body: ReactNode[] = [
    <Text key="top" color={rule}>
      {edge('┌', '┬', '┐')}
    </Text>,
    ...renderRow(headers, 'head', true),
    <Text key="mid" color={rule}>
      {edge('├', '┼', '┤')}
    </Text>,
    ...rows.flatMap((row, r) => renderRow(row, `row-${r}`, false)),
    <Text key="bottom" color={rule}>
      {edge('└', '┴', '┘')}
    </Text>,
  ];
  return (
    <Box key={key} flexDirection="column" width={width}>
      {body}
    </Box>
  );
}

function renderList(token: Tokens.List, width: number, key: string): ReactNode {
  const start = typeof token.start === 'number' ? token.start : 1;
  const markers = token.items.map((item, i) => {
    if (item.task) return item.checked ? '[x] ' : '[ ] ';
    return token.ordered ? `${start + i}. ` : `${BULLET} `;
  });
  const markerWidth = Math.max(0, ...markers.map((m) => displayWidth(m)));
  const bodyWidth = Math.max(1, width - markerWidth);
  return (
    <Box key={key} flexDirection="column" width={width}>
      {token.items.map((item, i) => (
        <Box key={`${key}-${i}`} flexDirection="row" width={width}>
          <Box width={markerWidth} flexShrink={0}>
            <Text color={color('dim')}>{padEnd(markers[i] ?? '', markerWidth)}</Text>
          </Box>
          <Box flexDirection="column" width={bodyWidth}>
            {renderBlocks(item.tokens, bodyWidth, `${key}-${i}`)}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

function renderCode(token: Tokens.Code, width: number, key: string): ReactNode {
  const inner = Math.max(1, width - 2);
  const lines = token.text.split('\n').flatMap((line) => hardWrap(line, inner));
  return (
    <Box key={key} flexDirection="column" width={width}>
      {lines.map((line, i) => (
        <Text key={`${key}-${i}`} color={color('paper')} backgroundColor={color('graphite')}>
          {padEnd(`  ${line}`, width)}
        </Text>
      ))}
    </Box>
  );
}

function renderBlock(token: Token, width: number, key: string): ReactNode {
  const generic = token as Tokens.Generic;
  switch (token.type) {
    case 'space':
      return null;
    case 'heading': {
      const depth = (token as Tokens.Heading).depth;
      const tone = depth <= 2 ? 'ledger' : depth === 3 ? 'paper' : 'dim';
      return renderProse(flattenInline(generic.tokens), width, key, { color: color(tone), bold: true });
    }
    case 'paragraph':
      return renderProse(flattenInline(generic.tokens), width, key, { color: color('paper') });
    case 'text':
      return renderProse(
        generic.tokens ? flattenInline(generic.tokens) : [{ text: generic.text ?? '', style: {} }],
        width,
        key,
        { color: color('paper') },
      );
    case 'code':
      return renderCode(token as Tokens.Code, width, key);
    case 'list':
      return renderList(token as Tokens.List, width, key);
    case 'table':
      return renderTable(token as Tokens.Table, width, key);
    case 'blockquote':
      return (
        <Box
          key={key}
          width={width}
          flexDirection="column"
          borderStyle="single"
          borderColor={color('dim')}
          borderTop={false}
          borderBottom={false}
          borderRight={false}
          paddingLeft={1}
        >
          {renderBlocks(generic.tokens, Math.max(1, width - 2), key)}
        </Box>
      );
    case 'hr':
      return (
        <Text key={key} color={color('rule')}>
          {'─'.repeat(width)}
        </Text>
      );
    case 'html':
      return (
        <Box key={key} width={width}>
          <Text color={color('paper')}>{(generic.text ?? generic.raw ?? '').trimEnd()}</Text>
        </Box>
      );
    default:
      return generic.text ? (
        <Box key={key} width={width}>
          <Text color={color('paper')}>{generic.text}</Text>
        </Box>
      ) : null;
  }
}

function renderBlocks(tokens: readonly Token[] | undefined, width: number, keyPrefix: string): ReactNode[] {
  if (!tokens) return [];
  return tokens.map((token, index) => renderBlock(token, width, `${keyPrefix}-${index}`));
}

/**
 * Render Markdown text as an Ink tree laid out at `width` columns. Top-level blocks
 * are separated by one blank line; empty input renders nothing.
 */
export function render(text: string, width: number): ReactNode {
  if (text.trim() === '') return null;
  const columns = Math.max(1, Math.floor(width));
  const tokens = lexer(text);
  const blocks = tokens
    .map((token, index) => ({ node: renderBlock(token, columns, `b${index}`), index }))
    .filter((entry) => entry.node !== null);
  return (
    <Box flexDirection="column" width={columns}>
      {blocks.map((entry, position) => (
        <Box key={`top-${entry.index}`} flexDirection="column" width={columns} marginTop={position === 0 ? 0 : 1}>
          {entry.node}
        </Box>
      ))}
    </Box>
  );
}
