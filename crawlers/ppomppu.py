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
        title_td = row.select_one("td.title")
        if not title_td:
            return None

        # a.baseList-title 태그가 2개: 첫 번째는 빈 태그, 두 번째에 실제 제목
        title_links = title_td.select("a.baseList-title")
        title = ""
        href = ""
        for a in title_links:
            text = a.get_text(strip=True)
            if text:
                title = text
                href = a.get("href", "")
                break

        if not title or not href:
            return None

        # href가 /zboard/... 형태이므로 base_url에 바로 붙임
        if not href.startswith("http"):
            href = self.base_url + href

        view_count = 0
        # 조회수: 마지막 td.board_date
        date_tds = row.select("td.board_date")
        if len(date_tds) >= 3:
            nums = re.findall(r"\d+", date_tds[-1].get_text(strip=True).replace(",", ""))
            if nums:
                view_count = int(nums[0])

        # 리스트 썸네일 사용 (본문에 이미지가 없는 경우가 많음)
        image_urls = []
        thumb = title_td.select_one("a.baseList-thumb img")
        if thumb:
            src = thumb.get("src", "")
            if src and "noimage" not in src:
                if src.startswith("//"):
                    src = "https:" + src
                elif not src.startswith("http"):
                    src = self.base_url + src
                image_urls.append(src)

        # 댓글 수
        comment_count = 0
        comment_el = title_td.select_one("span.list_comment2")
        if comment_el:
            nums = re.findall(r"\d+", comment_el.get_text())
            if nums:
                comment_count = int(nums[0])

        return ArticleData(
            title=title,
            url=href,
            image_urls=image_urls,
            view_count=view_count,
            comment_count=comment_count,
        )
