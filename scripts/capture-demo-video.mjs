import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..");
const packageDir = process.env.PLAYWRIGHT_PACKAGE_DIR;
const { chromium } = packageDir ? require(packageDir) : require("playwright");

const appUrl = process.env.DEMO_APP_URL || "http://127.0.0.1:5173/";
const scenesPath = path.resolve(
  process.env.DEMO_SCENES_PATH || path.join(projectRoot, "docs", "video", "demo-scenes.json"),
);
const outputDir = path.resolve(
  process.env.DEMO_VIDEO_WORK_DIR || path.join(projectRoot, "output", "demo-video", "work"),
);
const outputWebm = path.join(outputDir, "bidops-demo-capture.webm");
const scenes = JSON.parse(await fs.readFile(scenesPath, "utf8"));

await fs.mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
  args: ["--disable-gpu", "--hide-scrollbars"],
});
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
  recordVideo: {
    dir: outputDir,
    size: { width: 1280, height: 720 },
  },
});
const page = await context.newPage();
const video = page.video();
const browserErrors = [];

page.on("console", (message) => {
  const sourceUrl = message.location().url || "";
  if (message.type() === "error" && !sourceUrl.endsWith("/favicon.ico")) {
    browserErrors.push(`console: ${message.text()}`);
  }
});
page.on("pageerror", (error) => browserErrors.push(`page: ${error.message}`));
page.on("requestfailed", (request) => {
  if (!request.url().includes("favicon")) {
    browserErrors.push(`network: ${request.method()} ${request.url()} ${request.failure()?.errorText || ""}`);
  }
});

function slideMarkup(scene, index) {
  const common = `
    <div class="mark"><span>G</span></div>
    <div class="eyebrow">GE BIZ BID CONTROL</div>
    <div class="scene">${String(index + 1).padStart(2, "0")} / ${scenes.length}</div>
  `;

  let detail = "";
  if (scene.id === "responsibility") {
    detail = `
      <div class="responsibility-grid">
        <article><small>LLM</small><strong>Interpret language</strong><p>Typed requirements and semantic changes</p></article>
        <article><small>DETERMINISTIC</small><strong>Decide operational state</strong><p>Evidence, gates, coverage, tasks and deadlines</p></article>
        <article><small>HUMAN</small><strong>Approve and submit</strong><p>Review ambiguity and retain final authority</p></article>
      </div>`;
  } else if (scene.id === "validation") {
    detail = `
      <div class="validation-grid">
        <article><strong>64</strong><span>backend tests</span></article>
        <article><strong>4</strong><span>frontend tests</span></article>
        <article><strong>9 / 9</strong><span>deterministic benchmark</span></article>
        <article><strong>PASS</strong><span>live Bedrock R17 path</span></article>
      </div>
      <p class="caveat">Unseen extraction remains a measured limitation and requires human review.</p>`;
  } else if (scene.id === "close") {
    detail = `<div class="closing-flow"><span>CHANGE</span><b>→</b><span>IMPACT</span><b>→</b><span>RECOVERY</span></div>`;
  }

  return `<!doctype html>
    <html><head><meta charset="utf-8"><style>
      *{box-sizing:border-box} html,body{margin:0;width:100%;height:100%;overflow:hidden}
      body{font-family:Inter,"Segoe UI",Arial,sans-serif;color:#f8fafc;background:
        radial-gradient(circle at 78% 20%,rgba(51,115,96,.3),transparent 34%),
        radial-gradient(circle at 18% 85%,rgba(221,107,76,.22),transparent 32%),
        linear-gradient(135deg,#0e1726 0%,#111d2e 52%,#122a2a 100%)}
      body:after{content:"";position:absolute;inset:0;opacity:.07;background-image:linear-gradient(rgba(255,255,255,.6) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.6) 1px,transparent 1px);background-size:48px 48px}
      .frame{position:relative;z-index:1;height:100%;padding:58px 72px;display:flex;flex-direction:column;justify-content:center}
      .mark{position:absolute;top:44px;left:72px;width:48px;height:48px;border-radius:14px;background:#2f7d65;display:grid;place-items:center;box-shadow:0 12px 32px rgba(0,0,0,.25)}
      .mark span{font-size:24px;font-weight:900}.eyebrow{position:absolute;top:57px;left:136px;font-size:13px;font-weight:800;letter-spacing:.19em;color:#9db9ae}
      .scene{position:absolute;top:59px;right:72px;color:#92a2b8;font-size:13px;letter-spacing:.12em}
      h1{font-size:${scene.id === "title" || scene.id === "close" ? "68px" : "52px"};line-height:1.02;max-width:1040px;margin:0 0 22px;letter-spacing:-.045em}
      .accent{height:5px;width:84px;background:#e06c4e;border-radius:8px;margin-bottom:24px}
      .subtitle{font-size:24px;line-height:1.45;color:#c8d3df;max-width:980px;margin:0}
      .responsibility-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:38px}
      article{padding:24px;border:1px solid rgba(255,255,255,.12);border-radius:18px;background:rgba(255,255,255,.055)}
      article small{display:block;color:#7fd0b3;font-weight:800;letter-spacing:.13em;margin-bottom:13px}
      article strong{font-size:21px} article p{color:#aab8c7;line-height:1.5;margin:10px 0 0}
      .validation-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:38px}
      .validation-grid article{text-align:center}.validation-grid strong{display:block;color:#7fd0b3;font-size:38px;margin-bottom:8px}.validation-grid span{color:#c8d3df}
      .caveat{color:#f4b09b;margin-top:20px;font-size:16px}
      .closing-flow{display:flex;align-items:center;gap:18px;margin-top:42px}.closing-flow span{padding:14px 22px;border-radius:12px;background:rgba(255,255,255,.08);font-weight:800;letter-spacing:.12em}.closing-flow b{color:#e06c4e;font-size:28px}
    </style></head><body><main class="frame">${common}<div class="accent"></div><h1>${scene.title}</h1><p class="subtitle">${scene.caption}</p>${detail}</main></body></html>`;
}

