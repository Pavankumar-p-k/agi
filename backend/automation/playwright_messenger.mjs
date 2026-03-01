import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { chromium, firefox } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = "true";
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function jsonOut(payload) {
  // Last line must be parseable JSON for Python caller.
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function waitAnyVisible(page, selectors, timeoutMs = 30000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    for (const selector of selectors) {
      try {
        const el = await page.$(selector);
        if (el) return selector;
      } catch {
        // Navigation can replace execution context; continue polling.
      }
    }
    await page.waitForTimeout(300).catch(() => {});
  }
  return null;
}

async function clickAny(page, selectors, timeoutMs = 5000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    for (const selector of selectors) {
      try {
        const el = await page.$(selector);
        if (el) {
          await el.click({ timeout: 1000 }).catch(() => {});
          return true;
        }
      } catch {
        // Ignore transient context/navigation errors during polling.
      }
    }
    await page.waitForTimeout(200).catch(() => {});
  }
  return false;
}

async function fillAny(page, selectors, value, timeoutMs = 8000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    for (const selector of selectors) {
      try {
        const el = await page.$(selector);
        if (el) {
          await el.click({ timeout: 1000 }).catch(() => {});
          await el.fill("").catch(() => {});
          await el.type(value, { delay: 10 }).catch(() => {});
          return true;
        }
      } catch {
        // Ignore transient context/navigation errors during polling.
      }
    }
    await page.waitForTimeout(250).catch(() => {});
  }
  return false;
}

async function isInstagramLoginPage(page) {
  if (page.url().includes("accounts/login")) return true;
  const loginForm = await page.$('input[name="username"], input[name="password"]');
  return !!loginForm;
}

async function whatsappSend(page, target, message, timeoutMs) {
  const digits = String(target || "").replace(/[^\d]/g, "");
  if (!digits) {
    return { success: false, error: "Target phone number required for Playwright send." };
  }

  const url = `https://web.whatsapp.com/send?phone=${digits}&text=${encodeURIComponent(message || "")}`;
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });

  const loginSel = await waitAnyVisible(
    page,
    [
      'canvas[aria-label*="Scan"]',
      'div[data-ref] canvas',
      'div[role="button"][aria-label*="Log"]',
    ],
    6000
  );
  if (loginSel) {
    return { success: false, error: "login_required_whatsapp" };
  }

  const invalidSel = await waitAnyVisible(
    page,
    [
      'div[role="alert"]',
      '[data-testid="alert-phone-number"]',
      'span:has-text("Phone number shared via url is invalid")',
    ],
    3000
  );
  if (invalidSel) {
    return { success: false, error: "invalid_phone_or_chat_not_found" };
  }

  const composerSelectors = [
    'footer div[contenteditable="true"]',
    'div[contenteditable="true"][data-tab]',
  ];
  const readySel = await waitAnyVisible(page, composerSelectors, 25000);
  if (!readySel) {
    return { success: false, error: "chat_not_ready" };
  }

  const composer = await page.$(readySel);
  if (!composer) return { success: false, error: "composer_missing" };
  await composer.click({ timeout: 1000 }).catch(() => {});

  // URL pre-fills text, but ensure text exists in composer.
  const composerText = (await composer.innerText().catch(() => "")) || "";
  if (!composerText.trim() && message) {
    await composer.type(message, { delay: 10 }).catch(() => {});
  }

  const clickedSend = await clickAny(page, [
    'button span[data-icon="send"]',
    'button[aria-label="Send"]',
    'button[data-testid="compose-btn-send"]',
  ]);
  if (!clickedSend) {
    await page.keyboard.press("Enter").catch(() => {});
  }

  await page.waitForTimeout(1200);
  return { success: true };
}

async function whatsappLogin(page, timeoutMs) {
  await page.goto("https://web.whatsapp.com/", {
    waitUntil: "domcontentloaded",
    timeout: timeoutMs,
  });
  const readySel = await waitAnyVisible(
    page,
    [
      'footer div[contenteditable="true"]',
      'div[contenteditable="true"][data-tab]',
    ],
    timeoutMs
  );
  if (readySel) return { success: true };
  return { success: false, error: "login_timeout_whatsapp" };
}

