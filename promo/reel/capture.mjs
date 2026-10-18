/*
 * Captures the reel frame by frame and encodes it.
 *
 *   node promo/reel/capture.mjs                 # 1080x1920 -> promo/reel/out/alinka-reel.mp4
 *   node promo/reel/capture.mjs --landscape     # 1920x1080 -> promo/reel/out/alinka-reel-16x9.mp4
 *   node promo/reel/capture.mjs --still 31      # one PNG at t = 31 s, to check a frame
 *   node promo/reel/capture.mjs --pitch 02-flujo  # a pitch segment -> promo/reel/out/pitch/02-flujo.mp4
 *
 * Serves the repository root on a local port (the page loads the app's tokens from web/), drives
 * the system Chrome through the repo's Playwright, calls window.setTime(t) for each frame at
 * 30 fps and pipes the PNGs to ffmpeg: H.264, yuv420p, no audio. out/ is not committed.
 */
import { spawn } from "node:child_process";
import { createReadStream, mkdirSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const { chromium } = createRequire(new URL("../../web/package.json", import.meta.url))("@playwright/test");

const ROOT = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const OUT = join(ROOT, "promo", "reel", "out");
const FPS = 30;
const args = process.argv.slice(2);
const pitch = args.includes("--pitch") ? args[args.indexOf("--pitch") + 1] : null;
const landscape = args.includes("--landscape") || pitch !== null;
const stillAt = args.includes("--still") ? Number(args[args.indexOf("--still") + 1]) : null;
const [W, H] = landscape ? [1920, 1080] : [1080, 1920];

const TYPES = { ".json": "application/json", ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };

// Static files from the repository root only, GET only.
const server = createServer((req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname));
  const file = join(ROOT, path);
  if (req.method !== "GET" || !(file + sep).startsWith(ROOT + sep) && file !== ROOT) {
    res.writeHead(403).end();
    return;
  }
  try {
    if (!statSync(file).isFile()) throw new Error("not a file");
  } catch {
    res.writeHead(404).end();
    return;
  }
  res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const port = server.address().port;

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
const problems = [];
page.on("console", (m) => m.type() === "error" && problems.push(m.text()));
page.on("pageerror", (e) => problems.push(e.message));
const target = pitch ? `pitch.html?seg=${encodeURIComponent(pitch)}` : `index.html${landscape ? "?format=landscape" : ""}`;
await page.goto(`http://127.0.0.1:${port}/promo/reel/${target}`, { waitUntil: "networkidle" });
await page.evaluate(() => window.reelReady);
const frame = page.locator("#frame");

try {
  if (stillAt !== null) {
    const file = join(OUT, `still-${pitch ?? (landscape ? "16x9" : "9x16")}-${stillAt}.png`);
    await page.evaluate((t) => window.setTime(t), stillAt);
    await frame.screenshot({ path: file });
    console.log(file);
  } else {
    const duration = await page.evaluate(() => window.DURATION);
    const frames = Math.round(duration * FPS);
    if (pitch) mkdirSync(join(OUT, "pitch"), { recursive: true });
    const file = pitch ? join(OUT, "pitch", `${pitch}.mp4`) : join(OUT, landscape ? "alinka-reel-16x9.mp4" : "alinka-reel.mp4");
    const ffmpeg = spawn(
      "ffmpeg",
      ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", String(FPS),
        "-movflags", "+faststart", file],
      { stdio: ["pipe", "inherit", "inherit"] },
    );
    const done = new Promise((ok, fail) => ffmpeg.on("close", (code) => (code === 0 ? ok() : fail(new Error(`ffmpeg exited ${code}`)))));
    for (let i = 0; i < frames; i++) {
      await page.evaluate((t) => window.setTime(t), i / FPS);
      const png = await frame.screenshot({ type: "png" });
      if (!ffmpeg.stdin.write(png)) await new Promise((ok) => ffmpeg.stdin.once("drain", ok));
      if (i % 150 === 0) console.log(`frame ${i}/${frames}`);
    }
    ffmpeg.stdin.end();
    await done;
    console.log(file);
  }
  if (problems.length) console.log("page problems:", problems);
} finally {
  await browser.close();
  server.close();
}
