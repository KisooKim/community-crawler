import re
from crawlers.base import BaseCrawler, ArticleData


class InvenCrawler(BaseCrawler):
    """인벤 크롤러"""

    @property
    def site_name(self) -> str:
        return "inven"

    @property
    def display_name(self) -> str:
        return "인벤"

    @property
    def base_url(self) -> str:
        return "https://www.inven.co.kr"

    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
        """오픈이슈 갤러리 10추글"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/board/webzine/2097?my=chu&page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = soup.select("table.thumbnail tbody tr")
            rows = [r for r in rows if "notice" not in " ".join(r.get("class", []))]
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
        title_link = row.select_one("a.subject-link")
        if not title_link:
            return None

        # 카테고리 태그 제거
        category = title_link.select_one("span.category")
        if category:
            category.decompose()

        title = title_link.get_text(strip=True)
        if not title:
            return None

        href = title_link.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        view_count = 0
        view_td = row.select_one("td.view")
        if view_td:
            view_count = self._parse_count(view_td.get_text(strip=True))

        like_count = 0
        reco_td = row.select_one("td.reco")
        if reco_td:
            nums = re.findall(r"\d+", reco_td.get_text(strip=True))
            if nums:
                like_count = int(nums[0])

        comment_count = 0
        comment_el = row.select_one("span.con-comment")
        if comment_el:
            nums = re.findall(r"\d+", comment_el.get_text())
            if nums:
                comment_count = int(nums[0])

        published_at = None
        date_td = row.select_one("td.date")
        if date_td:
            published_at = self._parse_date(date_td.get_text(strip=True))

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
            soup = self.fetch_html(url)
            images = []
            content = soup.select_one("#powerbbsBody") or soup.select_one("#tbArticle")
            if not content:
                return [], []

            for img in content.select("img"):
                src = img.get("src") or img.get("data-src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = self.base_url + src
                    images.append(src)

            videos = self._extract_videos(content)
            return images[:50], videos
        except Exception:
            return [], []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank", "loading",
                    "inven.co.kr/common", "static.inven.co.kr"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)

    def _parse_count(self, text: str) -> int:
        text = text.strip().replace(",", "")
        if "만" in text:
            try:
                return int(float(text.replace("만", "")) * 10000)
            except ValueError:
                return 0
        nums = re.findall(r"\d+", text)
        return int(nums[0]) if nums else 0
