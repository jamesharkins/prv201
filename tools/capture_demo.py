"""Silent screen capture of one scripted diagnosis (M3 90-second capture, M5 voice-over).

Start the server (``make demo``), then::

    .venv/bin/python tools/capture_demo.py                  # docs/media/demo_capture.mp4

One session on the channel strip with a fixed hidden fault and unit: the complaint
is typed, each recommended measurement is taken until the engine stops, the ticket
is opened and signed, and the hidden fault is revealed. Pauses are paced so the
whole capture runs about 90 seconds; the video has no audio track. Playwright
records WebM; ffmpeg converts it to H.264 MP4 when available.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import (  # noqa: E402
    click_measure,
    confirm_discharge,
    find_chromium,
    settle,
    state,
    wait_idle,
)

OUT = ROOT / "docs" / "media" / "demo_capture.mp4"


def main(argv: list[str] | None = None) -> int:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--circuit", default="channel_strip")
    ap.add_argument("--fault", default="C105:high_esr")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--complaint", default="Loud hum on both outputs since it was moved, and it sounds a bit thin.")
    ap.add_argument("--seconds", type=float, default=90.0, help="target length")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)

    tmp = Path(tempfile.mkdtemp())
    t0 = time.time()
    with sync_playwright() as p:
        exe = find_chromium()
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1,
                                  record_video_dir=str(tmp), record_video_size={"width": 1280, "height": 720})
        page = ctx.new_page()
        q = urlencode({"circuit": a.circuit, "seed": a.seed, "fault": a.fault})
        page.goto(f"{a.url.rstrip('/')}/?{q}")
        page.wait_for_selector(".start-btn", state="visible")
        settle(page, 3000)
        page.click(".start-btn")
        page.wait_for_selector("#session-view:not([hidden])", timeout=180_000)
        wait_idle(page)
        settle(page, 2500)
        page.type(".composer-input", a.complaint, delay=35)
        settle(page, 1200)
        page.press(".composer-input", "Enter")
        page.wait_for_function("() => window.differential && !window.differential.busy && "
                               "(window.differential.state.history || []).length > 0", timeout=180_000)
        settle(page, 6000)
        steps = 0
        while steps < 20:
            st = state(page)
            p_ = st.get("pending") or {}
            if not p_ or p_.get("stop"):
                break
            if p_.get("blocked"):
                confirm_discharge(page)
                settle(page, 3000)
                continue
            if not click_measure(page):
                break
            steps += 1
            settle(page, 3600)
        settle(page, 3000)
        page.click("#ticket-btn")
        page.wait_for_selector(".tk-sign input, .tk-signed", timeout=60_000)
        settle(page, 4000)
        if page.locator(".tk-sign input").count():
            page.type(".tk-sign input", "Demo technician", delay=40)
            settle(page, 800)
            page.click(".tk-sign button[type=submit]")
            page.wait_for_selector(".tk-signed", timeout=60_000)
        settle(page, 4000)
        page.keyboard.press("Escape")
        page.wait_for_selector("#ticket-dialog:not([open])", state="attached")
        settle(page, 1200)
        stopped = bool((state(page).get("belief") or {}).get("would_stop"))
        page.click("#reveal-btn")
        if not stopped:
            page.wait_for_timeout(150)
            page.click("#reveal-btn")
        page.wait_for_function("() => window.differential.state && window.differential.state.revealed",
                               timeout=60_000)
        elapsed = time.time() - t0
        settle(page, max(4000, int((a.seconds - elapsed - 2) * 1000)))
        video = page.video.path() if page.video else None
        ctx.close()
        browser.close()
    if not video:
        print("no video recorded")
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-an", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "28", "-movflags", "+faststart", str(a.out)], check=True)
    else:
        a.out = a.out.with_suffix(".webm")
        shutil.copy(video, a.out)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(a.out)], capture_output=True, text=True).stdout.strip()
    print(f"wrote {a.out.relative_to(ROOT)} ({a.out.stat().st_size / 1e6:.1f} MB, {dur} s, {steps} measurements)")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
