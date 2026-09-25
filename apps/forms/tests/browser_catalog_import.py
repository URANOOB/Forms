"""Run with: uv run --with playwright python apps/forms/tests/browser_catalog_import.py."""

import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[3]


def response_for(name):
    return {
        "sheets": [name],
        "sheet": name,
        "header_row": 1,
        "headers": ["Código"],
        "sample": [["001"]],
        "row_count": 1,
        "issues": [],
        "issue_count": 0,
        "warnings": [],
        "field_definitions": [
            {
                "id": "code",
                "label": name,
                "value_column": 0,
                "label_columns": [0],
                "parent": "",
                "searchable": True,
                "required": False,
            }
        ],
        "proposal": {
            "option_count": 1,
            "explanation": name,
            "fields": [
                {
                    "stable_key": "code",
                    "label": name,
                    "required": False,
                    "configuration": {"searchable": True},
                    "options": [{"value": "001", "label": "001"}],
                }
            ],
        },
    }


async def main():
    template = (ROOT / "templates/admin/forms/catalog_import.html").read_text("utf-8")
    template = re.sub(r"\{#.*?#\}", "", template)
    css = (ROOT / "static/forms/catalog-import.css").read_text("utf-8")
    script = (ROOT / "static/forms/catalog-import.js").read_text("utf-8")
    # Include the actual theme listener that also processes this file input.
    unfold = (ROOT / ".venv/Lib/site-packages/unfold/static/unfold/js/app.js").read_text("utf-8")
    unfold = unfold[unfold.index("function fileInputUpdatePath() {") :]
    unfold = unfold[
        : unfold.index("/*************************************************************")
    ]
    html = (
        f"<meta charset='utf-8'><style>{css}</style><div id='builder' data-catalog-url='/analyze'>"
        "<input name='csrfmiddlewaretoken' value='test' type='hidden'>"
        f"<button data-open-catalog>Importar</button>{template}</div>"
        f"<script>{unfold}\nfileInputUpdatePath();</script><script>{script}</script>"
    )
    requests, errors = [], []
    slow_started, release_slow = asyncio.Event(), asyncio.Event()

    async def analyze(route):
        body = route.request.post_data_buffer.decode("utf-8", errors="replace")
        name = re.search(r'filename="([^"]+)"', body)[1]
        requests.append((name, body))
        if name == "slow.csv":
            slow_started.set()
            await release_slow.wait()
        payload = {"error": "Archivo dañado"} if name == "bad.xlsx" else response_for(name)
        await route.fulfill(
            status=400 if name == "bad.xlsx" else 200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.route(
            "http://catalog.test/",
            lambda route: route.fulfill(body=html, content_type="text/html; charset=utf-8"),
        )
        await page.route("http://catalog.test/analyze", analyze)
        await page.goto("http://catalog.test/")
        await page.locator("[data-open-catalog]").click()
        choose = page.locator("#catalog-choose-file")
        apply = page.locator("#catalog-apply")

        async def select(name):
            async with page.expect_file_chooser() as chooser:
                await choose.click()
            await (await chooser.value).set_files(
                {
                    "name": name,
                    "mimeType": "application/octet-stream",
                    "buffer": b"Codigo\n001",
                }
            )

        async def ready(name):
            await expect(page.locator("#catalog-filename")).to_have_text(name)
            await expect(page.locator("#catalog-explanation")).to_have_text(name)
            await expect(apply).to_be_enabled()
            await expect(choose).to_be_enabled()

        for name in ("first.xlsx", "second.csv", "third.xlsm", "third.xlsm"):
            await select(name)
            await ready(name)
        assert [name for name, _ in requests].count("third.xlsm") == 2
        assert all('name="sheet"' not in body for _, body in requests)

        await page.locator("#catalog-file").set_input_files([])
        await ready("third.xlsm")
        await page.locator("#catalog-header").fill("2")
        await page.locator("#catalog-header").dispatch_event("change")
        await ready("third.xlsm")
        assert 'name="sheet"' in requests[-1][1]

        await select("invalid.txt")
        await expect(page.locator("#catalog-status")).to_have_attribute("data-error", "true")
        await expect(apply).to_be_disabled()
        await select("bad.xlsx")
        await expect(page.locator("#catalog-status")).to_have_text("Archivo dañado")
        await select("recovered.csv")
        await ready("recovered.csv")

        await select("slow.csv")
        await asyncio.wait_for(slow_started.wait(), timeout=10)
        await expect(choose).to_be_enabled()
        await select("replacement.xlsm")
        await ready("replacement.xlsm")
        release_slow.set()
        await ready("replacement.xlsm")

        slow_started.clear()
        release_slow.clear()
        await select("slow.csv")
        await asyncio.wait_for(slow_started.wait(), timeout=10)
        await page.locator("[data-catalog-close]").last.click()
        await page.locator("[data-open-catalog]").click()
        await select("reopened.xlsx")
        await ready("reopened.xlsx")
        release_slow.set()
        await ready("reopened.xlsx")
        await apply.click()
        await expect(page.locator("#catalog-import")).not_to_be_visible()
        await page.locator("[data-open-catalog]").click()
        await expect(page.locator("#catalog-filename")).to_have_text("Ningún archivo seleccionado")
        await expect(apply).to_be_disabled()
        assert not errors, errors
        await browser.close()
    print("Browser checks passed: replacement, retry, cancel, errors, pending requests and reopen.")


if __name__ == "__main__":
    asyncio.run(main())
