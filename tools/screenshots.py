"""Screenshots and a demo GIF of the Differential web app (Playwright + Pillow).

Start the server first (``python -m differential.app.server``), then run::

    .venv/bin/python tools/screenshots.py            # server at http://127.0.0.1:8000
    .venv/bin/python tools/screenshots.py --size 1920x1080 --suffix _1920 --out /tmp/shots --no-gif

The script drives one scripted session per theme in headless Chromium: start
screen -> "Start with a simulated unit" -> the complaint -> "Measure" on each
recommendation until the engine stops (or ``--max-steps``) -> ticket -> sign-off
-> reveal. It saves, per theme (light, dark)::

    01_start  02_recommendation_hv  03_after_readings  04_ticket  05_revealed

as ``<name>_<theme>.png`` in ``docs/media/screenshots/`` and, from the first
theme's session, an animated GIF at ``docs/media/demo.gif`` (kept under 6 MB).

The hidden fault and the unit seed are fixed through the page's ``?fault=`` and
``?seed=`` parameters so both themes show the same session. The run fails (exit
code 1) on browser console errors, uncaught page errors, requests to any other
origin, or a page wider than the viewport.

Playwright's own Chromium is used when installed; otherwise the newest Chromium
found under ``PLAYWRIGHT_BROWSERS_PATH`` or ``/opt/pw-browsers`` (or ``--chromium``).
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlparse

from PIL import Image
from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "media" / "screenshots"
DEFAULT_GIF = ROOT / "docs" / "media" / "demo.gif"
GIF_LIMIT = 6 * 1024 * 1024


@dataclass
class Run:
    theme: str
    errors: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    frames: list[tuple[bytes, int]] = field(default_factory=list)  # (png, duration ms)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="running Differential server")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="screenshot folder")
    ap.add_argument("--gif", type=Path, default=DEFAULT_GIF, help="animated GIF path")
    ap.add_argument("--no-gif", action="store_true", help="skip the GIF")
    ap.add_argument("--size", default="1280x720", help="viewport WxH")
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--suffix", default="", help="extra filename suffix, e.g. _1920")
    ap.add_argument("--circuit", default="channel_strip")
    ap.add_argument("--fault", default="C105:high_esr", help="hidden fault id ('' = random)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--complaint", default="The channel hums and sounds thin")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--name", default="Demo technician", help="name used for the sign-off")
    ap.add_argument("--gif-width", type=int, default=960)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument(
        "--chromium",
        default=os.environ.get("DIFFERENTIAL_CHROMIUM", ""),
        help="Chromium executable (default: Playwright's own, else one found under "
        "PLAYWRIGHT_BROWSERS_PATH or /opt/pw-browsers)",
    )
    return ap.parse_args(argv)


def find_chromium() -> str | None:
    """A locally installed Chromium when Playwright's pinned build is not present."""
    roots = (
        [Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])]
        if os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        else []
    )
    roots += [Path("/opt/pw-browsers"), Path.home() / ".cache" / "ms-playwright"]
    for pattern in (
        "chromium_headless_shell-*/chrome-linux*/headless_shell",
        "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chromium-*/chrome-linux*/chrome",
    ):
        found = sorted(p for r in roots if r.exists() for p in r.glob(pattern))
        if found:
            return str(found[-1])
    return None


def launch(p, a: argparse.Namespace) -> Browser:  # type: ignore[no-untyped-def]
    kwargs = {"headless": not a.headed}
    if a.chromium:
        return p.chromium.launch(executable_path=a.chromium, **kwargs)
    try:
        return p.chromium.launch(**kwargs)
    except Exception as exc:
        exe = find_chromium()
        if "Executable doesn't exist" not in str(exc) or exe is None:
            raise
        print(f"  Playwright's pinned Chromium is missing; using {exe}")
        return p.chromium.launch(executable_path=exe, **kwargs)


# ----------------------------------------------------------------- helpers
def wait_idle(page: Page, timeout: float = 120_000) -> None:
    page.wait_for_function(
        "() => window.differential && !window.differential.busy", timeout=timeout
    )


def state(page: Page) -> dict:
    return page.evaluate("() => window.differential && window.differential.state") or {}


def settle(page: Page, ms: int = 900) -> None:
    """Let bar/label transitions finish before a screenshot."""
    page.wait_for_timeout(ms)


