import re
from crawlers.base import BaseCrawler, ArticleData


class TheqooCrawler(BaseCrawler):
    """더쿠 크롤러"""

    @property
    def site_name(self) -> str:
        return "theqoo"

    @property
    def display_name(self) -> str:
        return "더쿠"

    @property
    def base_url(self) -> str:
        return "https://theqoo.net"

    def get_popular_articles(self) -> list[ArticleData]:
        """핫 게시판"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/hot?page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = [
                tr for tr in soup.select("table tr")
                if "notice" not in tr.get("class", []) and tr.select("td.title")
            ]
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

        title_a = title_td.select_one("a")
        if not title_a:
            return None

        title = title_a.get_text(strip=True)
        href = title_a.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        view_count = 0
        views_td = row.select_one("td.m_no")
        if views_td:
            numbers = re.findall(r"\d+", views_td.get_text(strip=True).replace(",", ""))
            if numbers:
                view_count = int(numbers[0])

        comment_count = 0
        reply_el = title_td.select_one("a.replyNum")
        if reply_el:
            numbers = re.findall(r"\d+", reply_el.get_text(strip=True))
            if numbers:
                comment_count = int(numbers[0])

        image_urls = self._get_article_images(href)

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            view_count=view_count,
            comment_count=comment_count,
        )

    def _get_article_images(self, url: str) -> list[str]:
        try:
            soup = self.fetch_html(url)
            images = []
            content = soup.select_one(".xe_content")
            if not content:
                return []

            for img in content.select("img"):
                src = img.get("src") or img.get("data-src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    images.append(src)

            return images[:10]
        except Exception:
            return []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
