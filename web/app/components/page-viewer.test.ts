import { describe, expect, it } from "vitest";

import { clampZoom, imageScale, scaledUrl, stepZoom } from "./page-viewer";

describe("page viewer", () => {
  it("steps through the zoom levels from fit-to-width to 400%", () => {
    expect(stepZoom(1, 1)).toBe(1.5);
    expect(stepZoom(1.7, 1)).toBe(2);
    expect(stepZoom(1.7, -1)).toBe(1.5);
    expect(stepZoom(4, 1)).toBe(4);
    expect(stepZoom(1, -1)).toBe(1);
    expect(clampZoom(9)).toBe(4);
    expect(clampZoom(0.2)).toBe(1);
  });

  it("asks for a larger image only when the screen needs it", () => {
    expect(imageScale(800, 1000, 1)).toBe(1);
    expect(imageScale(800, 1000, 2)).toBe(2);
    expect(imageScale(3200, 1000, 1)).toBe(3);
  });

  it("adds the scale to the page URL and keeps its view", () => {
    expect(scaledUrl("/api/invoices/OCT-01/pages/1?view=canonical", 2)).toBe("/api/invoices/OCT-01/pages/1?view=canonical&scale=2");
    expect(scaledUrl("/api/invoices/OCT-01/pages/1", 3)).toBe("/api/invoices/OCT-01/pages/1?scale=3");
    expect(scaledUrl("/p.png", 1)).toBe("/p.png");
  });
});
