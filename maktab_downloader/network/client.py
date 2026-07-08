import asyncio
import random
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from maktab_downloader.auth.cookies import CookieManager
from maktab_downloader.config import settings
from maktab_downloader.utils.console import print_warning, print_error


class MaktabClient:
    """Async HTTP Client for Maktabkhooneh with resilient retry, polite jitter, and cookie management."""

    def __init__(self, cookie_manager: Optional[CookieManager] = None):
        self.cookie_manager = cookie_manager or CookieManager()
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        """Create or return existing httpx.AsyncClient session."""
        if self._client is None or self._client.is_closed:
            cookies = self.cookie_manager.get_cookies()
            headers = self.cookie_manager.get_headers()

            self._client = httpx.AsyncClient(
                headers=headers,
                cookies=cookies,
                timeout=httpx.Timeout(settings.REQUEST_TIMEOUT, connect=15.0),
                follow_redirects=True,
                http2=True,
            )
        return self._client

    async def close(self):
        """Close underlying client session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _polite_delay(self):
        """Introduce polite random jitter delay between API calls."""
        if settings.REQUEST_MAX_DELAY > 0:
            delay = random.uniform(settings.REQUEST_MIN_DELAY, settings.REQUEST_MAX_DELAY)
            await asyncio.sleep(delay)

    def _is_transient_error(self, exception: Exception) -> bool:
        """Check if exception is transient and worth retrying."""
        if isinstance(exception, (httpx.RequestError, httpx.TimeoutException)):
            return True
        if isinstance(exception, httpx.HTTPStatusError):
            return exception.response.status_code in (429, 500, 502, 503, 504)
        return False

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Execute request with automatic retry on transient failures and rate limits."""
        client = await self.get_client()

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(settings.MAX_RETRIES),
            wait=wait_exponential_jitter(
                initial=settings.RETRY_BACKOFF_MIN,
                max=settings.RETRY_BACKOFF_MAX,
                jitter=1.0,
            ),
            retry=retry_if_exception_type(
                (httpx.RequestError, httpx.TimeoutException)
            ),
            reraise=True,
        ):
            with attempt:
                await self._polite_delay()
                response = await client.request(method, url, **kwargs)

                # Check for rate-limiting or server errors
                if response.status_code == 429:
                    print_warning(f"Rate limited (429) on {url}. Retrying with backoff...")
                    response.raise_for_status()
                elif response.status_code in [500, 502, 503, 504]:
                    print_warning(f"Server error ({response.status_code}) on {url}. Retrying...")
                    response.raise_for_status()
                elif response.status_code >= 400:
                    # 401, 403, 404 immediately raise without wasteful retrying
                    response.raise_for_status()

                return response

        raise RuntimeError("Request retry failed")

    def format_course_slug_mk(self, slug_or_id: str | int, course_id: Optional[int] = None) -> str:
        """
        Format slug identifier to Maktabkhooneh slug format: `{slug}-mk{course_id}`.
        If slug already contains `-mk`, it will be URL encoded appropriately.
        """
        s = str(slug_or_id).strip()
        if "-mk" in s:
            slug_part = s
        elif course_id:
            slug_part = f"{s}-mk{course_id}"
        elif s.isdigit():
            slug_part = f"course-mk{s}"
        else:
            slug_part = s
        return quote(slug_part, safe="-mk")

    async def verify_auth(self) -> Dict[str, Any]:
        """Verify authentication session by requesting first page of my_courses."""
        url = f"{settings.MY_COURSES_URL}?archived=0&limit=1"
        try:
            resp = await self._request("GET", url)
            data = resp.json()
            return {"authenticated": True, "count": data.get("count", 0), "data": data}
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [401, 403]:
                return {"authenticated": False, "error": f"Unauthorized ({e.response.status_code}). Please check your cookies."}
            return {"authenticated": False, "error": str(e)}
        except Exception as e:
            return {"authenticated": False, "error": str(e)}

    # -------------------------------------------------------------
    # 1. Enrolled Courses, Outlines, Units
    # -------------------------------------------------------------
    async def get_my_courses_page(self, limit: int = 12, offset: int = 0) -> Dict[str, Any]:
        """Fetch a paginated slice of enrolled/accessible courses."""
        url = f"{settings.MY_COURSES_URL}?archived=0&limit={limit}&offset={offset}"
        headers = {"referer": "https://maktabkhooneh.org/dashboard/"}
        resp = await self._request("GET", url, headers=headers)
        return resp.json()

    async def get_course_outline(self, course_id: int, slug: Optional[str] = None) -> Dict[str, Any]:
        """Fetch chapter and unit outline for a specific course."""
        url = settings.COURSE_OUTLINE_URL.format(course_id=course_id)
        slug_mk = self.format_course_slug_mk(slug or f"course-{course_id}", course_id)
        headers = {
            "referer": f"https://maktabkhooneh.org/lms/course/{slug_mk}/",
            "x-requested-with": "XMLHttpRequest",
        }
        resp = await self._request("GET", url, headers=headers)
        return resp.json()

    async def get_unit_detail(self, unit_id: int, course_slug: Optional[str] = None, course_id: Optional[int] = None) -> Dict[str, Any]:
        """Fetch full details and video resource download URLs for a unit."""
        url = settings.UNIT_DETAIL_URL.format(unit_id=unit_id)
        headers = {
            "referer": f"https://maktabkhooneh.org/lms/unit/{unit_id}/",
            "x-requested-with": "XMLHttpRequest",
        }
        resp = await self._request("GET", url, headers=headers)
        return resp.json()

    # -------------------------------------------------------------
    # 2. Public Catalog Search & Discovery
    # -------------------------------------------------------------
    async def search_catalog(
        self,
        page: int = 1,
        offset: int = 0,
        limit: int = 12,
        types: Optional[List[str]] = None,
        sorting: str = "new",
        q: str = "-",
    ) -> Dict[str, Any]:
        """
        Search and browse public course catalog across categories.
        types: ["MAKTAB", "PLUS", "HAMAYESH"]
        """
        types = types or ["MAKTAB", "PLUS", "HAMAYESH"]
        type_params = "&".join([f"types={t}" for t in types])
        url = f"{settings.CATALOG_SEARCH_URL}?{type_params}&page={page}&offset={offset}&limit={limit}&sorting={sorting}&q={quote(q)}"
        resp = await self._request("GET", url)
        return resp.json()

    # -------------------------------------------------------------
    # 3. Course Public Landing Page Details
    # -------------------------------------------------------------
    async def get_course_landing_detail(self, slug_or_id: str | int, course_id: Optional[int] = None) -> Dict[str, Any]:
        """Fetch full public landing page metadata for a course (learning goals, topics, prerequisites, etc.)."""
        slug_mk = self.format_course_slug_mk(slug_or_id, course_id)
        url = settings.COURSE_LANDING_URL.format(course_slug_mk=slug_mk) + "?container=%2Flandings%2Fnewest%2F"
        resp = await self._request("GET", url)
        return resp.json()

    # -------------------------------------------------------------
    # 4. Course Actions & Registration / Enrollment
    # -------------------------------------------------------------
    async def get_course_actions(self, slug_or_id: str | int, course_id: Optional[int] = None) -> Dict[str, Any]:
        """Fetch available actions (call to action, enrollment eligibility) for a course."""
        slug_mk = self.format_course_slug_mk(slug_or_id, course_id)
        url = settings.COURSE_ACTIONS_URL.format(course_slug_mk=slug_mk)
        resp = await self._request("GET", url)
        return resp.json()

    async def enroll_course(self, slug_or_id: str | int, course_id: Optional[int] = None) -> Dict[str, Any]:
        """Register / Enroll into a course using POST /enroll/."""
        slug_mk = self.format_course_slug_mk(slug_or_id, course_id)
        url = settings.COURSE_ENROLL_URL.format(course_slug_mk=slug_mk)
        headers = {
            "origin": "https://maktabkhooneh.org",
            "referer": f"https://maktabkhooneh.org/course/{slug_mk}/",
            "content-length": "0",
        }
        resp = await self._request("POST", url, headers=headers)
        if resp.status_code in [200, 201, 204]:
            return {"success": True, "status_code": resp.status_code, "data": resp.json() if resp.content else {}}
        return {"success": False, "status_code": resp.status_code, "text": resp.text}

    # -------------------------------------------------------------
    # 5. Course Reviews
    # -------------------------------------------------------------
    async def get_course_reviews(
        self,
        slug_or_id: str | int,
        course_id: Optional[int] = None,
        page: int = 1,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Fetch paginated student reviews and ratings for a course."""
        slug_mk = self.format_course_slug_mk(slug_or_id, course_id)
        url = settings.COURSE_REVIEWS_URL.format(course_slug_mk=slug_mk) + f"?limit={limit}&offset={offset}&page={page}"
        resp = await self._request("GET", url)
        return resp.json()

    # -------------------------------------------------------------
    # 6. Size Inspector
    # -------------------------------------------------------------
    async def get_resource_size(self, url: str, unit_id: Optional[int] = None) -> Optional[int]:
        """
        Determine exact file size in bytes without downloading the file.
        Uses HTTP HEAD, and falls back to a 1-byte HTTP Range GET request (Content-Range).
        Auto-refreshes download token if expired (403/410).
        """
        client = await self.get_client()
        current_url = url

        for attempt in range(2):
            try:
                # 1. Try HEAD request first (0 bytes downloaded)
                head_resp = await client.head(current_url, timeout=10.0)
                if head_resp.status_code == 200:
                    cl = head_resp.headers.get("content-length")
                    if cl and cl.isdigit():
                        return int(cl)

                # If token expired and unit_id is provided, refresh URL
                if head_resp.status_code in [401, 403, 410] and unit_id and attempt == 0:
                    fresh_unit = await self.get_unit_detail(unit_id)
                    for r in fresh_unit.get("resources", []):
                        if r.get("download_url"):
                            current_url = r["download_url"]
                            break
                    continue

                # 2. Fallback: GET with Range: bytes=0-0 (downloads only 1 byte)
                range_resp = await client.get(current_url, headers={"Range": "bytes=0-0"}, timeout=10.0)
                if range_resp.status_code == 206:
                    cr = range_resp.headers.get("content-range")
                    if cr:
                        # Format: "bytes 0-0/47432819"
                        match = re.search(r"/(\d+)$", cr)
                        if match:
                            return int(match.group(1))
                elif range_resp.status_code == 200:
                    cl = range_resp.headers.get("content-length")
                    if cl and cl.isdigit():
                        return int(cl)

            except Exception:
                pass

        return None
