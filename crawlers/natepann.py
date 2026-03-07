import re
from crawlers.base import BaseCrawler, ArticleData


class NatepannCrawler(BaseCrawler):
    """네이트판 크롤러"""

    @property
    def site_name(self) -> str:
        return "natepann"

    @property
    def display_name(self) -> str:
        return "네이트판"

    @property
    def base_url(self) -> str:
        return "https://pann.nate.com"

    def get_popular_articles(self) -> list[ArticleData]:
        """톡톡 랭킹"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/talk/ranking?page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            items = soup.select("ul.post_wrap > li")
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
        title_a = item.select_one("dl dt h2 a")
        if not title_a:
            return None

        title = title_a.get("title") or title_a.get_text(strip=True)
        href = title_a.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        view_count = 0
        count_span = item.select_one("dl dd.info span.count")
        if count_span:
            nums = re.findall(r"[\d,]+", count_span.get_text())
            if nums:
                view_count = int(nums[0].replace(",", ""))

        like_count = 0
        rcm_span = item.select_one("dl dd.info span.rcm")
        if rcm_span:
            nums = re.findall(r"[\d,]+", rcm_span.get_text())
            if nums:
                like_count = int(nums[0].replace(",", ""))

        comment_count = 0
        reply_span = item.select_one("dl dt span.reple-num")
        if reply_span:
            nums = re.findall(r"\d+", reply_span.get_text())
            if nums:
                comment_count = int(nums[0])

        # Check for thumbnail
        has_thumb = bool(item.select_one("div.thumb img"))

        image_urls, video_urls = self._get_article_images(href)

        # Skip if no images at all
        if not image_urls and not has_thumb:
            return None

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            video_urls=video_urls,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
        )

    def _get_article_images(self, url: str) -> tuple[list[str], list[str]]:
        try:
            soup = self.fetch_html(url)
            images = []
            content = soup.select_one("div#contentArea")
            if not content:
                return [], []

            for img in content.select("img"):
                src = img.get("src") or img.get("data-src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    images.append(src)

            videos = self._extract_videos(content)
            return images[:50], videos
        except Exception:
            return [], []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank", "loading"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
