import re
import time
import random
from bs4 import BeautifulSoup
from scrapling.fetchers import StealthyFetcher
from crawlers.base import BaseCrawler, ArticleData


class ArcaliveCrawler(BaseCrawler):
    """아카라이브 크롤러 (Scrapling StealthyFetcher, self-hosted runner 전용)"""

    @property
    def site_name(self) -> str:
        return "arcalive"

    @property
    def display_name(self) -> str:
        return "아카라이브"

    @property
    def base_url(self) -> str:
        return "https://arca.live"

    def _fetch_stealth(self, url: str) -> BeautifulSoup:
        page = StealthyFetcher.fetch(
            url, headless=True, network_idle=True,
            wait=random.randint(2, 4),
        )
        return BeautifulSoup(page.body, "lxml")

    def get_popular_articles(self) -> list[ArticleData]:
        """베스트 라이브 수집"""
        articles = []
        soup = self._fetch_stealth(f"{self.base_url}/b/live")

        for row in soup.select("div.vrow.hybrid")[:30]:
            try:
                article = self._parse_row(row)
                if article:
                    articles.append(article)
            except Exception:
                continue

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
