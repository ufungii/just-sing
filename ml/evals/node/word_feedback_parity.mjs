/** Run against a patched TS module: node word_feedback_parity.mjs /path/to/words.ts fixture.json */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const module = await import(pathToFileURL(process.argv[2]).href);
const fixture = JSON.parse(readFileSync(process.argv[3], 'utf8'));
assert.equal(module.WORD_FEEDBACK_VERSION, fixture.word_feedback_version);
assert.deepEqual(module.WORD_FEEDBACK_CONFIG, fixture.config);
assert.deepEqual(module.WORD_PITCH_CONFIG, fixture.pitch_config);
function compare(actual, expected, path) {
  if (typeof expected === 'number') {
    assert.ok(Math.abs(actual - expected) <= fixture.tolerance, `${path}: ${actual} != ${expected}`);
  } else if (Array.isArray(expected)) {
    assert.equal(actual.length, expected.length, path);
    expected.forEach((value, i) => compare(actual[i], value, `${path}[${i}]`));
  } else if (expected !== null && typeof expected === 'object') {
    assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort(), path);
    for (const key of Object.keys(expected)) compare(actual[key], expected[key], `${path}.${key}`);
  } else assert.equal(actual, expected, path);
}
for (const test of fixture.cases) compare(module.wordFeedback(test.input), test.expected, test.name);
console.log(`${fixture.cases.length} word feedback fixtures passed in TypeScript`);
