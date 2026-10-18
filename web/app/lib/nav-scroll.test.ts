import { describe, expect, it } from "vitest";

import { fadeEdges } from "./nav-scroll";

describe("fadeEdges", () => {
  it("fades nothing when the nav fits", () => {
    expect(fadeEdges(0, 300, 300)).toBeUndefined();
  });
  it("fades the edges that hide links", () => {
    expect(fadeEdges(0, 465, 328)).toBe("end");
    expect(fadeEdges(60, 465, 328)).toBe("start end");
    expect(fadeEdges(137, 465, 328)).toBe("start");
  });
});
