// Byte ranges for /media/* (ranges.ts). Same runner as frozen.test.ts:
//   node --test 'edge/src/*.test.ts'               (from the repo root)

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { contentRange, parseRange } from "./ranges.ts";

const SIZE = 1000;

describe("parseRange", () => {
  test("serves the whole file when no single byte range is asked for", () => {
    assert.equal(parseRange(null, SIZE), null);
    assert.equal(parseRange("", SIZE), null);
    assert.equal(parseRange("items=0-1", SIZE), null);
    assert.equal(parseRange("bytes=-", SIZE), null);
    assert.equal(parseRange("bytes=0-1,5-9", SIZE), null);
    assert.equal(parseRange("bytes=9-5", SIZE), null);
  });

  test("reads the probe Safari sends before playing a video", () => {
    assert.deepEqual(parseRange("bytes=0-1", SIZE), { start: 0, end: 1 });
  });

  test("clamps an open or overlong end to the last byte", () => {
    assert.deepEqual(parseRange("bytes=0-", SIZE), { start: 0, end: 999 });
    assert.deepEqual(parseRange("bytes=500-5000", SIZE), { start: 500, end: 999 });
  });

  test("reads a suffix as the last N bytes", () => {
    assert.deepEqual(parseRange("bytes=-100", SIZE), { start: 900, end: 999 });
    assert.deepEqual(parseRange("bytes=-5000", SIZE), { start: 0, end: 999 });
  });

  test("refuses a span that starts past the end, or an empty suffix", () => {
    assert.equal(parseRange("bytes=1000-", SIZE), "unsatisfiable");
    assert.equal(parseRange("bytes=-0", SIZE), "unsatisfiable");
  });
});

describe("contentRange", () => {
  test("names the span and the size, or only the size for a 416", () => {
    assert.equal(contentRange({ start: 0, end: 1 }, SIZE), "bytes 0-1/1000");
    assert.equal(contentRange(null, SIZE), "bytes */1000");
  });
});
