"""Capture synthetic-but-real UI screenshots for the submission pack.

Drives the actual running stack through Chromium (no mocked responses), so every
image reflects canonical backend state. Safe to re-run.

    .venv/bin/python scripts/capture_screenshots.py

Writes PNGs to docs/screenshots/. Requires the backend on :8000 and the Angular
dev server on :4200 (scripts/dev.sh).
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
BASE = "http://localhost:4200"
VIEWPORT = {"width": 1440, "height": 900}


def shot(page: Page, name: str, *, full: bool = True) -> None:
    # Full-page capture otherwise repeats a position:sticky header at the
    # scroll offset. Neutralise stickiness for the capture only.
    page.add_style_tag(
        content="*{position:static !important} .option-card,.btn{cursor:default !important}"
    )
    page.wait_for_timeout(150)
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=full)
    print(f"  wrote {path.relative_to(OUT.parents[1])}")


def sign_in(page: Page, email: str, *, expect_path: str | None = None) -> None:
    page.goto(BASE, wait_until="networkidle")
    page.get_by_role("button", name=email, exact=False).first.click()
    if expect_path:
        page.wait_for_url(f"**/{expect_path}", timeout=15000)
    page.wait_for_timeout(1200)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        page = ctx.new_page()

        # 1. Landing — the pitch + synthetic demo accounts.
        print("1. landing")
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(600)
        shot(page, "01-landing")

        # 2. Customer journey — conversational request producing real options.
        print("2. customer request")
        page.get_by_role("button", name="maya@example.com", exact=False).first.click()
        page.wait_for_timeout(1500)
        page.get_by_role("button", name="Use the demo request", exact=False).first.click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="Ask the assistant", exact=False).first.click()
        try:
            page.wait_for_selector(".option-card, .option, [class*='option']", timeout=60000)
        except Exception:
            failures.append("options did not render for the customer request")
        page.wait_for_timeout(800)
        shot(page, "02-customer-validated-options")

        # 3. Hold + checkout surface (real PayPal sandbox order when in sandbox mode).
        print("3. hold + checkout")
        try:
            page.get_by_role("radio").first.click()
            page.wait_for_timeout(500)
            page.get_by_role("button", name="Hold this slot", exact=False).first.click()
            page.wait_for_timeout(2500)
            shot(page, "03-hold-created")
            page.get_by_role("button", name="Pay with PayPal", exact=False).first.click()
            page.wait_for_timeout(6000)
            shot(page, "04-checkout-paypal-sandbox")
        except Exception as exc:  # noqa: BLE001 - screenshot capture is best-effort
            failures.append(f"hold/checkout step: {exc}")

        # 4. Owner console — timeline + analytics from the same canonical state.
        print("4. owner console")
        owner = ctx.new_page()
        owner.goto(BASE, wait_until="networkidle")
        owner.get_by_role("button", name="owner@northline.example", exact=False).first.click()
        owner.wait_for_url("**/owner", timeout=15000)
        owner.wait_for_timeout(5000)
        shot(owner, "05-owner-timeline")

        for name, heading in (
            ("06-owner-analytics", "Analytics"),
            ("07-owner-disruption", "Technician"),
        ):
            try:
                owner.get_by_role("heading", name=heading, exact=False).first.scroll_into_view_if_needed()
                owner.wait_for_timeout(1200)
                shot(owner, name)
            except Exception:
                failures.append(f"owner section {heading!r} not found")

        # 6. Mobile customer layout.
        print("5. mobile")
        mobile = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        ).new_page()
        mobile.goto(BASE, wait_until="networkidle")
        mobile.wait_for_timeout(700)
        shot(mobile, "08-mobile-landing")

        browser.close()

    if failures:
        print("\nINCOMPLETE:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nall screenshots captured")
    return 0


if __name__ == "__main__":
    sys.exit(main())
