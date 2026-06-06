from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
import tempfile

from playwright.sync_api import BrowserContext, Error, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .models import ObservedPost, Profile


class XMonitor:
    def __init__(
        self,
        storage_state_path: str,
        headless: bool = True,
        browser_channel: str = "msedge",
        navigation_timeout_ms: int = 45000,
        post_load_wait_ms: int = 2500,
        debug: bool = False,
    ) -> None:
        self._storage_state_path = storage_state_path
        self._headless = headless
        self._browser_channel = browser_channel.strip()
        self._navigation_timeout_ms = navigation_timeout_ms
        self._post_load_wait_ms = post_load_wait_ms
        self._debug = debug

    def _debug_log(self, message: str) -> None:
        if self._debug:
            print(f"[debug] {message}", flush=True)

    def login(self) -> None:
        with sync_playwright() as p:
            context = self._launch_login_context(p)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded")
                print("Log into X in the opened browser, then press Enter here to save the session.")
                input()

                if not self._has_x_auth_session(context):
                    raise RuntimeError(
                        "No authenticated X session was detected. "
                        "If X rejected the login, retry with X_BROWSER_CHANNEL=chrome or msedge."
                    )

                context.storage_state(path=self._storage_state_path)
            finally:
                context.close()

    def fetch_new_posts(
        self,
        profiles: Iterable[Profile],
        seen_post_ids: set[str],
    ) -> list[ObservedPost]:
        if not Path(self._storage_state_path).exists():
            raise FileNotFoundError(
                f"Missing X browser session at {self._storage_state_path}. Run `copytrade-monitor login` first."
            )
        posts: list[ObservedPost] = []
        with sync_playwright() as p:
            launch_options = {
                "headless": self._headless,
                "ignore_default_args": ["--enable-automation"],
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            if self._browser_channel:
                launch_options["channel"] = self._browser_channel
            browser = p.chromium.launch(**launch_options)
            context = browser.new_context(storage_state=self._storage_state_path)
            context.set_default_navigation_timeout(self._navigation_timeout_ms)
            context.set_default_timeout(self._navigation_timeout_ms)
            context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in {"image", "media", "font"}
                else route.continue_(),
            )
            page = context.new_page()
            for profile in profiles:
                try:
                    posts.extend(self._fetch_profile_posts(page, profile, seen_post_ids))
                except Exception as exc:
                    print(f"Monitor warning: failed to fetch @{profile.handle}: {exc}", flush=True)
            browser.close()
        return posts

    def _launch_login_context(self, playwright) -> BrowserContext:
        profile_dir = Path(tempfile.gettempdir()) / "copytrade-monitor-login-profile"
        channels: list[str | None] = []
        if self._browser_channel:
            channels.append(self._browser_channel)
        for fallback in ("msedge", "chrome", None):
            if fallback not in channels:
                channels.append(fallback)

        last_error: Exception | None = None
        for channel in channels:
            try:
                return playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=False,
                    channel=channel,
                    ignore_default_args=["--enable-automation"],
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Error as exc:
                last_error = exc

        raise RuntimeError(
            "Could not start a browser for X login. "
            "Install Microsoft Edge or Google Chrome, or set X_BROWSER_CHANNEL explicitly."
        ) from last_error

    def _has_x_auth_session(self, context: BrowserContext) -> bool:
        auth_cookie_names = {"auth_token", "twid", "ct0"}
        for cookie in context.cookies():
            if cookie.get("name") not in auth_cookie_names:
                continue
            domain = cookie.get("domain", "")
            if "x.com" in domain or "twitter.com" in domain:
                return True
        return False

    def _fetch_profile_posts(
        self,
        page: Page,
        profile: Profile,
        seen_post_ids: set[str],
    ) -> list[ObservedPost]:
        profile_url = f"https://x.com/{profile.handle}"
        self._debug_log(f"opening {profile_url}")
        self._open_profile(page, profile_url, profile.handle)
        self._dismiss_cookie_banner(page, profile.handle)
        self._wait_for_timeline_content(page, profile.handle)
        self._ensure_tweet_articles(page, profile.handle)
        self._debug_log(f"landed on {page.url}")
        self._debug_log(f"title: {page.title()}")
        articles = page.locator("article[data-testid='tweet']").all()
        self._debug_log(f"tweet articles for {profile.handle}: {len(articles)}")
        if not articles:
            status_link_count = page.locator("a[href*='/status/']").count()
            self._debug_log(f"status links for {profile.handle}: {status_link_count}")
            self._log_page_diagnostics(page, profile.handle)
        results: list[ObservedPost] = []

        for article in articles[:5]:
            links = article.locator("a[href*='/status/']")
            count = links.count()
            if count == 0:
                continue
            href = links.nth(0).get_attribute("href")
            if not href or "/status/" not in href:
                continue
            post_id = href.rsplit("/", 1)[-1]
            if post_id in seen_post_ids:
                continue

            text = article.inner_text()
            image_urls, image_alts = self._extract_post_images(article)
            time_node = article.locator("time").first
            posted_at = None
            if time_node.count() > 0:
                dt = time_node.get_attribute("datetime")
                if dt:
                    posted_at = datetime.fromisoformat(dt.replace("Z", "+00:00"))

            results.append(
                ObservedPost(
                    post_id=post_id,
                    handle=profile.handle,
                    display_name=profile.display_name,
                    text=text,
                    image_urls=image_urls,
                    image_alts=image_alts,
                    posted_at=posted_at,
                    url=f"https://x.com{href}",
                    captured_at=datetime.now(UTC),
                )
            )
        return results

    def _extract_post_images(self, article) -> tuple[list[str], list[str]]:
        image_data = article.locator("img").evaluate_all(
            """
            (nodes) => nodes.map((node) => ({
                src: node.getAttribute("src") || "",
                alt: node.getAttribute("alt") || ""
            }))
            """
        )

        urls: list[str] = []
        alts: list[str] = []
        for item in image_data:
            src = (item.get("src") or "").strip()
            alt = (item.get("alt") or "").strip()

            if not src:
                continue
            if "/profile_images/" in src or "/emoji/" in src:
                continue
            if "abs-0.twimg.com/emoji" in src:
                continue

            urls.append(src)
            if alt:
                alts.append(alt)

        deduped_urls = list(dict.fromkeys(urls))
        deduped_alts = list(dict.fromkeys(alts))
        return deduped_urls, deduped_alts

    def _open_profile(self, page: Page, profile_url: str, handle: str) -> None:
        attempts = (
            ("domcontentloaded", self._navigation_timeout_ms),
            ("commit", self._navigation_timeout_ms),
        )
        last_error: Exception | None = None

        for wait_until, timeout_ms in attempts:
            try:
                page.goto(profile_url, wait_until=wait_until, timeout=timeout_ms)
                if wait_until == "commit":
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=min(10000, timeout_ms))
                    except PlaywrightTimeoutError:
                        self._debug_log(
                            f"domcontentloaded did not arrive for @{handle} after commit; continuing with partial page"
                        )
                page.wait_for_timeout(self._post_load_wait_ms)
                return
            except PlaywrightTimeoutError as exc:
                last_error = exc
                self._debug_log(f"navigation timeout for @{handle} with wait_until={wait_until}; retrying")

        raise RuntimeError(
            f"navigation to {profile_url} timed out after {self._navigation_timeout_ms}ms on all attempts"
        ) from last_error

    def _wait_for_timeline_content(self, page: Page, handle: str) -> None:
        selectors = (
            "article[data-testid='tweet']",
            "a[href*='/status/']",
            "[data-testid='primaryColumn']",
        )
        for selector in selectors:
            try:
                page.wait_for_selector(selector, timeout=10000)
                break
            except PlaywrightTimeoutError:
                continue
        else:
            self._debug_log(f"no timeline selectors appeared for @{handle}; reloading once")
            try:
                page.reload(wait_until="commit", timeout=self._navigation_timeout_ms)
                page.wait_for_timeout(self._post_load_wait_ms)
                self._dismiss_cookie_banner(page, handle)
                for selector in selectors:
                    try:
                        page.wait_for_selector(selector, timeout=10000)
                        break
                    except PlaywrightTimeoutError:
                        continue
            except PlaywrightTimeoutError:
                self._debug_log(f"reload timed out for @{handle}")

    def _ensure_tweet_articles(self, page: Page, handle: str) -> None:
        articles = page.locator("article[data-testid='tweet']")
        for attempt in range(3):
            if articles.count() > 0:
                return
            self._debug_log(f"no tweet articles yet for @{handle}; hydration retry {attempt + 1}/3")
            page.wait_for_timeout(3000)
            try:
                page.mouse.wheel(0, 1200)
            except Error:
                pass
            self._dismiss_cookie_banner(page, handle)
            try:
                page.wait_for_selector("article[data-testid='tweet']", timeout=5000)
                return
            except PlaywrightTimeoutError:
                continue

    def _log_page_diagnostics(self, page: Page, handle: str) -> None:
        try:
            body_text = page.locator("body").inner_text(timeout=5000)
        except PlaywrightTimeoutError:
            self._debug_log(f"body text unavailable for @{handle}")
            return

        compact = " ".join(body_text.split())
        if not compact:
            self._debug_log(f"empty body for @{handle}")
            return

        snippet = compact[:300]
        self._debug_log(f"body snippet for @{handle}: {snippet}")

    def _dismiss_cookie_banner(self, page: Page, handle: str) -> None:
        cookie_button_names = (
            "Accept all cookies",
            "Refuse non-essential cookies",
            "Reject non-essential cookies",
        )
        for button_name in cookie_button_names:
            button = page.get_by_role("button", name=button_name)
            try:
                if button.count() == 0:
                    continue
                button.first.click(timeout=5000)
                self._debug_log(f"dismissed cookie banner for @{handle} using '{button_name}'")
                page.wait_for_timeout(1000)
                return
            except PlaywrightTimeoutError:
                continue
