import re
from crawlers.base import BaseCrawler, ArticleData


class InstizCrawler(BaseCrawler):
    """인스티즈 크롤러"""

    @property
    def site_name(self) -> str:
        return "instiz"

    @property
    def display_name(self) -> str:
        return "인스티즈"

    @property
    def base_url(self) -> str:
        return "https://www.instiz.net"

    def get_popular_articles(self) -> list[ArticleData]:
        """HOT 게시판"""
        articles = []
        url = f"{self.base_url}/hot.htm"
        soup = self.fetch_html(url, delay=False)

        links = soup.select("div.result_search a[href*='/pt/']")
        for link in links[:30]:
            try:
                article = self._parse_item(link)
                if article:
                    articles.append(article)
            except Exception:
                continue

        return articles

    def _parse_item(self, link) -> ArticleData | None:
        title_el = link.select_one("h3.search_title")
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        href = link.get("href", "")

        # 조회수, 추천수
        view_count = 0
        like_count = 0
        for span in link.select("span.minitext3"):
            text = span.get_text(strip=True)
            view_match = re.search(r"조회\s+([\d,]+)", text)
            if view_match:
                view_count = int(view_match.group(1).replace(",", ""))
            like_match = re.search(r"추천\s+([\d,]+)", text)
            if like_match:
                like_count = int(like_match.group(1).replace(",", ""))

        comment_count = 0
        cmt = link.select_one("span.cmt2")
        if cmt:
            nums = re.findall(r"\d+", cmt.get_text(strip=True))
            if nums:
                comment_count = int(nums[0])

        # 썸네일
        image_urls = []
        thumb_img = link.select_one("div.thumb img")
        if thumb_img:
            src = thumb_img.get("data-original") or thumb_img.get("src") or ""
            if src and self._is_valid_image(src):
                if src.startswith("//"):
                    src = "https:" + src
                elif not src.startswith("http"):
                    src = self.base_url + src
                image_urls.append(src)

        if not image_urls:
            return None  # 이미지 없는 글 스킵

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
        )

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank.gif", "noimg"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
