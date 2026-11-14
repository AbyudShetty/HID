// Drives the spike capture page in headless Chrome with a fake camera over the DevTools Protocol (no dependencies;
// uses Node's built-in WebSocket/fetch). Verifies the real browser pipeline: rVFC capture, createImageBitmap, the
// encode worker, the challenge renderer under an opaque overlay, bundle packing, and upload.
//
//   node tools/cdp_spike_e2e.mjs --n 10 --video data/fake_camera/face.y4m --operator-token T [--app http://localhost:5173]
//
// Prints one JSON object with per-session results and any browser console errors. Exit code 1 if any session failed.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const arg = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : def;
};
const N = Number(arg("n", "3"));
const APP = arg("app", "http://localhost:5173");
const VIDEO = arg("video", "");
const TOKEN = arg("operator-token", "");
const CHROME = arg("chrome", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe");
const PORT = Number(arg("port", "9333"));
const PALETTES = (arg("palettes", "P1,P2")).split(",");
const LOCK = arg("lock", "none");
const MEASURE = process.argv.includes("--measure");
const STALL_MS = Number(arg("stall-ms", "0")); // negative-path timing test; never liveness data

const profile = mkdtempSync(join(tmpdir(), "hid-cdp-"));
const chromeArgs = [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  "--use-fake-device-for-media-stream",
  "--use-fake-ui-for-media-stream",
  "--no-first-run",
  "--no-default-browser-check",
  "--window-size=1280,900",
  ...(VIDEO ? [`--use-file-for-fake-video-capture=${VIDEO}`] : []),
  "about:blank",
];
const chrome = spawn(CHROME, chromeArgs, { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const cleanup = () => {
  try {
    chrome.kill();
  } catch {}
};
process.on("exit", cleanup);

async function waitJson(url, tries = 60) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url);
      if (r.ok) return await r.json();
    } catch {}
    await sleep(250);
  }
  throw new Error(`timeout waiting for ${url}`);
}

await waitJson(`http://127.0.0.1:${PORT}/json/version`);
const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => {
  ws.onopen = res;
  ws.onerror = rej;
});
let nextId = 1;
const pending = new Map();
const consoleMsgs = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { resolve, reject } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
  } else if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type)) {
    consoleMsgs.push(`${m.params.type}: ${m.params.args.map((a) => a.value ?? a.description ?? "").join(" ")}`);
  } else if (m.method === "Runtime.exceptionThrown") {
    consoleMsgs.push(`exception: ${m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text}`);
  }
};
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? "evaluate failed");
  return r.result.value;
};
const waitFor = async (expression, timeoutMs, what) => {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (await evaluate(expression)) return;
    await sleep(100);
  }
  throw new Error(`timeout waiting for ${what}`);
};

await send("Page.enable");
await send("Runtime.enable");
const form = {
  subject_id: "S900", presenter_id: "S900", cls: "bona_fide", enrolled: true, claimed_badge_id: "", capture_procedure: "standard",
  pai_family: "none", pai_species: "none", instrument_id: "", lighting: "office", distance_cm: "50", glasses: false,
  skin_tone_bucket: "unreported", consent_id: "C-AUTOTEST", operator: "cdp", notes: "automated browser test, not real data",
};
const settings = { countdown: 0, palette: "", lock: LOCK, exposureTime: "", colorTemperature: "", fullscreen: false };
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `localStorage.setItem('hid_spike_form', ${JSON.stringify(JSON.stringify(form))});
           localStorage.setItem('hid_spike_settings', ${JSON.stringify(JSON.stringify(settings))});
           sessionStorage.setItem('hid_operator_token', ${JSON.stringify(TOKEN)});`,
});
await send("Page.navigate", { url: `${APP}/ops/spike` });
await waitFor(`!!document.querySelector('[data-testid=start-camera]')`, 20000, "spike page");
await evaluate(`document.querySelector('[data-testid=start-camera]').click()`);
await waitFor(`document.querySelector('[data-testid=camera-status]').textContent.startsWith('camera')`, 20000, "camera status");
const camStatus = await evaluate(`document.querySelector('[data-testid=camera-status]').textContent`);
if (camStatus !== "camera on") {
  console.log(JSON.stringify({ ok: false, camStatus, consoleMsgs }, null, 1));
  process.exit(1);
}
// wait for the detector (MediaPipe) to resolve one way or the other
await waitFor(`/MediaPipe ready|no detector/.test(document.body.innerText)`, 30000, "detector status");
const detector = await evaluate(`(document.body.innerText.match(/MediaPipe ready|no detector[^\\n]*/) || [''])[0]`);
await sleep(1500); // let a few detections accumulate

const results = [];
for (let i = 0; i < N; i++) {
  const palette = PALETTES[i % PALETTES.length];
  // set palette through the controlled select via the native setter + input event
  await evaluate(`(() => { const sel = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.text === 'server default'));
    const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(sel, ${JSON.stringify(palette)}); sel.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  await evaluate(`document.querySelector('[data-testid=${MEASURE ? "measure" : "record"}]').click()`);
  if (STALL_MS > 0) {
    await waitFor(`(() => { const s = document.querySelector('[data-testid=overlay]').style;
      return s.display === 'block' && s.background !== 'rgb(205, 205, 205)'; })()`, 15000, "first coloured segment");
    await evaluate(`(() => { const until = performance.now() + ${STALL_MS}; while (performance.now() < until) {} })()`);
  }
  await waitFor(`/^(uploaded|measured|failed)/.test(document.querySelector('[data-testid=status-message]').textContent)`, 30000, `session ${i + 1}`);
  const msg = await evaluate(`document.querySelector('[data-testid=status-message]').textContent`);
  const row = await evaluate(`(() => { const r = document.querySelector('[data-testid=log] tbody tr'); return r ? [...r.children].map(c => c.textContent) : null })()`);
  results.push({ palette, msg, row });
  await sleep(300);
}
const report = MEASURE ? await evaluate(`document.querySelector('[data-testid=report] pre')?.textContent ?? null`) : null;
const failed = results.filter((r) => STALL_MS > 0 ? !r.msg.includes("invalid measurement: CAPTURE_OVERRUN") : !/^(uploaded|measured)/.test(r.msg)).length;
console.log(JSON.stringify({ report: report ? JSON.parse(report) : null, ok: failed === 0, mode: STALL_MS > 0 ? "synthetic-stall-rejection" : "simulated-camera-capture", detector, camStatus, n: N, failed, results, consoleMsgs }, null, 1));
ws.close();
cleanup();
process.exit(failed === 0 ? 0 : 1);
