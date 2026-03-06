import re
import time
import random
from bs4 import BeautifulSoup
from scrapling.fetchers import StealthyFetcher
from crawlers.base import BaseCrawler, ArticleData


class FmKoreaCrawler(BaseCrawler):
    """에펨코리아 크롤러 (Scrapling StealthyFetcher, self-hosted runner 전용)"""

    @property
    def site_name(self) -> str:
        return "fmkorea"

    @property
    def display_name(self) -> str:
        return "에펨코리아"

    @property
    def base_url(self) -> str:
        return "https://www.fmkorea.com"

    def _fetch_stealth(self, url: str, delay: bool = True) -> BeautifulSoup:
        if delay:
            time.sleep(random.uniform(2.0, 5.0))
        page = StealthyFetcher.fetch(
            url, headless=True, network_idle=True,
            wait=random.randint(2, 4),
        )
        return BeautifulSoup(page.body, "lxml")

    def get_popular_articles(self) -> list[ArticleData]:
        """포텐 터짐 화제순"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/best2?page={page}"
            soup = self._fetch_stealth(url, delay=(page > 1))

            items = soup.select("li.li")
            if not items:
                break

            for item in items:
                try:
                    article = self._parse_item(item)
                    if article:
                        articles.append(article)
                except Exception:
                    continue

        return articles

    def _parse_item(self, item) -> ArticleData | None:
        link = item.select_one("h3.title a")
        if not link:
            return None

        title_text = link.get_text(strip=True)
        title = re.sub(r"\[\d+\]$", "", title_text).strip()
        if not title:
            return None

        href = link.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        # 리스트 썸네일
        image_urls = []
        thumb = item.select_one("img")
        if thumb:
            src = thumb.get("data-original") or thumb.get("src") or ""
            if src and self._is_valid_image(src):
                if src.startswith("//"):
                    src = "https:" + src
                elif not src.startswith("http"):
                    src = self.base_url + src
                image_urls.append(src)

        # 추천수
        like_count = 0
        count_el = item.select_one(".count")
        if count_el:
            nums = re.findall(r"\d+", count_el.get_text(strip=True).replace(",", ""))
            if nums:
                like_count = int(nums[0])

        # 댓글수
        comment_count = 0
        cm = re.search(r"\[(\d+)\]", title_text)
        if cm:
            comment_count = int(cm.group(1))

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            like_count=like_count,
            comment_count=comment_count,
        )

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
