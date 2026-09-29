/* Browser regression suite. Run through browser_drafts.py with Playwright for Node. */
if (process.env.FORMS_DRAFT_MODE === "files") {
  const assert = require("node:assert/strict");
  const { chromium } = require(
    process.env.PLAYWRIGHT_NODE_MODULE || "playwright",
  );
  const fixture = JSON.parse(process.env.FORMS_DRAFT_FIXTURE);
  (async () => {
    const b = await chromium.launch({
      channel:
        process.env.PLAYWRIGHT_BROWSER_CHANNEL ||
        (process.platform === "win32" ? "msedge" : undefined),
      headless: true,
    });
    const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
    const p = await ctx.newPage();
    const errors = [];
    p.on("pageerror", (e) => errors.push(e.message));
    const start = async () => {
      await p.goto(fixture.url);
      if (await p.locator("#welcome-start").isVisible())
        await p.locator("#welcome-start").click();
    };
    await start();
    await p.locator("#id_answer_nombre").fill("Adjuntos");
    await p.locator("#id_answer_documento").fill("56789");
    const transfer = await p.evaluateHandle(() => {
      const t = new DataTransfer();
      t.items.add(
        new File(["Contenido privado de prueba"], "prueba.txt", {
          type: "text/plain",
        }),
      );
      return t;
    });
    await p
      .locator(".file-dropzone")
      .dispatchEvent("drop", { dataTransfer: transfer });
    await p.locator(".file-confirm").click();
    assert.equal(
      await p.locator("#id_answer_archivo").evaluate((el) => el.files.length),
      1,
    );
    await p.route("**/f/" + fixture.formId + "/", (route) =>
      route.request().method() === "POST" &&
      !route.request().postData().includes('name="submission_action"')
        ? route.fulfill({
            status: 503,
            contentType: "text/plain",
            body: "unavailable",
          })
        : route.continue(),
    );
    await p.locator("#submit-button").click();
    await p.waitForFunction(
      () => !document.getElementById("submit-button").disabled,
    );
    assert(
      (await p.locator("#submit-status").innerText()).includes(
        "No se pudo confirmar",
      ),
    );
    assert.equal(
      await p.locator("#id_answer_archivo").evaluate((el) => el.files.length),
      1,
    );
    const saved = await p.evaluate(
      (k) => localStorage.getItem(k),
      "forms:draft:v1:" + fixture.formId,
    );
    assert(!saved.includes("Contenido privado"));
    assert(JSON.parse(saved).hadFiles);
    if (process.env.FORMS_QA_SCREENSHOT)
      await p.screenshot({
        path: process.env.FORMS_QA_SCREENSHOT,
        fullPage: true,
      });
    assert(
      (await p.evaluate(() => document.documentElement.scrollWidth)) <= 390,
    );
    await p.unroute("**/f/" + fixture.formId + "/");
    await p.reload();
    await p.locator("#draft-continue").click();
    await p.waitForFunction(
      () => !document.getElementById("public-form").inert,
    );
    assert(
      (await p.locator("#draft-status").innerText()).includes(
        "Vuelve a seleccionar",
      ),
    );
    assert.equal(
      await p.locator("#id_answer_archivo").evaluate((el) => el.files.length),
      0,
    );
    assert.equal(await p.locator("#id_answer_nombre").inputValue(), "Adjuntos");
    await p.locator(".file-dropzone").dispatchEvent("drop", {
      dataTransfer: await p.evaluateHandle(() => {
        const t = new DataTransfer();
        t.items.add(
          new File(["Contenido privado de prueba"], "prueba.txt", {
            type: "text/plain",
          }),
        );
        return t;
      }),
    });
    await p.locator(".file-confirm").click();
    await p.locator("#submit-button").click();
    await p.waitForURL("**/f/enviado/**");
    console.log(
      "PASS upload failure keeps FileList, no binary stored, reload requests re-selection and retry succeeds; mobile layout fits",
    );
    await ctx.close();
    const blocked = await b.newContext();
    const q = await blocked.newPage();
    await q.addInitScript(() => {
      Object.defineProperty(window, "localStorage", {
        get() {
          throw new DOMException("Blocked", "SecurityError");
        },
      });
    });
    await q.goto(fixture.url);
    if (await q.locator("#welcome-start").isVisible())
      await q.locator("#welcome-start").click();
    assert(
      (await q.locator("#draft-status").innerText()).includes(
        "no permite guardar",
      ),
    );
    await q.locator("#id_answer_nombre").fill("Almacenamiento bloqueado");
    await q.locator("#submit-button").click();
    await q.waitForURL("**/f/enviado/**");
    console.log("PASS unavailable localStorage does not prevent submission");
    assert.deepEqual(errors, []);
    await b.close();
  })().catch((e) => {
    console.error(e);
    process.exit(1);
  });
} else {
  const assert = require("node:assert/strict");
  const { chromium } = require(
    process.env.PLAYWRIGHT_NODE_MODULE || "playwright",
  );
  const fixture = JSON.parse(process.env.FORMS_DRAFT_FIXTURE);
  (async () => {
    const browser = await chromium.launch({
      channel:
        process.env.PLAYWRIGHT_BROWSER_CHANNEL ||
        (process.platform === "win32" ? "msedge" : undefined),
      headless: true,
    });
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const key = "forms:draft:v1:" + fixture.formId;
    const draft = () =>
      page.evaluate((k) => JSON.parse(localStorage.getItem(k)), key);
    const wait = async (fn) => {
      for (let i = 0; i < 80; i++) {
        if (await fn()) return;
        await page.waitForTimeout(100);
      }
      throw Error("condition timeout");
    };
    await page.goto(fixture.url);
    if (await page.locator("#welcome-start").isVisible())
      await page.locator("#welcome-start").click();
    await page.locator("#id_answer_nombre").fill("Ana de prueba");
    await page.locator("#id_answer_documento").fill("12.345");
    await page.locator("#id_answer_contactar").selectOption("si");
    await page.locator("#id_answer_correo").fill("ana@example.test");
    await page.locator("#id_answer_fecha").fill("2026-09-29");
    await page.locator('input[name="answer_multiple"][value="uno"]').check();
    assert.equal((await draft()).answers.answer_nombre[0], "Ana de prueba");
    const expiry = (await draft()).updatedAt;
    await page.reload();
    assert(await page.locator("#draft-continue").isVisible());
    assert.equal(await page.locator("#id_answer_nombre").inputValue(), "");
    await page.locator("#draft-continue").click();
    await wait(
      async () =>
        (await page.locator("#id_answer_nombre").inputValue()) ===
        "Ana de prueba",
    );
    assert.equal(
      await page.locator("#id_answer_correo").inputValue(),
      "ana@example.test",
    );
    assert.equal(
      await page.locator("#id_answer_fecha").inputValue(),
      "2026-09-29",
    );
    assert(
      await page
        .locator('input[name="answer_multiple"][value="uno"]')
        .isChecked(),
    );
    assert.equal((await draft()).updatedAt, expiry);
    console.log(
      "PASS restore fields, choices, conditional visibility; viewing does not extend expiry",
    );
    await context.setOffline(true);
    await page.locator("#submit-button").click();
    await wait(
      async () => !(await page.locator("#submit-button").isDisabled()),
    );
    assert(
      (await page.locator("#submit-status").innerText()).includes(
        "No se pudo confirmar",
      ),
    );
    assert.equal(
      await page.locator("#id_answer_nombre").inputValue(),
      "Ana de prueba",
    );
    await context.setOffline(false);
    console.log("PASS offline submit retains values and permits retry");
    // Simulate a committed upload whose confirmation never reaches the browser.
    let dropped = false;
    await page.route("**/f/" + fixture.formId + "/", async (route) => {
      const req = route.request();
      if (
        req.method() === "POST" &&
        !req.postData().includes('name="submission_action"') &&
        !dropped
      ) {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        dropped = true;
        await route.abort();
      } else await route.continue();
    });
    await page.locator("#submit-button").click();
    await wait(
      async () =>
        dropped && !(await page.locator("#submit-button").isDisabled()),
    );
    assert(await draft());
    await page.unroute("**/f/" + fixture.formId + "/");
    await page.reload();
    await page.locator("#draft-continue").click();
    await page.waitForURL("**/f/enviado/**");
    assert.equal(await draft(), null);
    console.log("PASS lost confirmation recovers receipt and clears draft");
    await page.goto(fixture.url);
    if (await page.locator("#welcome-start").isVisible())
      await page.locator("#welcome-start").click();
    await page.locator("#id_answer_nombre").fill("Borrador de otra versión");
    await page.evaluate((k) => {
      const d = JSON.parse(localStorage.getItem(k));
      d.version = "older-version";
      localStorage.setItem(k, JSON.stringify(d));
    }, key);
    await page.reload();
    await context.setOffline(true);
    await page.locator("#draft-continue").click();
    assert.equal(await page.locator("#id_answer_nombre").inputValue(), "");
    assert(await page.locator("#public-form").evaluate((el) => el.inert));
    await context.setOffline(false);
    await page.locator("#draft-discard").click();
    await page.waitForLoadState("networkidle");
    console.log(
      "PASS offline recovery cannot restore a draft from another version",
    );

    await page.goto(fixture.url);
    if (await page.locator("#welcome-start").isVisible())
      await page.locator("#welcome-start").click();
    await page.locator("#id_answer_nombre").fill("Expira");
    await page.evaluate((k) => {
      const d = JSON.parse(localStorage.getItem(k));
      d.updatedAt = Date.now() - 86400001;
      localStorage.setItem(k, JSON.stringify(d));
    }, key);
    await page.reload();
    assert.equal(await page.locator("#id_answer_nombre").inputValue(), "");
    assert.equal(await draft(), null);
    assert(!(await page.locator("#draft-continue").isVisible()));
    console.log("PASS 24-hour expiry opens an empty form");
    if (await page.locator("#welcome-start").isVisible())
      await page.locator("#welcome-start").click();
    await page.locator("#id_answer_nombre").fill("Descartar");
    const prior = await page.locator('[name="submission_token"]').inputValue();
    await page.locator("#draft-discard").click();
    await page.waitForLoadState("networkidle");
    assert.equal(await page.locator("#id_answer_nombre").inputValue(), "");
    assert.equal(await draft(), null);
    assert.notEqual(
      await page.locator('[name="submission_token"]').inputValue(),
      prior,
    );
    console.log("PASS discard clears data and rotates nonce");
    if (await page.locator("#welcome-start").isVisible())
      await page.locator("#welcome-start").click();
    await page.locator("#id_answer_nombre").fill("Ana segundo envío");
    await page.locator("#id_answer_documento").fill("12345");
    await page.locator("#id_answer_contactar").selectOption("no");
    await page.locator("#submit-button").click();
    await page.waitForURL("**/f/enviado/**");
    console.log(
      "PASS new submission with same identity is received for review",
    );
    assert.deepEqual(errors, []);
    await browser.close();
  })().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
