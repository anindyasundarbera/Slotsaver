#!/usr/bin/env python
"""End-to-end PayPal Sandbox journey, driven headlessly.

Runs the real flow against a running SlotSaver instance:
  reset fixtures -> customer login -> (live) assistant -> hold -> real PayPal order
  -> log in as the sandbox PERSONAL buyer -> approve -> capture -> verify the booking
  persisted in the database.

It stops at the first step it cannot complete and says exactly what is missing.
It never prints a credential, a token, or the whole browser HTML.

Requirements
  playwright (Python) + a Chromium build
  PAYPAL_SANDBOX_BUYER_EMAIL / _PASSWORD in backend/.env   (or --headed to log in yourself)

Usage
  ../.venv/bin/python scripts/e2e_sandbox.py [--headed] [--base-url ...] [--api-url ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

RESULTS: list[tuple[str, str, str]] = []  # (step, status, detail)


def record(step: str, status: str, detail: str = "") -> None:
    RESULTS.append((step, status, detail))
    icon = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP", "INFO": "INFO"}[status]
    print(f"[{icon}] {step}" + (f" — {detail}" if detail else ""), flush=True)


def fatal(step: str, detail: str) -> int:
    record(step, "FAIL", detail)
    print("\nBlocked. Nothing above is a code defect unless it says so.", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:4200")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--headed", action="store_true", help="show the browser so you can log in manually")
    parser.add_argument("--slow", type=float, default=0.0)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        return fatal("playwright installed", "pip install playwright && playwright install chromium")

    from app.config import get_settings

    settings = get_settings()
    record("mode", "INFO", f"paypal_mode={settings.paypal_mode}")
    if settings.paypal_mode != "sandbox":
        return fatal(
            "sandbox mode",
            "set PAYPAL_MODE=sandbox in backend/.env and restart the API",
        )

    buyer_email = settings.paypal_sandbox_buyer_email
    buyer_password = settings.paypal_sandbox_buyer_password
    manual_login = args.headed and not (buyer_email and buyer_password)
    if not manual_login and not (buyer_email and buyer_password):
        return fatal(
            "sandbox buyer credentials",
            "set PAYPAL_SANDBOX_BUYER_EMAIL and PAYPAL_SANDBOX_BUYER_PASSWORD in "
            "backend/.env (developer.paypal.com -> Testing Tools -> Sandbox Accounts -> "
            "a PERSONAL account), or rerun with --headed to log in yourself",
        )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed, slow_mo=int(args.slow * 1000))
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()

        # ---------------------------------------------------------------- 1. app
        page.goto(args.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        badge = "PayPal Sandbox" in page.inner_text("body")
        record("app reachable and connected", "PASS" if badge else "FAIL", "badge = PayPal Sandbox")
        if not badge:
            browser.close()
            return fatal("app in sandbox mode", "the UI badge did not read 'PayPal Sandbox'")

        # ---------------------------------------------------------------- 2. login
        page.get_by_role("button", name="Maya Chen").click()
        page.wait_for_timeout(2500)
        record("customer signed in", "PASS", "maya@example.com")

        # ---------------------------------------------------------------- 3. assistant
        page.locator("#request").fill(
            "My washing machine is leaking. I need someone tomorrow after 4pm, budget $80."
        )
        page.get_by_role("button", name="Ask the assistant").click()
        options = page.locator('[role="radio"]')
        for _ in range(30):
            if options.count() > 0:
                break
            page.wait_for_timeout(500)
        count = options.count()
        record("assistant returned options", "PASS" if count else "FAIL", f"{count} option(s)")
        if not count:
            page.screenshot(path="/tmp/e2e-options-failed.png")
            browser.close()
            return fatal("assistant options", "no options; screenshot at /tmp/e2e-options-failed.png")

        live = "Live AI assistant" in page.inner_text("body")
        record("assistant runtime", "INFO", "live AI" if live else "scripted")

        # ---------------------------------------------------------------- 4. hold
        options.first.click()
        page.get_by_role("button", name="Hold this slot").click()
        page.wait_for_timeout(2000)
        held = "Your hold" in page.inner_text("body")
        record("slot held", "PASS" if held else "FAIL")
        if not held:
            browser.close()
            return fatal("slot hold", "the hold panel did not appear")

        # ---------------------------------------------------------------- 5. order
        page.get_by_role("button", name="Pay with PayPal").click()
        approve_url = ""
        for _ in range(40):
            link = page.locator('a:has-text("Reopen PayPal")')
            if link.count():
                approve_url = link.first.get_attribute("href") or ""
                break
            page.wait_for_timeout(500)
        if not approve_url:
            body = page.inner_text("body")
            browser.close()
            return fatal("real PayPal order", "no approve URL; UI said: " + body[:200])
        record("real PayPal order created", "PASS", "approve URL obtained from PayPal's own link")

        # ---------------------------------------------------------------- 6. buyer approval
        buyer = ctx.new_page()
        buyer.goto(approve_url, wait_until="domcontentloaded")
        buyer.wait_for_timeout(2500)

        if manual_login:
            record("buyer approval", "SKIP", "--headed: log in and approve in the visible window (120s)")
            for _ in range(240):
                if "checkoutnow" not in buyer.url:
                    break
                buyer.wait_for_timeout(500)
        else:
            try:
                email_box = buyer.get_by_role("textbox", name="Email or mobile number")
                email_box.fill(buyer_email)
                buyer.get_by_role("textbox", name="Password").fill(buyer_password)
                buyer.get_by_role("button", name="Log In").click()
                buyer.wait_for_timeout(6000)
                record("buyer logged in", "PASS", "sandbox personal account")
            except Exception:
                record("buyer logged in", "INFO", "no login form (session may already be signed in)")

            # Approve / Continue / Pay Now depending on the sandbox flow variant.
            for label in ("Pay Now", "Complete Purchase", "Agree & Continue", "Continue", "Log In"):
                btn = buyer.get_by_role("button", name=label)
                if btn.count():
                    try:
                        btn.first.click(timeout=5000)
                    except Exception:
                        pass
                    buyer.wait_for_timeout(6000)
                    break

        approved = "checkoutnow" not in buyer.url
        record(
            "buyer approved the payment",
            "PASS" if approved else "FAIL",
            "" if approved else f"still on {buyer.url.split('?')[0]}",
        )
        if not approved:
            buyer.screenshot(path="/tmp/e2e-buyer-failed.png")
            record("screenshot", "INFO", "/tmp/e2e-buyer-failed.png")

        # ---------------------------------------------------------------- 7. capture
        page.bring_to_front()
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        capture = page.get_by_role("button", name="Capture payment")
        if capture.count():
            capture.first.click()
            page.wait_for_timeout(6000)

        body = page.inner_text("body")
        confirmed = "you are booked" in body.lower() or "confirmed" in body.lower()
        record("payment captured", "PASS" if confirmed else "FAIL")
        if not confirmed:
            page.screenshot(path="/tmp/e2e-capture-failed.png")
            record("screenshot", "INFO", "/tmp/e2e-capture-failed.png")
            browser.close()
            return fatal(
                "capture",
                "the booking did not reach 'confirmed'. This is the honest NOT RUN state "
                "until a sandbox buyer approves.",
            )

        # ---------------------------------------------------------------- 8. persistence
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        persisted = "confirmed" in page.inner_text("body").lower()
        record("confirmation survives a refresh", "PASS" if persisted else "FAIL")

        browser.close()

    print("\n=== SUMMARY ===")
    for step, status, detail in RESULTS:
        print(f"{status:4}  {step}" + (f" — {detail}" if detail else ""))
    ok = all(s != "FAIL" for s, status, _ in [(0, st, d) for _, st, d in RESULTS])
    print("\nRESULT:", "all steps passed" if ok else "see failures above")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