async function instagramSend(page, target, message, timeoutMs) {
  const username = String(target || "").trim().replace(/^@+/, "");
  if (!username) return { success: false, error: "instagram_username_required" };

  await page.goto("https://www.instagram.com/direct/new/", {
    waitUntil: "domcontentloaded",
    timeout: timeoutMs,
  });

  if (await isInstagramLoginPage(page)) {
    return { success: false, error: "login_required_instagram" };
  }

  const searchSelectors = [
    'input[name="queryBox"]',
    'input[placeholder="Search..."]',
    'input[aria-label="Search input"]',
  ];
  const hasSearch = await fillAny(page, searchSelectors, username, 12000);
  if (!hasSearch) return { success: false, error: "instagram_search_box_not_found" };

  await page.waitForTimeout(1200);
  const targetRegex = new RegExp(`^${escapeRegExp(username)}$`, "i");
  const candidate = page.getByText(targetRegex).first();
  if ((await candidate.count()) > 0) {
    await candidate.click().catch(() => {});
  } else {
    // Fallback click first search result row/checkbox.
    await clickAny(page, [
      'div[role="dialog"] div[role="button"]',
      'div[role="dialog"] input[type="checkbox"]',
    ], 5000);
  }

  const nextBtn = page.getByRole("button", { name: /chat|next/i }).first();
  if ((await nextBtn.count()) > 0) {
    await nextBtn.click().catch(() => {});
  } else {
    return { success: false, error: "instagram_next_button_not_found" };
  }

  const messageSelectors = [
    'textarea[placeholder="Message..."]',
    'div[contenteditable="true"][aria-label="Message"]',
    'div[contenteditable="true"]',
  ];
  const hasMessageBox = await fillAny(page, messageSelectors, message || "", 15000);
  if (!hasMessageBox) return { success: false, error: "instagram_message_box_not_found" };

  const sent = await clickAny(page, [
    'div[role="button"]:has-text("Send")',
    'button:has-text("Send")',
  ], 4000);
  if (!sent) await page.keyboard.press("Enter").catch(() => {});

  await page.waitForTimeout(1200);
  return { success: true };
}

async function instagramLogin(page, timeoutMs) {
  await page.goto("https://www.instagram.com/", {
    waitUntil: "domcontentloaded",
    timeout: timeoutMs,
  });
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (!(await isInstagramLoginPage(page))) return { success: true };
    await page.waitForTimeout(800);
  }
  return { success: false, error: "login_timeout_instagram" };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const platform = String(args.platform || "").toLowerCase();
  const mode = String(args.mode || "send").toLowerCase();
  const target = String(args.target || "");
  const message = String(args.message || "");
  const browser = String(args.browser || "chromium").toLowerCase();
  const timeoutMs = Number(args.timeout_ms || 60000);

  const profileDir = path.join(__dirname, "..", "data", "playwright-profile");
  fs.mkdirSync(profileDir, { recursive: true });

  const result = { success: false, platform, mode, error: "" };
  let context;
  try {
    if (browser === "firefox") {
      context = await firefox.launchPersistentContext(profileDir, {
        headless: false,
        viewport: { width: 1366, height: 900 },
      });
    } else if (browser === "chrome") {
      context = await chromium.launchPersistentContext(profileDir, {
        channel: "chrome",
        headless: false,
        viewport: { width: 1366, height: 900 },
      });
    } else if (browser === "msedge" || browser === "edge") {
      context = await chromium.launchPersistentContext(profileDir, {
        channel: "msedge",
        headless: false,
        viewport: { width: 1366, height: 900 },
      });
    } else {
      // Default: Playwright Chromium (works even when Edge/Chrome channels are missing)
      context = await chromium.launchPersistentContext(profileDir, {
        headless: false,
        viewport: { width: 1366, height: 900 },
      });
    }
    const page = context.pages()[0] || (await context.newPage());

    if (platform === "whatsapp" && mode === "send") {
      Object.assign(result, await whatsappSend(page, target, message, timeoutMs));
    } else if (platform === "instagram" && mode === "send") {
      Object.assign(result, await instagramSend(page, target, message, timeoutMs));
    } else if (platform === "whatsapp" && mode === "login") {
      Object.assign(result, await whatsappLogin(page, timeoutMs));
    } else if (platform === "instagram" && mode === "login") {
      Object.assign(result, await instagramLogin(page, timeoutMs));
    } else {
      result.error = "unsupported_platform_or_mode";
    }
  } catch (err) {
    result.success = false;
    result.error = String(err);
  } finally {
    if (context) {
      await context.close().catch(() => {});
    }
  }

  jsonOut(result);
}

await main();
