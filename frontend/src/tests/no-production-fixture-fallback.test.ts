/**
 * Structural guard: production code must never reach test fixtures.
 *
 * The behavioural tests assert that empty and failed responses render honest
 * states. This test closes the other half of the rule by inspecting the source
 * tree directly: no module outside `src/tests` may import from the fixtures,
 * and no production module may carry a hard-coded stand-in for live
 * intelligence.
 *
 * A file-system check rather than a runtime one, because the failure mode it
 * guards against — someone adding `?? SAMPLE_DATA` during a demo — would not
 * necessarily be exercised by any behavioural test.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = join(process.cwd(), 'src');
const TEST_DIRECTORY = join(SRC, 'tests');

function sourceFiles(directory: string): string[] {
  const results: string[] = [];
  for (const entry of readdirSync(directory)) {
    const full = join(directory, entry);
    if (statSync(full).isDirectory()) {
      results.push(...sourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry)) {
      results.push(full);
    }
  }
  return results;
}

/** Every source file that ships in the production bundle. */
function productionFiles(): string[] {
  return sourceFiles(SRC).filter(
    (file) => !file.startsWith(TEST_DIRECTORY) && !/\.test\.tsx?$/.test(file),
  );
}

describe('no production fixture fallback', () => {
  it('finds production source files to inspect', () => {
    // Guards the guard: a path change that silences this suite would be worse
    // than the defect it looks for.
    const files = productionFiles();
    expect(files.length).toBeGreaterThan(20);
    expect(files.some((file) => file.includes(`features${sep}overview`))).toBe(true);
  });

  it('never imports test fixtures from production code', () => {
    const offenders: string[] = [];

    for (const file of productionFiles()) {
      const source = readFileSync(file, 'utf-8');
      if (/from\s+['"][^'"]*tests\/fixtures['"]/.test(source)) {
        offenders.push(relative(SRC, file));
      }
      if (/from\s+['"][^'"]*tests\/harness['"]/.test(source)) {
        offenders.push(relative(SRC, file));
      }
    }

    expect(offenders).toEqual([]);
  });

  it('never falls back to a hard-coded stand-in for live intelligence', () => {
    // Patterns that would substitute invented data when the API gives none.
    const forbidden: Array<[RegExp, string]> = [
      [/\?\?\s*(MOCK|SAMPLE|DEMO|FAKE|PLACEHOLDER|DUMMY)_/i, 'nullish fallback to sample data'],
      [/\|\|\s*(MOCK|SAMPLE|DEMO|FAKE|PLACEHOLDER|DUMMY)_/i, 'boolean fallback to sample data'],
      [/const\s+(MOCK|SAMPLE|DEMO|FAKE|DUMMY)_[A-Z_]+\s*(:|=)/, 'sample data constant'],
      [/TEST FIXTURE/, 'test fixture marker'],
      [/lorem ipsum/i, 'placeholder prose'],
    ];

    const offenders: string[] = [];

    for (const file of productionFiles()) {
      const source = readFileSync(file, 'utf-8');
      for (const [pattern, description] of forbidden) {
        if (pattern.test(source)) {
          offenders.push(`${relative(SRC, file)}: ${description}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it('routes every network call through the api module', () => {
    // A stray `fetch` outside src/api would bypass error normalisation, the
    // bearer token and the 401 refresh path.
    const offenders: string[] = [];
    const apiDirectory = join(SRC, 'api');

    for (const file of productionFiles()) {
      if (file.startsWith(apiDirectory)) continue;
      const source = readFileSync(file, 'utf-8');
      // Ignore the word inside comments and identifiers such as `refetch`.
      if (/(?<![A-Za-z.])fetch\s*\(/.test(source)) {
        offenders.push(relative(SRC, file));
      }
    }

    expect(offenders).toEqual([]);
  });

  it('keeps severity colours out of ad-hoc class strings', () => {
    // Severity colour must come from lib/risk descriptors so one colour keeps
    // one meaning. A raw hex severity value in a component is a drift risk.
    const rawSeverityHex = /#(f04438|ef6820|f5b546|17b26a)/i;
    const allowed = new Set([
      join('lib', 'risk.ts'),
      join('components', 'maps', 'SomaliaMap.tsx'), // MapLibre paint expressions
      join('styles.css'),
    ]);

    const offenders: string[] = [];
    for (const file of productionFiles()) {
      const relativePath = relative(SRC, file);
      if (allowed.has(relativePath)) continue;
      if (rawSeverityHex.test(readFileSync(file, 'utf-8'))) {
        offenders.push(relativePath);
      }
    }

    expect(offenders).toEqual([]);
  });
});
