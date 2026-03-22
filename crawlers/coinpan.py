import re
import time
import random
import logging
from crawlers.base import ArticleData, BaseCrawler

logger = logging.getLogger(__name__)


class CoinpanCrawler:
    """코인판 크롤러 (Scrapling - TLS fingerprint bypass)"""

    MAX_PAGES = 3

    def __init__(self):
        from scrapling.fetchers import Fetcher
        self.fetcher = Fetcher()

    @property
    def site_name(self) -> str:
        return "coinpan"

    @property
    def display_name(self) -> str:
        return "코인판"

    @property
    def base_url(self) -> str:
        return "https://coinpan.com"

    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
        """자유게시판 추천순"""
        articles = []
        for page_num in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/index.php?mid=free&sort_index=voted_count&order_type=desc&page={page_num}"

            if page_num > 1:
                time.sleep(random.uniform(2.0, 5.0))

            page = self.fetcher.get(url, stealthy_headers=True)
            if page.status != 200:
                logger.warning(f"[coinpan] page {page_num} status={page.status}")
                break

            rows = page.css("#board_list table tr")
            data_rows = [r for r in rows if "notice" not in r.attrib.get("class", "")]
            if not data_rows:
                break

            for row in data_rows:
                try:
                    article = self._parse_row(row)
                    if article:
                        articles.append(article)
                except Exception:
                    continue

        return articles

    def _parse_row(self, row) -> ArticleData | None:
        title_cells = row.css("td.title")
        if not title_cells:
            return None
        title_td = title_cells[0]

        title_links = title_td.css("a[href]")
        if not title_links:
            return None
        title_link = title_links[0]

        title = title_link.get_all_text(strip=True)
        if not title:
            return None

        href = title_link.attrib.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        view_count = 0
        view_cells = row.css("td.readed")
        if view_cells:
            nums = re.findall(r"\d+", view_cells[0].get_all_text(strip=True).replace(",", ""))
            if nums:
                view_count = int(nums[0])

        like_count = 0
        vote_cells = row.css("td.voted")
        if vote_cells:
            nums = re.findall(r"\d+", vote_cells[0].get_all_text(strip=True))
            if nums:
                like_count = int(nums[0])

        comment_count = 0
        comment_spans = title_td.css("a[title='Replies'] span.number")
        if comment_spans:
            nums = re.findall(r"\d+", comment_spans[0].get_all_text())
            if nums:
                comment_count = int(nums[0])

        published_at = None
        date_cells = row.css("td.regdate")
        if date_cells:
            published_at = BaseCrawler._parse_date(date_cells[0].get_all_text(strip=True))

        image_urls, video_urls = self._get_article_images(href)

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            video_urls=video_urls,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
            published_at=published_at,
        )

    def _get_article_images(self, url: str) -> tuple[list[str], list[str]]:
        try:
            time.sleep(random.uniform(1.0, 3.0))
            page = self.fetcher.get(url, stealthy_headers=True)
            if page.status != 200:
                return [], []

            content_els = page.css("div.read_body div.xe_content")
            if not content_els:
                content_els = page.css("div.read_body")
            if not content_els:
                return [], []

            content = content_els[0]
            images = []
            for img in content.css("img"):
                src = img.attrib.get("src", "")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = self.base_url + src
                    images.append(src)

            # 비디오 추출 (Scrapling API)
            videos = []
            for video in content.css("video"):
                src = video.attrib.get("src", "")
                if not src:
                    sources = video.css("source")
                    if sources:
                        src = sources[0].attrib.get("src", "")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = self.base_url + src
                    videos.append(src)

            return images[:50], videos[:5]
        except Exception:
            return [], []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank", "loading"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
