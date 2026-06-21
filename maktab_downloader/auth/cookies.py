import json
from pathlib import Path
from typing import Dict, Optional
import httpx
from maktab_downloader.config import settings
from maktab_downloader.utils.console import console, print_info, print_warning, print_error, print_success

AUTH_CACHE_FILE = Path(".maktab_auth.json")


class CookieManager:
    """Handles extracting, storing, and formatting Maktabkhooneh authentication cookies."""

    def __init__(
        self,
        cookie_string: Optional[str] = None,
        sessionid: Optional[str] = None,
        csrftoken: Optional[str] = None,
        browser: Optional[str] = None,
    ):
        self.cookie_string = cookie_string or settings.COOKIE_STRING
        self.sessionid = sessionid or settings.SESSIONID
        self.csrftoken = csrftoken or settings.CSRFTOKEN
        self.browser = browser or settings.BROWSER

    @staticmethod
    def parse_cookie_string(raw_cookies: str) -> Dict[str, str]:
        """Parse raw Cookie header string into dict."""
        cookies = {}
        for item in raw_cookies.split(";"):
            item = item.strip()
            if not item:
                continue
            if "=" in item:
                key, val = item.split("=", 1)
                cookies[key.strip()] = val.strip()
        return cookies

    def extract_from_browser(self, browser_name: str = "chrome") -> Dict[str, str]:
        """Extract cookies for maktabkhooneh.org from specified local browser using browser_cookie3."""
        try:
            import browser_cookie3
        except ImportError:
            print_error("browser-cookie3 library is not installed.")
            return {}

        browser_map = {
            "chrome": browser_cookie3.chrome,
            "brave": browser_cookie3.brave,
            "firefox": browser_cookie3.firefox,
            "edge": browser_cookie3.edge,
            "safari": browser_cookie3.safari,
            "opera": browser_cookie3.opera,
            "chromium": browser_cookie3.chromium,
            "vivaldi": browser_cookie3.vivaldi,
        }

        func = browser_map.get(browser_name.lower())
        if not func:
            print_warning(f"Unsupported browser '{browser_name}'. Trying chrome...")
            func = browser_cookie3.chrome

        try:
            cj = func(domain_name="maktabkhooneh.org")
            extracted = {c.name: c.value for c in cj}
            if extracted:
                print_success(f"Successfully extracted {len(extracted)} cookies from {browser_name}.")
                return extracted
        except Exception as e:
            print_warning(f"Could not extract cookies automatically from {browser_name}: {e}")

        # If specific browser failed, attempt all available browsers
        for name, browser_func in browser_map.items():
            if name == browser_name.lower():
                continue
            try:
                cj = browser_func(domain_name="maktabkhooneh.org")
                extracted = {c.name: c.value for c in cj}
                if extracted and ("sessionid" in extracted or "csrftoken" in extracted):
                    print_success(f"Successfully extracted cookies from alternate browser: {name}.")
                    return extracted
            except Exception:
                continue

        return {}

    def load_cached_auth(self) -> Dict[str, str]:
        """Load cached credentials from local JSON file if exists."""
        if AUTH_CACHE_FILE.exists():
            try:
                with open(AUTH_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and ("sessionid" in data or "csrftoken" in data):
                        return data
            except Exception:
                pass
        return {}

    def save_cached_auth(self, cookies: Dict[str, str]):
        """Save credentials to local JSON cache."""
        try:
            with open(AUTH_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
        except Exception as e:
            print_warning(f"Failed to cache auth credentials: {e}")

    def get_cookies(self) -> Dict[str, str]:
        """
        Get complete cookie dictionary combining configured cookie string,
        explicit tokens, cached credentials, and browser auto-extraction.
        """
        cookies: Dict[str, str] = {}

        # 1. Start with cached credentials
        cached = self.load_cached_auth()
        if cached:
            cookies.update(cached)

        # 2. Extract from browser if requested or if sessionid is missing
        if self.browser:
            browser_cookies = self.extract_from_browser(self.browser)
            if browser_cookies:
                cookies.update(browser_cookies)

        # 3. Apply raw cookie string from settings / .env
        if self.cookie_string:
            cookies.update(self.parse_cookie_string(self.cookie_string))

        # 4. Apply explicit individual tokens
        if self.sessionid:
            cookies["sessionid"] = self.sessionid
        if self.csrftoken:
            cookies["csrftoken"] = self.csrftoken

        # Cache valid found credentials
        if cookies.get("sessionid"):
            self.save_cached_auth(cookies)

        return cookies

    def get_headers(self) -> Dict[str, str]:
        """Generate headers with current CSRF token and referer."""
        headers = dict(settings.DEFAULT_HEADERS)
        cookies = self.get_cookies()
        csrf = cookies.get("csrftoken") or self.csrftoken
        if csrf:
            headers["x-csrftoken"] = csrf
        return headers
