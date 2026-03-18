"""Playwright browser automation for Kling AI web UI.

Discovered internal API (base: https://api-app-global.klingai.com):
  POST /api/task/submit          — Submit generation task
  GET  /api/task/status           — Check task status
  POST /api/upload/issue/token    — Get file upload token
  POST /api/task/preprocess       — Validate uploaded files
  GET  /api/task/price            — Calculate credit cost
  GET  /api/user/profile_and_features — User info
  GET  /api/user/isLogin          — Login check
  GET  /api/pay/package/v2        — Subscription/credit info

Motion Control page: https://app.klingai.com/global/video-motion-control/new
File inputs:
  - Video: input[type="file"][accept=".mp4,.mov"]
  - Image: input[type="file"][accept=".jpg,.jpeg,.png"]
Generate button: button:has-text("Generate")
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from . import config as cfg

log = logging.getLogger(__name__)

# Kling-specific URLs (discovered via testing)
MOTION_CONTROL_URL = "https://app.klingai.com/global/video-motion-control/new"
APP_HOME_URL = "https://app.klingai.com/global/"
INTERNAL_API_BASE = "https://api-app-global.klingai.com"


class KlingBrowser:
    """Manages a single Kling account session via Playwright."""

    def __init__(
        self,
        account_name: str,
        proxy: Optional[str] = None,
        headless: bool = cfg.HEADLESS,
    ):
        self.account_name = account_name
        self.proxy = proxy
        self.headless = headless
        self._pw = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._intercepted_apis: List[Dict] = []
        self._task_submit_response: Dict = {}
        self._cookies_path = cfg.SESSIONS_DIR / f"{account_name}.json"

    # ── Lifecycle ────────────────────────────────────────────

    def start(self):
        cfg.ensure_dirs()
        self._pw = sync_playwright().start()

        launch_opts = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
            ],
        }
        if self.proxy:
            launch_opts["proxy"] = {"server": self.proxy}

        self._browser = self._pw.chromium.launch(**launch_opts)

        context_opts = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "locale": "en-US",
        }

        # Load saved session if exists
        if self._cookies_path.exists():
            context_opts["storage_state"] = str(self._cookies_path)
            log.info("Loaded saved session for '%s'", self.account_name)

        self._context = self._browser.new_context(**context_opts)
        self._context.on("request", self._on_request)
        self._page = self._context.new_page()

        # Intercept task submit responses
        self._page.on("response", self._on_response)

        return self

    def stop(self):
        if self._context:
            self._save_cookies()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()

    # ── Login ────────────────────────────────────────────────

    def login(self, email: str, password: str) -> bool:
        """Login to Kling AI web via email and save session cookies.

        Flow: app homepage → click action to trigger login modal →
              "Sign in with email" → email field → continue →
              password field → sign in → verify logged in.
        """
        page = self._page
        log.info("Logging in as '%s' (%s)...", self.account_name, email)

        # Go to app
        page.goto(APP_HOME_URL, timeout=cfg.DEFAULT_TIMEOUT, wait_until="domcontentloaded")
        time.sleep(4)

        # Dismiss any promo popups first
        self._dismiss_overlays()

        # Check if already logged in
        if self._is_logged_in():
            log.info("Already logged in via saved session.")
            self._save_cookies()
            return True

        # Trigger login modal — try multiple strategies
        login_triggers = [
            'text="Sign In"',                        # Sidebar "Sign In" button
            'button:has-text("Sign In")',
            'a:has-text("Sign In")',
            'text="One-click Sign In"',              # Right panel button
            'button:has-text("Experience Now")',      # Hero button
            'button:has-text("Generate")',            # Any action that requires login
        ]
        for sel in login_triggers:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                log.info("Triggering login via: %s", sel)
                btn.click()
                time.sleep(3)
                self._dismiss_overlays()
                break

        # Wait for login modal to appear
        time.sleep(2)
        self._screenshot("login_modal_check")

        # Click "Sign in with email" in the login modal
        email_signin = page.query_selector('text="Sign in with email"')
        if not email_signin:
            # Maybe modal didn't appear, try Escape and retry
            page.keyboard.press("Escape")
            time.sleep(1)
            for sel in login_triggers[:3]:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(3)
                    break
            email_signin = page.query_selector('text="Sign in with email"')

        if not email_signin:
            log.error("Could not find 'Sign in with email' button")
            self._screenshot("login_no_email_btn")
            return False

        email_signin.click()
        time.sleep(3)
        self._screenshot("login_email_form")

        # Fill email — look for visible email/text input
        email_input = page.query_selector(
            'input[type="email"]:visible, '
            'input[placeholder*="email" i]:visible, '
            'input[placeholder*="Email" i]:visible'
        )
        if not email_input:
            # Fallback: first visible text input
            for inp in page.query_selector_all('input:visible'):
                itype = inp.get_attribute("type") or "text"
                if itype in ("text", "email"):
                    email_input = inp
                    break

        if not email_input:
            log.error("Could not find email input")
            self._screenshot("login_no_email_input")
            return False

        email_input.fill(email)
        time.sleep(1)

        # Click Continue/Next
        next_btn = page.query_selector(
            'button:has-text("Continue"), button:has-text("Next"), '
            'button:has-text("Send"), button:has-text("Sign in"), '
            'button[type="submit"]'
        )
        if next_btn:
            next_btn.click()
            time.sleep(3)

        # Fill password
        pass_input = page.query_selector('input[type="password"]:visible')
        if pass_input:
            pass_input.fill(password)
            time.sleep(1)

            # Click Sign in / Log in
            login_btn = page.query_selector(
                'button:has-text("Log in"), button:has-text("Sign in"), '
                'button:has-text("Continue"), button[type="submit"]'
            )
            if login_btn:
                login_btn.click()
                time.sleep(5)
        else:
            log.warning("No password field found — may use OTP/verification code")
            self._screenshot("login_no_password")
            return False

        self._screenshot("login_result")

        if self._is_logged_in():
            log.info("Login successful for '%s'", self.account_name)
            self._save_cookies()
            return True

        log.warning("Login may have failed for '%s'", self.account_name)
        return False

    def _is_logged_in(self) -> bool:
        """Check if the current session is authenticated."""
        page = self._page
        try:
            url = page.url
            if "app.klingai.com" not in url:
                return False

            # Check for elements that only appear when logged in
            logged_in_selectors = [
                'text="Generate"',           # Sidebar nav
                'text="Assets"',             # Sidebar nav
                'text="All Tools"',          # Sidebar nav
                'text="Omni"',               # Sidebar nav
                '[class*="avatar"]',         # User avatar
                'text="Plans from"',         # Pricing in sidebar (visible when logged in)
                'text="Standard"',
                'text="Pro"',
                'text="Premium"',
            ]
            for sel in logged_in_selectors:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    return True

            # If page has motion control / video generation content, user is logged in
            if page.query_selector('button:has-text("Generate")'):
                return True

            return False
        except Exception:
            return False

    # ── Motion Control ───────────────────────────────────────

    def create_motion_task(
        self,
        image_path: str,
        video_path: str,
        prompt: str = "",
        mode: str = "pro",
        model_name: str = "kling-v2-6",
        character_orientation: str = "image",
        keep_original_sound: str = "yes",
    ) -> Dict[str, Any]:
        """Create a Motion Control video via web UI.

        Uses exact selectors discovered from live testing:
        - Video input: input[type="file"][accept=".mp4,.mov"]
        - Image input: input[type="file"][accept=".jpg,.jpeg,.png"]
        - Generate: button:has-text("Generate")
        - Task submit captured via api/task/submit response interception
        """
        page = self._page
        result = {"success": False, "task_id": "", "error": "", "raw_response": {}}
        self._task_submit_response = {}

        try:
            # Navigate to Motion Control page
            log.info("Navigating to Motion Control...")
            page.goto(MOTION_CONTROL_URL, timeout=cfg.DEFAULT_TIMEOUT, wait_until="domcontentloaded")
            time.sleep(5)
            self._dismiss_overlays()
            self._screenshot("mc_page")

            # Upload motion video first (input accepts .mp4,.mov)
            log.info("Uploading motion video: %s", video_path)
            video_input = page.query_selector('input[type="file"][accept=".mp4,.mov"]')
            if video_input:
                video_input.set_input_files(video_path)
                log.info("Video file attached")
                time.sleep(5)  # Wait for upload + preprocessing
            else:
                result["error"] = "Video file input not found"
                return result

            self._screenshot("mc_after_video")

            # Upload character image (input accepts .jpg,.jpeg,.png)
            log.info("Uploading character image: %s", image_path)
            image_input = page.query_selector('input[type="file"][accept=".jpg,.jpeg,.png"]')
            if image_input:
                image_input.set_input_files(image_path)
                log.info("Image file attached")
                time.sleep(5)  # Wait for upload + preprocessing
            else:
                result["error"] = "Image file input not found"
                return result

            self._screenshot("mc_after_image")

            # Select character orientation if needed
            try:
                if character_orientation == "image":
                    orient_btn = page.query_selector('text="Character Orientation Matches Image"')
                    if orient_btn:
                        page.evaluate("el => el.click()", orient_btn)
                        time.sleep(1)
                elif character_orientation == "video":
                    orient_btn = page.query_selector('text="Character Orientation Matches Video"')
                    if orient_btn:
                        page.evaluate("el => el.click()", orient_btn)
                        time.sleep(1)
            except Exception:
                pass

            # Dismiss overlays + remove blocking video elements
            self._dismiss_overlays()
            time.sleep(1)

            # Click Generate using JavaScript (bypasses ALL overlay/pointer-event issues)
            log.info("Clicking Generate via JS...")
            gen_btn = page.query_selector('button:has-text("Generate")')
            if not gen_btn:
                result["error"] = "Generate button not found"
                return result

            page.evaluate("el => el.click()", gen_btn)
            log.info("Generate clicked, waiting for task submission...")
            time.sleep(8)
            self._screenshot("mc_after_generate")

            # Extract task info from intercepted api/task/submit response
            if self._task_submit_response:
                data = self._task_submit_response.get("data", {})
                task = data.get("task", {})
                task_id = str(task.get("id", ""))

                result["success"] = True
                result["task_id"] = task_id
                result["raw_response"] = self._task_submit_response
                result["task_type"] = task.get("type", "")
                result["task_status"] = task.get("status", 0)
                log.info("Task submitted: id=%s type=%s", task_id, task.get("type"))
            else:
                # Fallback: assume success if no error visible
                result["success"] = True
                result["task_id"] = ""
                log.warning("Task likely submitted but could not intercept response")

            return result

        except Exception as e:
            log.error("Motion task error: %s", e)
            self._screenshot("mc_error")
            result["error"] = str(e)
            return result

    def check_task_status(self, task_id: str = "") -> Dict[str, Any]:
        """Check task status by observing the generation panel on the motion page."""
        page = self._page
        result = {"status": "unknown", "video_url": "", "error": ""}

        try:
            body = page.inner_text("body")

            if "Creating..." in body or "Queueing..." in body:
                result["status"] = "processing"
                return result

            if "Failed" in body:
                result["status"] = "failed"
                result["error"] = "Generation failed"
                return result

            # Look for completed video — find result video (not background video)
            # Result videos are in the right panel, not the login background
            video_els = page.query_selector_all("video")
            for vel in video_els:
                src = vel.get_attribute("src") or ""
                # Skip login background video (has autoplay+loop and poster with login image)
                is_bg = vel.get_attribute("loop") is not None and vel.get_attribute("autoplay") is not None
                poster = vel.get_attribute("poster") or ""
                if is_bg and ("login" in poster or "kling-website" in poster):
                    continue
                # This is likely the result video
                if src and (src.startswith("blob:") or ".mp4" in src):
                    result["status"] = "succeed"
                    result["video_url"] = src
                    return result

            # Also check <video><source> pattern
            source_els = page.query_selector_all("video source[src]")
            for sel in source_els:
                src = sel.get_attribute("src") or ""
                if src and (src.startswith("blob:") or ".mp4" in src):
                    result["status"] = "succeed"
                    result["video_url"] = src
                    return result

            # Check for download button (appears when video is ready)
            dl = page.query_selector('[class*="download"]:visible, a[download]:visible')
            if dl:
                result["status"] = "succeed"
                return result

            # Check via intercepted status API
            for api in reversed(self._intercepted_apis):
                if "task/status" in api.get("url", ""):
                    result["status"] = "processing"
                    return result

            return result

        except Exception as e:
            log.error("Status check error: %s", e)
            result["error"] = str(e)
            return result

    def get_credits(self) -> float:
        """Read remaining credits from the web UI sidebar."""
        page = self._page
        try:
            # Credits shown in sidebar as a number (e.g. "981")
            # Look for the credit icon area in sidebar
            import re

            body = page.inner_text("body")
            # The credit count appears near "Standard" or "Pro" in sidebar
            # Try to find it via the API response we intercepted
            for api in reversed(self._intercepted_apis):
                url = api.get("url", "")
                if "pay/package" in url or "price" in url:
                    break

            # Alternative: parse sidebar text
            # Credit display is typically a number near bottom of sidebar
            sidebar = page.query_selector('[class*="sidebar"], nav')
            if sidebar:
                text = sidebar.inner_text()
                # Look for standalone numbers (credit balance)
                nums = re.findall(r"\b(\d{2,})\b", text)
                if nums:
                    return float(nums[-1])  # Last number is usually credits

            return -1
        except Exception as e:
            log.warning("Could not read credits: %s", e)
            return -1

    # ── Overlay / popup dismissal ────────────────────────────

    def _dismiss_overlays(self):
        """Close any overlay dialogs, modals, popups that block interaction."""
        page = self._page
        try:
            # Strategy 1: Click close buttons on overlays
            close_selectors = [
                '.el-overlay .el-dialog__close',
                '.el-overlay button[aria-label="Close"]',
                '.el-overlay .close-btn',
                '.el-overlay [class*="close"]',
                '[class*="modal"] [class*="close"]',
                '[class*="popup"] [class*="close"]',
                'button:has-text("Close")',
                'button:has-text("Got it")',
                'button:has-text("OK")',
                'button:has-text("I know")',
                'button:has-text("Confirm")',
                'button:has-text("Skip")',
                'button:has-text("Later")',
                'button:has-text("Not now")',
                'button:has-text("Dismiss")',
                '[class*="bonus"] [class*="close"]',
                '[class*="trial"] [class*="close"]',
                '[class*="promotion"] [class*="close"]',
            ]
            for sel in close_selectors:
                btns = page.query_selector_all(sel)
                for btn in btns:
                    if btn.is_visible():
                        btn.click(force=True)
                        log.info("Dismissed overlay via: %s", sel)
                        time.sleep(0.5)

            # Strategy 2: Press Escape to close any modal
            page.keyboard.press("Escape")
            time.sleep(0.5)

            # Strategy 3: Click overlay backdrop to dismiss
            overlays = page.query_selector_all('.el-overlay')
            for overlay in overlays:
                if overlay.is_visible():
                    # Click the overlay itself (backdrop click usually closes dialog)
                    overlay.click(position={"x": 5, "y": 5}, force=True)
                    time.sleep(0.3)

            # Strategy 4: Remove overlays and blocking elements via JavaScript
            page.evaluate("""() => {
                // Remove overlay dialogs
                document.querySelectorAll('.el-overlay, [class*="modal-mask"], [class*="overlay"]').forEach(el => {
                    if (el.style.display !== 'none') el.style.display = 'none';
                });
                // Remove blocking video backgrounds (login page bg)
                document.querySelectorAll('video.video[autoplay][loop]').forEach(el => {
                    el.style.pointerEvents = 'none';
                    el.style.zIndex = '-1';
                });
                // Remove any full-screen blocking divs
                document.querySelectorAll('[class*="login-bg"], [class*="video-bg"]').forEach(el => {
                    el.style.pointerEvents = 'none';
                });
            }""")
            time.sleep(0.3)

        except Exception as e:
            log.debug("Overlay dismissal: %s", e)

    # ── Video download ───────────────────────────────────────

    def download_video(self, save_path: str) -> bool:
        """Download the completed video to a local file.

        Strategy order:
        1. Find CDN URL from intercepted API responses (fastest, most reliable)
        2. Click download button on Kling UI and capture file
        3. Fetch blob: URL via JavaScript (fallback)
        """
        import base64

        import httpx as _httpx

        page = self._page
        video_url = ""

        # Strategy 1: Get real CDN URL from intercepted API responses
        for api in reversed(self._intercepted_apis):
            url = api.get("url", "")
            if "works/personal/feeds" in url or "task/status" in url:
                # These responses contain CDN video URLs
                break

        # Try to extract CDN URL via JavaScript from page's network responses
        cdn_url = page.evaluate("""() => {
            // Find video elements with real URLs (not blob:)
            const videos = document.querySelectorAll('video');
            for (const v of videos) {
                const src = v.src || '';
                if (src.startsWith('http') && !src.includes('login')) return src;
                const source = v.querySelector('source');
                if (source && source.src && source.src.startsWith('http')) return source.src;
            }
            // Check for download links
            const links = document.querySelectorAll('a[href*=".mp4"], a[download]');
            for (const a of links) {
                if (a.href && a.href.startsWith('http')) return a.href;
            }
            return '';
        }""")

        if cdn_url and cdn_url.startswith("http"):
            video_url = cdn_url
            log.info("Found CDN URL: %s", video_url[:100])

        # Strategy 2: Click download button and capture download
        if not video_url:
            try:
                download_btn = page.query_selector('[class*="download"]:visible')
                if not download_btn:
                    # Look for download icon (usually a down arrow icon)
                    download_btn = page.query_selector('svg[class*="download"], [data-icon="download"]')
                    if download_btn:
                        download_btn = download_btn.query_selector('xpath=..')  # parent button

                if download_btn:
                    with page.expect_download(timeout=30000) as dl:
                        page.evaluate("el => el.click()", download_btn)
                    download = dl.value
                    download.save_as(save_path)
                    log.info("Video downloaded via button: %s bytes", Path(save_path).stat().st_size)
                    return True
            except Exception as e:
                log.debug("Download button approach failed: %s", e)

        # Strategy 3: Find blob: URL from video elements
        if not video_url:
            for vel in page.query_selector_all("video"):
                src = vel.get_attribute("src") or ""
                is_bg = vel.get_attribute("loop") is not None and vel.get_attribute("autoplay") is not None
                poster = vel.get_attribute("poster") or ""
                if is_bg and ("login" in poster or "kling-website" in poster):
                    continue
                if src and (src.startswith("blob:") or src.startswith("http")):
                    video_url = src
                    break

        if not video_url:
            for sel in page.query_selector_all("video source[src]"):
                src = sel.get_attribute("src") or ""
                if src:
                    video_url = src
                    break

        if not video_url:
            log.warning("No video URL found on page")
            self._screenshot("download_no_video")
            return False

        log.info("Downloading video: %s -> %s", video_url[:80], save_path)

        try:
            if video_url.startswith("http"):
                # Direct download from CDN (best case)
                resp = _httpx.get(video_url, timeout=120, follow_redirects=True)
                resp.raise_for_status()
                Path(save_path).write_bytes(resp.content)
                log.info("Video downloaded (CDN): %s bytes", len(resp.content))
                return True

            if video_url.startswith("blob:"):
                # Blob URL — download via JavaScript with longer timeout
                log.info("Downloading blob URL (this may take a moment)...")
                b64_data = page.evaluate(
                    """async (url) => {
                        try {
                            const resp = await fetch(url);
                            const buf = await resp.arrayBuffer();
                            const bytes = new Uint8Array(buf);
                            let binary = '';
                            const chunk = 8192;
                            for (let i = 0; i < bytes.length; i += chunk) {
                                binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
                            }
                            return btoa(binary);
                        } catch(e) {
                            return '';
                        }
                    }""",
                    video_url,
                )

                if b64_data:
                    Path(save_path).write_bytes(base64.b64decode(b64_data))
                    size = Path(save_path).stat().st_size
                    if size > 10000:  # Valid video should be >10KB
                        log.info("Video downloaded (blob): %s bytes", size)
                        return True
                    else:
                        log.warning("Downloaded file too small (%s bytes), likely invalid", size)
                        Path(save_path).unlink(missing_ok=True)

                # Blob fetch failed — try triggering download via Kling's download button
                log.info("Blob fetch failed, trying download button...")
                return self._download_via_button(save_path)

        except Exception as e:
            log.error("Video download failed: %s", e)
            # Last resort: try download button
            return self._download_via_button(save_path)

        return False

    def _download_via_button(self, save_path: str) -> bool:
        """Click download icon on Kling UI and save the file."""
        page = self._page
        try:
            # Kling has download icons on each video result
            # Look for SVG download icons or download-related buttons
            download_selectors = [
                '[class*="download"]',
                'svg[class*="download"]',
                '[data-icon="download"]',
                'button[title*="download" i]',
                'button[title*="Download" i]',
            ]
            for sel in download_selectors:
                els = page.query_selector_all(sel)
                for el in els:
                    if el.is_visible():
                        try:
                            with page.expect_download(timeout=60000) as dl:
                                page.evaluate("el => el.click()", el)
                            download = dl.value
                            download.save_as(save_path)
                            size = Path(save_path).stat().st_size
                            log.info("Video downloaded (button): %s bytes", size)
                            return size > 10000
                        except Exception:
                            continue

        except Exception as e:
            log.debug("Download button failed: %s", e)
        return False

    # ── Internal helpers ─────────────────────────────────────

    def _save_cookies(self):
        if self._context:
            state = self._context.storage_state()
            self._cookies_path.parent.mkdir(parents=True, exist_ok=True)
            self._cookies_path.write_text(json.dumps(state), encoding="utf-8")

    def _screenshot(self, name: str):
        if self._page:
            path = cfg.SCREENSHOTS_DIR / f"{self.account_name}_{name}.png"
            try:
                self._page.screenshot(path=str(path), full_page=False)
            except Exception:
                pass

    def _on_request(self, request):
        """Intercept requests to log internal API patterns."""
        url = request.url
        if any(kw in url for kw in ["/api/", "/v1/", "/v2/"]):
            entry = {"method": request.method, "url": url}
            try:
                entry["post_data"] = request.post_data
            except Exception:
                pass
            self._intercepted_apis.append(entry)

    def _on_response(self, response):
        """Capture task submit response for task ID extraction."""
        url = response.url
        if "api/task/submit" in url and response.status == 200:
            try:
                body = response.json()
                if body.get("result") == 1:
                    self._task_submit_response = body
                    log.info("Captured task submit: %s", str(body.get("data", {}).get("task", {}).get("id", ""))[:50])
            except Exception:
                pass

    def get_intercepted_apis(self) -> List[Dict]:
        return list(self._intercepted_apis)

    def export_cookies(self) -> Optional[Dict]:
        if self._context:
            return self._context.storage_state()
        if self._cookies_path.exists():
            return json.loads(self._cookies_path.read_text(encoding="utf-8"))
        return None
