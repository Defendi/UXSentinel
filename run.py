import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

from flows import FLOWS
from analyze import analyze_screenshot

load_dotenv()

BASE_URL = os.environ.get("QA_BASE_URL", "http://localhost:8069")
OUT_DIR = Path("report")


async def run_step(page: Page, step: dict):
    action = step["action"]
    if action == "goto":
        url = step["url"]
        full_url = url if url.startswith("http") else BASE_URL.rstrip("/") + url
        await page.goto(full_url)
    elif action == "click":
        await page.click(step["selector"])
    elif action == "fill":
        await page.fill(step["selector"], step.get("value", ""))
    elif action == "wait_for_selector":
        await page.wait_for_selector(step["selector"], timeout=10_000)
    elif action == "wait_for_url":
        await page.wait_for_url(step["url"], timeout=10_000)
    else:
        raise ValueError(f"Ação desconhecida: {action}")


async def main():
    OUT_DIR.mkdir(exist_ok=True)
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,   # <- você acompanha visualmente
            slow_mo=350,       # <- dá tempo de ver cada ação
        )
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        for flow in FLOWS:
            name = flow["name"]
            print(f"\n▶ Executando fluxo: {name}")
            try:
                for step in flow["steps"]:
                    await run_step(page, step)

                await page.wait_for_timeout(500)  # pequena espera pra UI assentar

                screenshot_path = OUT_DIR / f"{name}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                dom_text = await page.evaluate("document.body.innerText")

                print("  📸 screenshot capturado, enviando para análise...")
                analysis = analyze_screenshot(
                    flow_name=name,
                    checkpoint_expected=flow["checkpoint"]["expected_behavior"],
                    screenshot_path=str(screenshot_path),
                    dom_text=dom_text,
                )

                print(f"  ✅ status: {analysis.get('status')}")
                results.append({"flow": name, "analysis": analysis})
            except Exception as err:  # noqa: BLE001
                print(f"  ❌ erro no fluxo {name}: {err}")
                results.append({"flow": name, "error": str(err)})

        await browser.close()

    (OUT_DIR / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nRelatório salvo em {OUT_DIR / 'report.json'}")


if __name__ == "__main__":
    asyncio.run(main())