async function showLowerThird(scene, index) {
  await page.evaluate(
    ({ title, caption, current, total }) => {
      document.getElementById("demo-video-caption")?.remove();
      const overlay = document.createElement("aside");
      overlay.id = "demo-video-caption";
      overlay.setAttribute("aria-hidden", "true");
      overlay.innerHTML = `<div class="demo-video-kicker">${String(current).padStart(2, "0")} / ${total}</div><strong>${title}</strong><span>${caption}</span>`;
      Object.assign(overlay.style, {
        position: "fixed",
        left: "32px",
        right: "32px",
        bottom: "22px",
        zIndex: "2147483647",
        display: "grid",
        gridTemplateColumns: "88px 310px 1fr",
        alignItems: "center",
        gap: "18px",
        minHeight: "78px",
        padding: "15px 22px",
        border: "1px solid rgba(255,255,255,.18)",
        borderRadius: "16px",
        background: "linear-gradient(90deg,rgba(12,23,38,.97),rgba(17,42,42,.95))",
        color: "#f8fafc",
        boxShadow: "0 16px 48px rgba(0,0,0,.32)",
        fontFamily: "Inter, Segoe UI, Arial, sans-serif",
      });
      const kicker = overlay.querySelector(".demo-video-kicker");
      Object.assign(kicker.style, { color: "#7fd0b3", fontWeight: "800", letterSpacing: ".12em", fontSize: "12px" });
      const strong = overlay.querySelector("strong");
      Object.assign(strong.style, { fontSize: "18px", lineHeight: "1.25" });
      const span = overlay.querySelector("span");
      Object.assign(span.style, { color: "#c8d3df", fontSize: "15px", lineHeight: "1.4" });
      document.body.appendChild(overlay);
    },
    { title: scene.title, caption: scene.caption, current: index + 1, total: scenes.length },
  );
}

async function scrollToHeading(name) {
  const heading = page.getByRole("heading", { name, exact: true }).first();
  await heading.evaluate((element) => {
    const target = element.getBoundingClientRect().top + window.scrollY - 260;
    window.scrollTo({ top: target, behavior: "auto" });
  });
  await page.waitForTimeout(450);
}

