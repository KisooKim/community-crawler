import re
from crawlers.base import BaseCrawler, ArticleData


class DogdripCrawler(BaseCrawler):
    """개드립 크롤러"""

    @property
    def site_name(self) -> str:
        return "dogdrip"

    @property
    def display_name(self) -> str:
        return "개드립"

    @property
    def base_url(self) -> str:
        return "https://www.dogdrip.net"

    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
        """개드립 게시판, 추천순 정렬"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/index.php?mid=dogdrip&sort_index=voted_count&order_type=desc&page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = soup.select("li.ed.webzine")
            if not rows:
                break

            for row in rows:
                try:
                    article = self._parse_row(row)
                    if article:
                        articles.append(article)
                except Exception:
                    continue

        return articles

    def _parse_row(self, row) -> ArticleData | None:
        title_a = row.select_one(".title a.title-link")
        if not title_a:
            return None

        title = title_a.get_text(strip=True)
        href = title_a.get("href", "")
        if not href:
            return None
        # Strip query params (sort_index/page) for canonical URL
        href = href.split("?")[0]
        if not href.startswith("http"):
            href = self.base_url + href

        # Comment count: span next to title link
        comment_count = 0
        cmt_span = title_a.find_next_sibling("span", class_="text-primary")
        if cmt_span:
            nums = re.findall(r"\d+", cmt_span.get_text())
            if nums:
                comment_count = int(nums[0])

        # Like count: span next to thumbs-up icon
        like_count = 0
        thumbs = row.select_one("i.fa-thumbs-up")
        if thumbs:
            # The like number is in the next sibling span of the icon's wrapping span
            wrap = thumbs.find_parent("span")
            if wrap:
                like_span = wrap.find_next_sibling("span", class_="text-primary")
                if like_span:
                    nums = re.findall(r"\d+", like_span.get_text())
                    if nums:
                        like_count = int(nums[0])

        # Published_at: text next to clock icon ("16 분 전")
        published_at = None
        clock = row.select_one("i.fa-clock")
        if clock:
            wrap = clock.find_parent("span")
            if wrap:
                published_at = self._parse_date(wrap.get_text(strip=True))

        image_urls, video_urls, text_content = self._get_article_images(href)

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            video_urls=video_urls,
            view_count=0,
            like_count=like_count,
            comment_count=comment_count,
            published_at=published_at,
            content=text_content,
        )

    def _get_article_images(self, url: str) -> tuple[list[str], list[str], str | None]:
        try:
            soup = self.fetch_html(url)
            content = soup.select_one("div.xe_content")
            if not content:
                return [], [], None

            images = []
            for img in content.select("img"):
                src = img.get("src") or img.get("data-src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = self.base_url + src
                    images.append(src)

            videos = self._extract_videos(content)
            text_content = self._extract_text_content(content)
            return images[:50], videos, text_content
        except Exception:
            return [], [], None

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank", "ddcoa"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
