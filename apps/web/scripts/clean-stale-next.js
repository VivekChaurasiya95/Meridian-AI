// Removes a stale Next.js build cache that the next command cannot reuse.
//
// `next build` and `next dev` share the `.next` directory but write
// incompatible manifests. Starting `dev` on top of a production `.next`
// produces MODULE_NOT_FOUND chunk errors, "Cannot read properties of
// undefined (reading '/_app')", RSC manifest corruption, and ENOENT
// manifest crashes. This guard deletes `.next` only when it holds
// production markers, so normal dev restarts keep their fast cache.
//
// Usage: node scripts/clean-stale-next.js [--force]
const fs = require("fs");
const path = require("path");

const dir = path.join(__dirname, "..", ".next");
const force = process.argv.includes("--force");
const productionMarkers = [
  "export-marker.json",
  "prerender-manifest.json",
  "required-server-files.json",
];

function isProductionCache() {
  return productionMarkers.some((marker) =>
    fs.existsSync(path.join(dir, marker)),
  );
}

if (force || isProductionCache()) {
  fs.rmSync(dir, { recursive: true, force: true });
  console.log(
    `[clean-stale-next] removed stale ${force ? "" : "production "}.next cache`,
  );
} else {
  console.log("[clean-stale-next] .next is dev-compatible, keeping cache");
}
