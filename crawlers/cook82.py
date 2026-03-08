import re
from crawlers.base import BaseCrawler, ArticleData


class Cook82Crawler(BaseCrawler):
    """82쿡 크롤러"""

    @property
    def site_name(self) -> str:
        return "cook82"

    @property
    def display_name(self) -> str:
        return "82쿡"

    @property
    def base_url(self) -> str:
        return "https://www.82cook.com"

    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
        """자유게시판 인기글"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/entiz/enti.php?bn=15&searchType=best&page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = soup.select("#bbs table tr")
            rows = [r for r in rows if "noticeList" not in " ".join(r.get("class", []))]
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
        title_td = row.select_one("td.title")
        if not title_td:
            return None

        title_link = title_td.select_one("a")
        if not title_link:
            return None

        title = title_link.get_text(strip=True)
        if not title:
            return None

        href = title_link.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + "/entiz/" + href

        view_count = 0
        num_tds = row.select("td.numbers")
        if num_tds:
            last_num = num_tds[-1].get_text(strip=True).replace(",", "")
            nums = re.findall(r"\d+", last_num)
            if nums:
                view_count = int(nums[0])

        comment_count = 0
        comment_el = title_td.select_one("em")
        if comment_el:
            nums = re.findall(r"\d+", comment_el.get_text())
            if nums:
                comment_count = int(nums[0])

        image_urls, video_urls = self._get_article_images(href)

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            video_urls=video_urls,
            view_count=view_count,
            comment_count=comment_count,
        )

    def _get_article_images(self, url: str) -> tuple[list[str], list[str]]:
        try:
            soup = self.fetch_html(url)
            images = []
            content = soup.select_one("#articleBody")
            if not content:
                return [], []

            for img in content.select("img"):
                src = img.get("src")
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
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank", "loading"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
