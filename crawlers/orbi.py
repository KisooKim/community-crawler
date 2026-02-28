import re
from crawlers.base import BaseCrawler, ArticleData


class OrbiCrawler(BaseCrawler):
    """오르비 크롤러"""

    @property
    def site_name(self) -> str:
        return "orbi"

    @property
    def display_name(self) -> str:
        return "오르비"

    @property
    def base_url(self) -> str:
        return "https://orbi.kr"

    def get_popular_articles(self) -> list[ArticleData]:
        """인기글 수집"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/list/hot?page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            items = soup.select("ul.post-list > li")
            items = [i for i in items if "notice" not in " ".join(i.get("class", []))]
            if not items:
                break

            for item in items:
                try:
                    article = self._parse_item(item)
                    if article:
                        articles.append(article)
                except Exception:
                    continue

        return articles

    def _parse_item(self, item) -> ArticleData | None:
        title_el = item.select_one("p.title a")
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        if not title:
            return None

        href = title_el.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href
        # ?type=hot 쿼리 제거
        href = href.split("?")[0]

        like_count = 0
        like_el = item.select_one("span.like-count")
        if like_el:
            nums = re.findall(r"\d+", like_el.get_text())
            if nums:
                like_count = int(nums[0])

        comment_count = 0
        comment_el = item.select_one("span.comment-count")
        if comment_el:
            nums = re.findall(r"\d+", comment_el.get_text())
            if nums:
                comment_count = int(nums[0])

        image_urls = self._get_article_images(href)

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            like_count=like_count,
            comment_count=comment_count,
        )

    def _get_article_images(self, url: str) -> list[str]:
        try:
            soup = self.fetch_html(url)
            images = []
            content = soup.select_one("div.content-wrap")
            if not content:
                return []

            for img in content.select("img"):
                src = img.get("src") or img.get("data-src")
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
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank",
                    "loading", "avatar", "fa-"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
