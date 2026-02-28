import re
from crawlers.base import BaseCrawler, ArticleData


class RuliwebCrawler(BaseCrawler):
    """루리웹 크롤러"""

    @property
    def site_name(self) -> str:
        return "ruliweb"

    @property
    def display_name(self) -> str:
        return "루리웹"

    @property
    def base_url(self) -> str:
        return "https://bbs.ruliweb.com"

    def get_popular_articles(self) -> list[ArticleData]:
        """베스트 유머 게시판"""
        articles = []
        url = f"{self.base_url}/best/humor"
        soup = self.fetch_html(url, delay=False)

        rows = soup.select("tr.table_body.blocktarget")[:30]

        for row in rows:
            try:
                article = self._parse_row(row)
                if article:
                    articles.append(article)
            except Exception:
                continue

        return articles

    def _parse_row(self, row) -> ArticleData | None:
        title_a = row.select_one("a.subject_link")
        if not title_a:
            return None

        title = title_a.get_text(strip=True)
        # Remove trailing comment count like "(64)"
        title = re.sub(r"\(\d+\)$", "", title).strip()

        href = title_a.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        view_count = 0
        hit_td = row.select_one("td.hit")
        if hit_td:
            numbers = re.findall(r"\d+", hit_td.get_text(strip=True).replace(",", ""))
            if numbers:
                view_count = int(numbers[0])

        like_count = 0
        recom_td = row.select_one("td.recomd")
        if recom_td:
            numbers = re.findall(r"\d+", recom_td.get_text(strip=True))
            if numbers:
                like_count = int(numbers[0])

        image_urls = self._get_article_images(href)

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            view_count=view_count,
            like_count=like_count,
        )

    def _get_article_images(self, url: str) -> list[str]:
        try:
            soup = self.fetch_html(url)
            images = []
            content = soup.select_one(".view_content")
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
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
