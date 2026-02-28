import re
from bs4 import BeautifulSoup
from crawlers.base import BaseCrawler, ArticleData


class FmKoreaCrawler(BaseCrawler):
    """에펨코리아 크롤러 (Playwright 사용 - JS challenge 우회)"""

    def __init__(self):
        super().__init__()
        self._playwright = None
        self._browser = None
        self._page = None

    @property
    def site_name(self) -> str:
        return "fmkorea"

    @property
    def display_name(self) -> str:
        return "에펨코리아"

    @property
    def base_url(self) -> str:
        return "https://www.fmkorea.com"

    def _ensure_browser(self):
        """Playwright 브라우저 lazy 초기화"""
        if self._page:
            return
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._page = self._browser.new_page()
        self._page.set_extra_http_headers({
            "Accept-Language": "ko-KR,ko;q=0.9",
        })

    def _fetch_page(self, url: str) -> BeautifulSoup:
        """Playwright로 페이지 로드 후 BeautifulSoup 반환"""
        self._ensure_browser()
        self._page.goto(url, wait_until="networkidle", timeout=30000)
        html = self._page.content()
        return BeautifulSoup(html, "lxml")

    def get_popular_articles(self) -> list[ArticleData]:
        """인기글 목록 수집 (유머 게시판)"""
        articles = []

        url = f"{self.base_url}/best2"
        soup = self._fetch_page(url)

        for item in soup.select("li.li")[:20]:
            try:
                article = self._parse_list_item(item)
                if article:
                    articles.append(article)
            except Exception:
                continue

        return articles

    def _parse_list_item(self, item) -> ArticleData | None:
        """목록 아이템 파싱"""
        link = item.select_one("h3.title a")
        if not link:
            link = item.select_one("a.title, a[href*='document_srl']")
        if not link:
            return None

        title = link.get_text(strip=True)
        href = link.get("href", "")

        if not href.startswith("http"):
            href = self.base_url + href

        # 리스트 페이지 썸네일만 사용 (개별 페이지 방문은 너무 느림)
        image_urls = []
        thumb = item.select_one("img.thumb, img[src*='thumb'], img")
        if thumb:
            src = thumb.get("src") or thumb.get("data-src") or ""
            if src and self._is_valid_image(src):
                if not src.startswith("http"):
                    src = self.base_url + src
                image_urls.append(src)

        # 추천수
        like_count = 0
        count_el = item.select_one(".count")
        if count_el:
            numbers = re.findall(r"\d+", count_el.get_text(strip=True).replace(",", ""))
            if numbers:
                like_count = int(numbers[0])

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            view_count=0,
            like_count=like_count,
        )

    def _is_valid_image(self, url: str) -> bool:
        """유효한 이미지 URL인지 확인"""
        exclude_patterns = [
            "emoticon", "icon", "btn_", "logo",
            "banner", "ad_", "advertisement",
        ]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude_patterns)

    def close(self):
        """리소스 정리"""
        if self._page:
            self._page.close()
            self._page = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        super().close()
