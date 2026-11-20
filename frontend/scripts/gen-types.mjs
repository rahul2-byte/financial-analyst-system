// Generates src/protocol/generated.ts from the committed JSON schemas.
// Regenerate with: npm run gen:types   (check: npm run gen:types:check)
//
// Both schemas are merged into one document before compilation so that
// json-schema-to-typescript emits a single, self-consistent set of types.
// Compiling them separately would duplicate the shared event definitions and
// reuse the auto-generated helper aliases (`Type1`, `Label2`, ...) ambiguously.
import { compileFromFile } from 'json-schema-to-typescript';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, '..');
const repoRoot = path.resolve(frontendRoot, '..');
const outFile = path.join(frontendRoot, 'src/protocol/generated.ts');

const EVENT_SCHEMA = 'protocol/schema/research_event.schema.json';
const PROTOCOL_SCHEMA = 'protocol/schema/protocol.schema.json';

const HEADER = `// GENERATED — do not edit. Regenerate with \`npm run gen:types\`.
// Sources: ${EVENT_SCHEMA}, ${PROTOCOL_SCHEMA}
// Schema title: "FIN-AI bridge protocol v1" (PROTOCOL_VERSION 1).
// Hand-written additions belong in src/protocol/{events,methods,version}.ts.
`;

function readSchema(relativePath) {
  const absolute = path.join(repoRoot, relativePath);
  if (!existsSync(absolute)) throw new Error(`schema not found: ${absolute}`);
  return JSON.parse(readFileSync(absolute, 'utf8'));
}

/** Stable structural serialization, used to detect real definition conflicts. */
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/**
 * json-schema-to-typescript turns a property with a `default` into an optional
 * member, which would also make the `type` discriminant optional. The Python
 * models always serialize `type` (it is also in `required`), so drop the
 * redundant `default` next to a `const`.
 */
function dropConstDefaults(node) {
  if (Array.isArray(node)) return node.map(dropConstDefaults);
  if (node === null || typeof node !== 'object') return node;
  const result = {};
  for (const [key, value] of Object.entries(node)) {
    if (key === 'default' && Object.hasOwn(node, 'const')) continue;
    result[key] = dropConstDefaults(value);
  }
  return result;
}

/**
 * A `const` property must be required in the generated type, otherwise the
 * `type` discriminant would come out optional (`type?: 'run.started'`) and the
 * union would not narrow. Pydantic always serializes these constants, even
 * though it lists them outside `required` when they have a default.
 */
function requireConstProperties(node) {
  if (Array.isArray(node)) return node.map(requireConstProperties);
  if (node === null || typeof node !== 'object') return node;

  const result = {};
  for (const [key, value] of Object.entries(node)) {
    result[key] = requireConstProperties(value);
  }

  if (result.properties !== null && typeof result.properties === 'object') {
    const required = Array.isArray(result.required) ? [...result.required] : [];
    for (const [key, value] of Object.entries(result.properties)) {
      if (
        value !== null &&
        typeof value === 'object' &&
        Object.hasOwn(value, 'const') &&
        !required.includes(key)
      ) {
        required.push(key);
      }
    }
    if (required.length > 0) result.required = required;
  }

  return result;
}

function buildCombinedSchema() {
  const events = readSchema(EVENT_SCHEMA);
  const protocol = readSchema(PROTOCOL_SCHEMA);

  const defs = { ...protocol.$defs };
  const conflicts = [];

  for (const [name, definition] of Object.entries(events.$defs ?? {})) {
    const existing = defs[name];
    if (existing !== undefined && canonical(existing) !== canonical(definition)) {
      conflicts.push(name);
      continue;
    }
    if (existing === undefined) defs[name] = definition;
  }

  if (conflicts.length > 0) {
    throw new Error(
      `event definitions disagree with protocol.schema.json: ${conflicts.join(', ')} — ` +
        'regenerate both schemas from the Python models before running gen:types',
    );
  }

  defs.ResearchEvent = {
    title: 'ResearchEvent',
    discriminator: events.discriminator,
    oneOf: events.oneOf,
  };

  return requireConstProperties(
    dropConstDefaults({
      $schema: protocol.$schema ?? 'https://json-schema.org/draft/2020-12/schema',
      title: 'FINAIProtocol',
      type: 'object',
      additionalProperties: true,
      // The root object exists only to force `unreachableDefinitions` to emit
      // every $defs entry; nothing consumes it.
      properties: {
        event: { $ref: '#/$defs/ResearchEvent' },
      },
      $defs: defs,
    }),
  );
}

function firstDifference(actual, expected) {
  const a = actual.split('\n');
  const b = expected.split('\n');
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    if (a[i] !== b[i]) {
      return `line ${i + 1}:\n  committed: ${String(a[i]).slice(0, 200)}\n  fresh:     ${String(b[i]).slice(0, 200)}`;
    }
  }
  return 'files differ in trailing bytes';
}

async function generate() {
  const schema = buildCombinedSchema();
  const scratch = mkdtempSync(path.join(tmpdir(), 'finai-gen-types-'));
  const schemaFile = path.join(scratch, 'combined.schema.json');
  try {
    writeFileSync(schemaFile, `${JSON.stringify(schema, null, 2)}\n`, 'utf8');
    const compiled = await compileFromFile(schemaFile, {
      name: 'FINAIProtocol',
      cwd: scratch,
      bannerComment: '',
      unreachableDefinitions: true,
      style: { singleQuote: true, semi: true, tabWidth: 2 },
    });
    return `${HEADER}\n${compiled.trim()}\n`;
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

const check = process.argv.includes('--check');
const generated = await generate();

if (!check) {
  writeFileSync(outFile, generated, 'utf8');
  console.log(`wrote ${path.relative(repoRoot, outFile)} (${generated.split('\n').length} lines)`);
} else if (!existsSync(outFile)) {
  console.error(`missing ${path.relative(repoRoot, outFile)} — run: npm run gen:types`);
  process.exit(1);
} else {
  const committed = readFileSync(outFile, 'utf8');
  if (committed === generated) {
    console.log('generated types are up to date');
  } else {
    console.error(
      `generated types are stale (${path.relative(repoRoot, outFile)}):\n` +
        `${firstDifference(committed, generated)}\n` +
        'run: npm run gen:types',
    );
    process.exitCode = 1;
  }
}
