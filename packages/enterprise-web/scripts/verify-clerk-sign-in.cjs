/** Exercise the shared form through a local website and a disposable Clerk development instance. */
const assert = require("node:assert/strict");
const { chromium, expect } = require("@playwright/test");

let stage = "development fixture configuration";

async function verify() {
  const origin = new URL(process.env.CLERK_E2E_ORIGIN);
  assert.ok(origin.protocol === "http:" && ["127.0.0.1", "localhost"].includes(origin.hostname));
  assert.equal(origin.href, origin.origin + "/");
  assert.match(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || "", /^pk_test_/);
  assert.match(process.env.CLERK_E2E_EMAIL || "", /\+clerk_test@example\.(com|org|net)$/i);
  assert.ok(process.env.CLERK_E2E_PASSWORD);

  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
  try {
    const page = await browser.newPage({ viewport: { width: 320, height: 820 } });
    stage = "unauthenticated dashboard redirect";
    await page.goto(new URL("/dashboard", origin).href, { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/sign-in(?:[/?].*)?$/);
    await expect(page.getByRole("button", { name: "Other sign-in options" })).toBeEnabled();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 320);
    const sizes = await page.locator("main form input, main form button").evaluateAll(nodes =>
      nodes.map(node => node.getBoundingClientRect().height));
    assert.ok(sizes.length >= 4 && sizes.every(size => size >= 44));

    stage = "wrong-password rejection and announced feedback";
    const email = page.getByLabel("Email address");
    const password = page.getByLabel("Password", { exact: true });
    await email.fill(process.env.CLERK_E2E_EMAIL);
    await password.fill("wrong-clerk-test-password-82");
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    const alert = page.locator("main").getByRole("alert");
    await expect(alert).toHaveText("Incorrect email or password. Try again.");
    await expect(password).toHaveAttribute("aria-invalid", "true");
    await expect(password).toHaveAttribute("aria-describedby", "workspace-sign-in-error");
    await expect(page).toHaveURL(/\/sign-in(?:[/?].*)?$/);

    stage = "valid password and Clerk device challenge";
    const code = page.getByRole("textbox", { name: "Verification code" });
    await password.fill(process.env.CLERK_E2E_PASSWORD);
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await Promise.any([code.waitFor({ state: "visible", timeout: 25_000 }),
      page.waitForURL(/\/dashboard(?:[/?].*)?$/, { waitUntil: "commit", timeout: 25_000 })]);
    if (await code.isVisible()) {
      // Fixed verification codes apply only to Clerk's synthetic development users.
      await code.fill("424242");
      await page.getByRole("button", { name: "Verify", exact: true }).click();
    }
    await page.waitForURL(/\/dashboard(?:[/?].*)?$/, { waitUntil: "commit", timeout: 25_000 });

    stage = "authenticated dashboard reload";
    const result = await page.goto(new URL("/dashboard", origin).href, { waitUntil: "domcontentloaded" });
    assert.equal(result.status(), 200);
    assert.equal(new URL(page.url()).pathname, "/dashboard");
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 320);

    stage = "managed Clerk alternatives";
    const guest = await browser.newPage({ viewport: { width: 320, height: 820 } });
    await guest.goto(new URL("/sign-in", origin).href, { waitUntil: "domcontentloaded" });
    await guest.getByRole("button", { name: "Other sign-in options" }).click();
    await expect(guest.getByRole("button", { name: "Other sign-in options" })).toHaveCount(0);
    await expect(guest.getByLabel(/email address|email or username/i).first()).toBeVisible({ timeout: 20_000 });
    console.log("PASS Clerk password rejection, announced error, device verification, dashboard reload and managed alternatives at 320 px.");
  } finally {
    await browser.close();
  }
}

verify().catch(error => {
  // Browser locator errors may include fixture values. Report only the failed stage.
  console.error(`FAIL ${stage} (${error.name})`);
  process.exitCode = 1;
});
