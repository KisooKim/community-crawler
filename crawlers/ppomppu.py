import re
from crawlers.base import BaseCrawler, ArticleData


class PpomppuCrawler(BaseCrawler):
    """뽐뿌 크롤러"""

    @property
    def site_name(self) -> str:
        return "ppomppu"

    @property
    def display_name(self) -> str:
        return "뽐뿌"

    @property
    def base_url(self) -> str:
        return "https://www.ppomppu.co.kr"

    def get_popular_articles(self) -> list[ArticleData]:
        """핫 게시판 (커뮤니티)"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/hot.php?category=1&page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = soup.select("tr.baseList")
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
        title_a = row.select_one("a.baseList-title")
        if not title_a:
            return None

        title = title_a.get_text(strip=True)
        href = title_a.get("href", "")
        if not href.startswith("http"):
            href = f"{self.base_url}/zboard/{href}"

        view_count = 0
        views_td = row.select_one("td.baseList-views")
        if views_td:
            numbers = re.findall(r"\d+", views_td.get_text(strip=True).replace(",", ""))
            if numbers:
                view_count = int(numbers[0])

        image_urls = self._get_article_images(href)

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            view_count=view_count,
        )

    def _get_article_images(self, url: str) -> list[str]:
        try:
            soup = self.fetch_html(url)
            images = []
            content = soup.select_one("td.board-contents")
            if not content:
                return []

            for img in content.select("img"):
                src = img.get("src") or img.get("data-src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = self.base_url + "/" + src.lstrip("/")
                    images.append(src)

            return images[:10]
        except Exception:
            return []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