def shot(page: Page, run: Run, out: Path, name: str, suffix: str) -> Path:
    path = out / f"{name}_{run.theme}{suffix}.png"
    page.screenshot(path=str(path))
    print(f"  saved {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return path


def frame(page: Page, run: Run, ms: int, capture: bool) -> None:
    if capture:
        run.frames.append((page.screenshot(), ms))


def check_layout(page: Page, run: Run, where: str) -> None:
    wide = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    if wide > 0:
        run.errors.append(f"{where}: page is {wide}px wider than the viewport (horizontal scroll)")
    clipped = page.evaluate(
        """() => {
          const out = [];
          const sel = '.btn, .chip, .panel-title, .bar-label, .bar-pct, .next-what, .banner-title, '
            + '.tk-title, .status-badge, .mode-badge, .tp-label, .opt-val, .meter-value, .data-table td';
          for (const el of document.querySelectorAll(sel)) {
            if (!el.offsetParent) continue;
            const cs = getComputedStyle(el);
            if (cs.overflow === 'visible' && cs.textOverflow !== 'ellipsis') {
              if (el.scrollWidth > el.clientWidth + 2 && cs.whiteSpace === 'nowrap' && el.clientWidth > 0
                  && !el.classList.contains('tp-label')) out.push(el.className + ': ' + el.textContent.trim().slice(0, 40));
            } else if (el.scrollWidth > el.clientWidth + 2) {
              out.push(el.className + ': ' + el.textContent.trim().slice(0, 40));
            }
          }
          return out.slice(0, 8);
        }"""
    )
    for c in clipped:
        run.notes.append(f"{where}: possibly clipped text in {c}")


def new_page(browser: Browser, run: Run, base: str, size: tuple[int, int]) -> Page:
    ctx = browser.new_context(
        viewport={"width": size[0], "height": size[1]},
        device_scale_factor=1,
        color_scheme=run.theme,
        reduced_motion="no-preference",
    )
    page = ctx.new_page()
    origin = urlparse(base)

    def on_console(msg) -> None:  # type: ignore[no-untyped-def]
        if msg.type == "error":
            run.errors.append(f"console: {msg.text}")

    def on_request(req) -> None:  # type: ignore[no-untyped-def]
        u = urlparse(req.url)
        if u.scheme in ("data", "blob"):
            return
        if (u.scheme, u.netloc) != (origin.scheme, origin.netloc):
            run.external.append(req.url)

    page.on("console", on_console)
    page.on("pageerror", lambda exc: run.errors.append(f"page error: {exc}"))
    page.on("request", on_request)
    return page


def click_measure(page: Page) -> bool:
    btn = page.locator("#next-card .next-actions .btn-primary")
    if btn.count() == 0 or not btn.first.is_enabled():
        return False
    before = len(state(page).get("readings", []))
    btn.first.click()
    page.wait_for_function(
        f"() => window.differential && !window.differential.busy && "
        f"(window.differential.state.readings || []).length > {before}",
        timeout=120_000,
    )
    return True


def confirm_discharge(page: Page) -> None:
    form = page.locator(".banner .discharge-form")
    form.locator("input").fill("0.4")
    form.locator("button[type=submit]").click()
    wait_idle(page)


# -------------------------------------------------------------- one session
def session(
    browser: Browser, a: argparse.Namespace, theme: str, size: tuple[int, int], capture: bool
) -> Run:
    run = Run(theme)
    base = a.url.rstrip("/")
    q = {"circuit": a.circuit, "seed": a.seed}
    if a.fault:
        q["fault"] = a.fault
    page = new_page(browser, run, base, size)
    out = a.out
    print(f"[{theme}] {base}/?{urlencode(q)}")
    page.goto(f"{base}/?{urlencode(q)}")
    page.wait_for_selector(".start-btn", state="visible")
    page.wait_for_function(
        "() => { const i = document.querySelector('.sch-img');"
        " return i && i.complete && i.naturalWidth > 0; }"
    )
    settle(page, 500)
    check_layout(page, run, "start")
    shot(page, run, out, "01_start", a.suffix)
    frame(page, run, 2200, capture)

    page.click(".start-btn")
    page.wait_for_selector("#session-view:not([hidden])", timeout=180_000)
    wait_idle(page)
    page.wait_for_selector(".composer-input")
    frame(page, run, 1200, capture)

    page.fill(".composer-input", a.complaint)
    frame(page, run, 1400, capture)
    page.press(".composer-input", "Enter")
    page.wait_for_function(
        "() => window.differential && !window.differential.busy && "
        "(window.differential.state.history || []).length > 0",
        timeout=180_000,
    )
    settle(page)
    frame(page, run, 2600, capture)

    got_hv = False
    first_rec = None
    steps = 0
    while steps < a.max_steps:
        st = state(page)
        pending = st.get("pending")
        if not pending:
            break
        if st.get("banner") and not got_hv:
            got_hv = True
            settle(page, 500)
            page.evaluate("() => document.getElementById('side').scrollTo(0, 0)")
            check_layout(page, run, "hv recommendation")
            shot(page, run, out, "02_recommendation_hv", a.suffix)
            frame(page, run, 3200, capture)
        if first_rec is None:
            page.evaluate("() => document.getElementById('side').scrollTo(0, 0)")
            first_rec = page.screenshot()
        if pending.get("blocked") == "discharge_verification":
            confirm_discharge(page)
            settle(page)
            frame(page, run, 1600, capture)
            continue
        if not click_measure(page):
            run.notes.append("the Measure button was not available")
            break
        steps += 1
        if capture:
            page.wait_for_timeout(250)
            frame(page, run, 300, capture)  # mid-animation frame
        settle(page)
        frame(page, run, 1000, capture)
    if not got_hv:
        run.notes.append(
            "no high-voltage recommendation came up in this session; "
            "02_recommendation_hv shows the first recommendation instead"
        )
        if first_rec is not None:
            (out / f"02_recommendation_hv_{theme}{a.suffix}.png").write_bytes(first_rec)

    settle(page, 700)
    page.evaluate("() => document.getElementById('side').scrollTo(0, 0)")
    check_layout(page, run, "after readings")
    shot(page, run, out, "03_after_readings", a.suffix)
    frame(page, run, 2600, capture)

    # ticket + sign-off
    page.click("#ticket-btn")
    page.wait_for_selector(".tk-sign input, .tk-signed", timeout=60_000)
    settle(page, 300)
    frame(page, run, 2200, capture)
    if page.locator(".tk-sign input").count():
        page.fill(".tk-sign input", a.name)
        frame(page, run, 900, capture)
        page.click(".tk-sign button[type=submit]")
        page.wait_for_selector(".tk-signed", timeout=60_000)
    settle(page, 400)
    check_layout(page, run, "ticket")
    shot(page, run, out, "04_ticket", a.suffix)
    frame(page, run, 2800, capture)
    page.keyboard.press("Escape")
    page.wait_for_selector("#ticket-dialog:not([open])", state="attached")

    # demo reveal: one click after the engine stopped, else a second click confirms
    stopped = bool((state(page).get("belief") or {}).get("would_stop"))
    page.click("#reveal-btn")
    if not stopped:
        page.wait_for_timeout(150)
        page.click("#reveal-btn")
    page.wait_for_function(
        "() => window.differential.state && window.differential.state.revealed", timeout=60_000
    )
    settle(page, 700)
    shot(page, run, out, "05_revealed", a.suffix)
    frame(page, run, 3000, capture)
    page.context.close()
    return run


# --------------------------------------------------------------------- GIF
def write_gif(frames: list[tuple[bytes, int]], path: Path, width: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for w, colors in ((width, 128), (int(width * 0.85), 96), (int(width * 0.7), 64)):
        imgs, durs = [], []
        for png, ms in frames:
            im = Image.open(io.BytesIO(png)).convert("RGB")
            h = round(im.height * w / im.width)
            im = im.resize((w, h), Image.Resampling.LANCZOS)
            imgs.append(
                im.quantize(
                    colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
                )
            )
            durs.append(ms)
        buf = io.BytesIO()
        imgs[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=imgs[1:],
            duration=durs,
            loop=0,
            optimize=True,
            disposal=1,
        )
        if buf.tell() <= GIF_LIMIT:
            path.write_bytes(buf.getvalue())
            print(
                f"  saved {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} "
                f"({buf.tell() / 1e6:.2f} MB, {len(imgs)} frames, {w}px wide)"
            )
            return
    raise SystemExit(f"GIF stays above {GIF_LIMIT} bytes even at reduced size")


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    w, h = (int(x) for x in a.size.lower().split("x"))
    a.out.mkdir(parents=True, exist_ok=True)
    themes = [t.strip() for t in a.themes.split(",") if t.strip()]
    runs: list[Run] = []
    t0 = time.time()
    with sync_playwright() as p:
        browser = launch(p, a)
        for i, theme in enumerate(themes):
            runs.append(session(browser, a, theme, (w, h), capture=(i == 0 and not a.no_gif)))
        browser.close()
    if not a.no_gif and runs and runs[0].frames:
        write_gif(runs[0].frames, a.gif, a.gif_width)
    failed = False
    for r in runs:
        for n in r.notes:
            print(f"[{r.theme}] note: {n}")
        for e in r.errors:
            print(f"[{r.theme}] ERROR: {e}")
            failed = True
        for u in sorted(set(r.external)):
            print(f"[{r.theme}] ERROR: request to another origin: {u}")
            failed = True
    print(f"done in {time.time() - t0:.0f}s" + (" with errors" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