async function resetMainFixture() {
  if (!page.url().startsWith(appUrl)) await page.goto(appUrl, { waitUntil: "domcontentloaded" });
  await page.getByText("Operational Feasibility", { exact: true }).first().waitFor({ state: "visible", timeout: 15000 });
  const selector = page.getByLabel("Select demo scenario");
  await selector.selectOption({ label: "Main corrigendum demo" });
  await page.waitForTimeout(900);
  await page.locator('button[title="Reset demo"]').click();
  await page.getByText("FEASIBLE", { exact: true }).first().waitFor({ state: "visible", timeout: 15000 });
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.waitForTimeout(500);
}

async function actionFor(scene, index) {
  switch (scene.id) {
    case "title":
    case "close":
      await page.setContent(slideMarkup(scene, index), { waitUntil: "domcontentloaded" });
      return true;
    case "control_room":
      await page.goto(appUrl, { waitUntil: "domcontentloaded" });
      await resetMainFixture();
      break;
    case "initial_metrics":
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
      break;
    case "coverage":
      await scrollToHeading("Submission Coverage");
      break;
    case "r17_source": {
      const row = page.getByRole("row").filter({ hasText: "R17" }).filter({ hasText: "three personnel" }).first();
      await row.scrollIntoViewIfNeeded();
      await row.click();
      await page.waitForTimeout(700);
      break;
    }
    case "corrigendum_intro":
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
      await page.waitForTimeout(900);
      break;
    case "workflow":
      await showLowerThird(scene, index);
      await page.waitForTimeout(2200);
      await page.getByRole("button", { name: /Apply Corrigendum #2/ }).click();
      await page.getByText("RECOVERABLE", { exact: true }).first().waitFor({ state: "visible", timeout: 60000 });
      return true;
    case "recoverable_metrics":
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
      break;
    case "candidate":
      await scrollToHeading("Evidence gap review");
      break;
    case "recovery_tasks":
      await scrollToHeading("Recovery Actions");
      break;
    case "impact_chain":
      await scrollToHeading("Impact Chain");
      break;
    case "blocked":
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
      await page.getByLabel("Select demo scenario").selectOption({ label: "BLOCKED · no fourth engineer" });
      await page.getByText("BLOCKED", { exact: true }).first().waitFor({ state: "visible", timeout: 15000 });
      break;
    case "uncertain":
      await page.getByLabel("Select demo scenario").selectOption({ label: "UNCERTAIN · ambiguous clause" });
      await page.getByText("UNCERTAIN", { exact: true }).first().waitFor({ state: "visible", timeout: 15000 });
      break;
    case "responsibility":
      await page.getByLabel("Select demo scenario").selectOption({ label: "Main corrigendum demo" });
      await page.getByText("FEASIBLE", { exact: true }).first().waitFor({ state: "visible", timeout: 15000 });
      await page.setContent(slideMarkup(scene, index), { waitUntil: "domcontentloaded" });
      return true;
    case "validation":
      await page.setContent(slideMarkup(scene, index), { waitUntil: "domcontentloaded" });
      return true;
    default:
      break;
  }
  await showLowerThird(scene, index);
  return true;
}

let captureFailure;
try {
  for (let index = 0; index < scenes.length; index += 1) {
    const scene = scenes[index];
    console.log(`Scene ${String(index + 1).padStart(2, "0")}/${scenes.length}: ${scene.title}`);
    const startedAt = Date.now();
    await actionFor(scene, index);
    const remaining = scene.duration_ms - (Date.now() - startedAt);
    if (remaining > 0) await page.waitForTimeout(remaining);
  }
} catch (error) {
  captureFailure = error;
} finally {
  await context.close();
}

await video.saveAs(outputWebm);
await browser.close();
if (captureFailure) throw captureFailure;
if (browserErrors.length) {
  await fs.writeFile(path.join(outputDir, "browser-errors.txt"), browserErrors.join("\n"), "utf8");
  console.warn(`Capture completed with ${browserErrors.length} browser error(s).`);
} else {
  await fs.writeFile(path.join(outputDir, "browser-errors.txt"), "No browser errors captured.\n", "utf8");
}
console.log(outputWebm);
