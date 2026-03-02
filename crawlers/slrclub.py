import re
from crawlers.base import BaseCrawler, ArticleData


class SlrclubCrawler(BaseCrawler):
    """SLR클럽 크롤러"""

    @property
    def site_name(self) -> str:
        return "slrclub"

    @property
    def display_name(self) -> str:
        return "SLR클럽"

    @property
    def base_url(self) -> str:
        return "https://www.slrclub.com"

    def get_popular_articles(self) -> list[ArticleData]:
        """인기글 수집"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/bbs/zboard.php?id=hot_article&page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = soup.select("tbody tr")
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
        title_td = row.select_one("td.sbj")
        if not title_td:
            return None

        title_link = title_td.select_one("a[href*='/bbs/vx2.php']")
        if not title_link:
            return None

        title = title_link.get_text(strip=True)
        if not title:
            return None

        href = title_link.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        view_count = 0
        view_td = row.select_one("td.list_click")
        if view_td:
            nums = re.findall(r"\d+", view_td.get_text(strip=True).replace(",", ""))
            if nums:
                view_count = int(nums[0])

        like_count = 0
        vote_td = row.select_one("td.list_vote")
        if vote_td:
            nums = re.findall(r"\d+", vote_td.get_text(strip=True))
            if nums:
                like_count = int(nums[0])

        # 댓글 수 - 제목 뒤 [N] 형식
        comment_count = 0
        sbj_text = title_td.get_text()
        comment_match = re.search(r"\[(\d+)\]", sbj_text)
        if comment_match:
            comment_count = int(comment_match.group(1))

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
            content = soup.select_one("div#userct")
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
            return images[:10], videos
        except Exception:
            return [], []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank",
                    "loading", "smile", "smiley"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
