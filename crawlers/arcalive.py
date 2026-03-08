import re
import time
import random
from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright
from crawlers.base import BaseCrawler, ArticleData


class ArcaliveCrawler(BaseCrawler):
    """아카라이브 크롤러 (Patchright, self-hosted runner 전용)"""

    @property
    def site_name(self) -> str:
        return "arcalive"

    @property
    def display_name(self) -> str:
        return "아카라이브"

    @property
    def base_url(self) -> str:
        return "https://arca.live"

    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
        """베스트 라이브 수집"""
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        page = context.new_page()

        articles = []
        try:
            page.goto(f"{self.base_url}/b/live", wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(6, 10))  # Cloudflare challenge 대기
            soup = BeautifulSoup(page.content(), "lxml")

            for row in soup.select("div.vrow.hybrid")[:30]:
                try:
                    article = self._parse_row(row)
                    if article:
                        articles.append(article)
                except Exception:
                    continue
        finally:
            page.close()
            context.close()
            browser.close()
            pw.stop()

        return articles

    def _parse_row(self, row) -> ArticleData | None:
        # 제목 + 링크: a.title.hybrid-title
        link = row.select_one("a.title.hybrid-title") or row.select_one("a.title")
        if not link:
            return None

        # 제목 텍스트 (댓글수 [N] 제외)
        title_text = link.get_text(strip=True)
        title = re.sub(r"\[\d+\]$", "", title_text).strip()
        if not title:
            return None

        href = link.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        # 썸네일
        image_urls = []
        thumb = row.select_one("img")
        if thumb:
            src = thumb.get("src") or thumb.get("data-src") or ""
            if src and "icon" not in src.lower() and "emoticon" not in src.lower():
                if src.startswith("//"):
                    src = "https:" + src
                elif not src.startswith("http"):
                    src = self.base_url + src
                image_urls.append(src)

        # 추천수
        like_count = 0
        rate_el = row.select_one(".col-rate")
        if rate_el:
            nums = re.findall(r"\d+", rate_el.get_text(strip=True))
            if nums:
                like_count = int(nums[0])

        # 조회수
        view_count = 0
        view_el = row.select_one(".col-view")
        if view_el:
            nums = re.findall(r"\d+", view_el.get_text(strip=True).replace(",", ""))
            if nums:
                view_count = int(nums[0])

        # 댓글수
        comment_count = 0
        comment_el = row.select_one(".comment-count")
        if comment_el:
            nums = re.findall(r"\d+", comment_el.get_text())
            if nums:
                comment_count = int(nums[0])

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
        )
