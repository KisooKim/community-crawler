import re
from crawlers.base import BaseCrawler, ArticleData


class CoinpanCrawler(BaseCrawler):
    """코인판 크롤러"""

    @property
    def site_name(self) -> str:
        return "coinpan"

    @property
    def display_name(self) -> str:
        return "코인판"

    @property
    def base_url(self) -> str:
        return "https://coinpan.com"

    def get_popular_articles(self) -> list[ArticleData]:
        """자유게시판 추천순"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/index.php?mid=free&sort_index=voted_count&order_type=desc&page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = soup.select("#board_list table tr")
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
        title_td = row.select_one("td.title")
        if not title_td:
            return None

        title_link = title_td.select_one("a[href]")
        if not title_link:
            return None

        title = title_link.get_text(strip=True)
        if not title:
            return None

        href = title_link.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        view_count = 0
        view_td = row.select_one("td.readed")
        if view_td:
            nums = re.findall(r"\d+", view_td.get_text(strip=True).replace(",", ""))
            if nums:
                view_count = int(nums[0])

        like_count = 0
        vote_td = row.select_one("td.voted")
        if vote_td:
            nums = re.findall(r"\d+", vote_td.get_text(strip=True))
            if nums:
                like_count = int(nums[0])

        comment_count = 0
        comment_link = title_td.select_one("a[title='Replies'] span.number")
        if comment_link:
            nums = re.findall(r"\d+", comment_link.get_text())
            if nums:
                comment_count = int(nums[0])

        image_urls = self._get_article_images(href)

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
        )

    def _get_article_images(self, url: str) -> list[str]:
        try:
            soup = self.fetch_html(url)
            images = []
            content = soup.select_one("div.read_body div.xe_content") or soup.select_one("div.read_body")
            if not content:
                return []

            for img in content.select("img"):
                src = img.get("src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = self.base_url + src
                    images.append(src)

            return images[:10]
        except Exception:
            return []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank", "loading"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
