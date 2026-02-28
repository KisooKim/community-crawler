import re
from crawlers.base import BaseCrawler, ArticleData


class ClienCrawler(BaseCrawler):
    """클리앙 크롤러"""

    @property
    def site_name(self) -> str:
        return "clien"

    @property
    def display_name(self) -> str:
        return "클리앙"

    @property
    def base_url(self) -> str:
        return "https://www.clien.net"

    def get_popular_articles(self) -> list[ArticleData]:
        """오늘의 추천글 수집"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/service/recommend?po={page - 1}"
            soup = self.fetch_html(url, delay=(page > 1))

            items = [
                i for i in soup.select(".list_item.symph_row")
                if "notice" not in i.get("class", [])
            ]
            if not items:
                break

            for item in items:
                try:
                    article = self._parse_list_item(item)
                    if article:
                        articles.append(article)
                except Exception:
                    continue

        return articles

    def _parse_list_item(self, item) -> ArticleData | None:
        link = item.select_one("a.list_subject")
        if not link:
            return None

        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href
        # Remove query params for cleaner URL
        href = href.split("?")[0]

        view_count = 0
        hit_el = item.select_one(".hit")
        if hit_el:
            view_count = self._parse_count(hit_el.get_text(strip=True))

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
            content = soup.select_one(".post_article")
            if not content:
                return []

            for img in content.select("img"):
                src = img.get("src") or img.get("data-src")
                if src and self._is_valid_image(src):
                    if not src.startswith("http"):
                        src = "https:" + src if src.startswith("//") else self.base_url + src
                    images.append(src)

            return images[:10]
        except Exception:
            return []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank.gif"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)

    def _parse_count(self, text: str) -> int:
        """'14.6 k' -> 14600, '3.4 M' -> 3400000"""
        text = text.strip().lower()
        multipliers = {"k": 1000, "m": 1000000}
        for suffix, mult in multipliers.items():
            if text.endswith(suffix):
                try:
                    return int(float(text[:-1].strip()) * mult)
                except ValueError:
                    return 0
        numbers = re.findall(r"\d+", text.replace(",", ""))
        return int(numbers[0]) if numbers else 0
