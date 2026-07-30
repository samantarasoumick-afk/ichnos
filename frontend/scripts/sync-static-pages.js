#!/usr/bin/env node
// Regenerates the marketing/legal HTML copies under frontend/public/ from
// their single source of truth in ../website/, instead of hand-editing two
// drifting copies of the same pages.
//
// Why frontend/public/ has copies at all: frontend/src/app/page.tsx falls
// back to serving /site.html when the Next.js app is hit directly (rather
// than through the nginx-routed marketing domain) - see that file's
// comment. The four legal pages are duplicated the same way so they're
// reachable same-origin from inside the app.
//
// This only runs when ../website is actually present next to frontend/,
// which is true for local dev and for the CI frontend-checks job (both
// have the full repo checked out). It's a deliberate no-op, not a failure,
// when it isn't - the production Docker image builds frontend/ in
// isolation (see frontend/Dockerfile's `context: ./frontend` in
// docker-compose.yml) and has no access to ../website at all, so it just
// uses whatever frontend/public/*.html was already committed. Run
// `npm run sync-static-pages` locally and commit the result before a
// release if you've touched anything under website/.

const fs = require("fs");
const path = require("path");

const WEBSITE_DIR = path.join(__dirname, "..", "..", "website");
const PUBLIC_DIR = path.join(__dirname, "..", "public");

// website/index.html -> frontend/public/site.html (renamed, since
// frontend/public/index.html would collide with Next.js's own routing);
// everything else copies over under its own name.
const FILES = [
  ["index.html", "site.html"],
  ["dpa.html", "dpa.html"],
  ["privacy.html", "privacy.html"],
  ["terms.html", "terms.html"],
  ["trust.html", "trust.html"],
];

if (!fs.existsSync(WEBSITE_DIR)) {
  console.log("[sync-static-pages] ../website not found next to frontend/ - skipping (expected inside the frontend-only Docker build context).");
  process.exit(0);
}

let changed = 0;
for (const [src, dest] of FILES) {
  const srcPath = path.join(WEBSITE_DIR, src);
  const destPath = path.join(PUBLIC_DIR, dest);

  if (!fs.existsSync(srcPath)) {
    console.warn(`[sync-static-pages] Expected website/${src} but it doesn't exist - skipping.`);
    continue;
  }

  const srcContent = fs.readFileSync(srcPath, "utf8");
  const destContent = fs.existsSync(destPath) ? fs.readFileSync(destPath, "utf8") : null;

  if (srcContent !== destContent) {
    fs.writeFileSync(destPath, srcContent);
    console.log(`[sync-static-pages] Updated public/${dest} from website/${src}`);
    changed += 1;
  }
}

if (changed === 0) {
  console.log("[sync-static-pages] frontend/public/*.html already matches website/*.html - nothing to do.");
}
