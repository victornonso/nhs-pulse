import { mkdir, copyFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../", import.meta.url));
await mkdir(root + "public", { recursive: true });
await copyFile(
  root + "node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs",
  root + "public/maplibre-worker.mjs",
);
await copyFile(
  root + "node_modules/maplibre-gl/LICENSE.txt",
  root + "public/maplibre-LICENSE.txt",
);
