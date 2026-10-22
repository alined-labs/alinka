// Byte ranges for the files under /media/ (the pitch video), which the assets layer serves whole:
// it answers a Range request with 200 and the full body. Safari will not play an MP4 that way,
// it asks for bytes=0-1 and needs a 206, so index.ts answers /media/* itself and slices the file
// with the range read here. Pure, so the same node:test runner as frozen.test.ts covers it.

/** The inclusive byte span a Range header asks for, as RFC 9110 section 14.1.2 defines it. */
export interface Span {
  start: number;
  end: number;
}

/**
 * The single span a Range header asks for within a file of `size` bytes.
 * - `null`: serve the whole file with 200. That covers no header, a unit other than bytes, a
 *   malformed value and a list of several ranges, which RFC 9110 lets a server ignore.
 * - `"unsatisfiable"`: the span starts at or past the end of the file; the answer is 416.
 * The end is clamped to the last byte, so `bytes=0-` and an end past the file both work.
 */
export function parseRange(header: string | null, size: number): Span | "unsatisfiable" | null {
  if (!header) return null;
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (!m || (m[1] === "" && m[2] === "")) return null;
  const last = size - 1;
  if (m[1] === "") {
    // bytes=-N: the last N bytes.
    const n = Number(m[2]);
    if (n === 0 || size === 0) return "unsatisfiable";
    return { start: Math.max(0, size - n), end: last };
  }
  const start = Number(m[1]);
  const end = m[2] === "" ? last : Math.min(Number(m[2]), last);
  if (m[2] !== "" && Number(m[2]) < start) return null; // backwards, so malformed: serve it whole
  if (start > last) return "unsatisfiable";
  return { start, end };
}

/** The Content-Range value for a span of a file of `size` bytes, or for a 416 when `span` is null. */
export function contentRange(span: Span | null, size: number): string {
  return span ? `bytes ${span.start}-${span.end}/${size}` : `bytes */${size}`;
}
