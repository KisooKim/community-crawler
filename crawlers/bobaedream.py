import re
from crawlers.base import BaseCrawler, ArticleData


class BobaedreamCrawler(BaseCrawler):
    """보배드림 크롤러"""

    @property
    def site_name(self) -> str:
        return "bobaedream"

    @property
    def display_name(self) -> str:
        return "보배드림"

    @property
    def base_url(self) -> str:
        return "https://www.bobaedream.co.kr"

    def get_popular_articles(self) -> list[ArticleData]:
        """베스트글 게시판"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/list.php?code=best&page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = soup.select("#boardlist tbody tr[itemscope]")
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
        title_a = row.select_one("td.pl14 a.bsubject")
        if not title_a:
            return None

        title = title_a.get("title") or title_a.get_text(strip=True)
        href = title_a.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + "/" + href.lstrip("/")

        # Check for image attachment
        has_image = bool(row.select_one("td.pl14 img.jpg") or row.select_one("td.pl14 img.png"))
        if not has_image:
            return None

        view_count = 0
        count_td = row.select_one("td.count")
        if count_td:
            nums = re.findall(r"[\d,]+", count_td.get_text(strip=True))
            if nums:
                view_count = int(nums[0].replace(",", ""))

        like_count = 0
        recomm_td = row.select_one("td.recomm font")
        if recomm_td:
            nums = re.findall(r"\d+", recomm_td.get_text(strip=True))
            if nums:
                like_count = int(nums[0])

        comment_count = 0
        reply_el = row.select_one("td.pl14 strong.totreply")
        if reply_el:
            nums = re.findall(r"\d+", reply_el.get_text())
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
            content = soup.select_one("div.bodyCont")
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
            return images[:10], videos
        except Exception:
            return [], []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank", "noimg"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
