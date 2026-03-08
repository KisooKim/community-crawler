import re
from crawlers.base import BaseCrawler, ArticleData


class TodayhumorCrawler(BaseCrawler):
    """오늘의유머 크롤러"""

    @property
    def site_name(self) -> str:
        return "todayhumor"

    @property
    def display_name(self) -> str:
        return "오늘의유머"

    @property
    def base_url(self) -> str:
        return "http://www.todayhumor.co.kr"

    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
        """베스트오브베스트 게시판"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/board/list.php?table=bestofbest&page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = soup.select("table.table_list tr.view")
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
        subject_td = row.select_one("td.subject")
        if not subject_td:
            return None

        title_a = subject_td.select_one("a")
        if not title_a:
            return None

        title = title_a.get_text(strip=True)
        href = title_a.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        # Check for photo indicator
        has_photo = bool(subject_td.select_one("img[src*='list_icon_photo']"))
        if not has_photo:
            return None  # Skip text-only posts

        view_count = 0
        hits_td = row.select_one("td.hits")
        if hits_td:
            numbers = re.findall(r"\d+", hits_td.get_text(strip=True).replace(",", ""))
            if numbers:
                view_count = int(numbers[0])

        like_count = 0
        oknok_td = row.select_one("td.oknok")
        if oknok_td:
            numbers = re.findall(r"\d+", oknok_td.get_text(strip=True))
            if numbers:
                like_count = int(numbers[0])

        comment_count = 0
        cmt_span = subject_td.select_one("span.list_memo_count_span")
        if cmt_span:
            nums = re.findall(r"\d+", cmt_span.get_text())
            if nums:
                comment_count = int(nums[0])

        image_urls, video_urls = self._get_article_images(href)

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
            content = soup.select_one("div.viewContent")
            if not content:
                return [], []

            for img in content.select("img"):
                src = img.get("src") or img.get("data-src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = self.base_url + "/" + src.lstrip("/")
                    images.append(src)

            videos = self._extract_videos(content)
            return images[:50], videos
        except Exception:
            return [], []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
