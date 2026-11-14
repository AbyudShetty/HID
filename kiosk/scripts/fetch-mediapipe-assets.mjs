// Copies the MediaPipe wasm runtime from node_modules and downloads the BlazeFace short-range model into public/mediapipe/
// (served locally so the kiosk works offline at the venue). Both are Apache-2.0. Usage: npm run assets
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = join(root, "public", "mediapipe");
const wasmSrc = join(root, "node_modules", "@mediapipe", "tasks-vision", "wasm");
const MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite";

mkdirSync(join(outDir, "wasm"), { recursive: true });
for (const f of readdirSync(wasmSrc)) copyFileSync(join(wasmSrc, f), join(outDir, "wasm", f));
console.log(`copied wasm runtime (${readdirSync(wasmSrc).length} files)`);

const modelPath = join(outDir, "blaze_face_short_range.tflite");
if (!existsSync(modelPath)) {
  const res = await fetch(MODEL_URL);
  if (!res.ok) throw new Error(`model download failed: ${res.status}`);
  writeFileSync(modelPath, Buffer.from(await res.arrayBuffer()));
}
const sha = createHash("sha256").update((await import("node:fs")).readFileSync(modelPath)).digest("hex");
console.log(`model: ${statSync(modelPath).size} bytes, sha256 ${sha}`);
