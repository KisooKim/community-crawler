import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from crawlers.base import BaseCrawler, ArticleData


class MlbparkCrawler(BaseCrawler):
    """엠엘비파크 크롤러"""

    @property
    def site_name(self) -> str:
        return "mlbpark"

    @property
    def display_name(self) -> str:
        return "엠엘비파크"

    @property
    def base_url(self) -> str:
        return "https://mlbpark.donga.com"

    def get_popular_articles(self) -> list[ArticleData]:
        """TODAY BEST 인기글 수집"""
        articles = []
        url = f"{self.base_url}/mp/best.php?b=bullpen"
        soup = self.fetch_html(url)

        rows = soup.select("table.tbl_type01 tbody tr")
        for row in rows:
            try:
                article = self._parse_row(row)
                if article:
                    articles.append(article)
            except Exception:
                continue

        return articles

    def _parse_row(self, row) -> ArticleData | None:
        title_link = row.select_one("a.txt")
        if not title_link:
            return None

        title = title_link.get("alt") or title_link.get_text(strip=True)
        if not title:
            return None

        href = title_link.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        # Strip list pagination param
        parsed = urlparse(href)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params.pop("p", None)
        href = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

        # best.php doesn't show engagement on list — get from detail page
        images, video_urls, like_count, view_count, comment_count = self._get_article_detail(href)

        return ArticleData(
            title=title,
            url=href,
            image_urls=images,
            video_urls=video_urls,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
        )

    def _get_article_detail(self, url: str) -> tuple[list[str], list[str], int, int, int]:
        """상세 페이지에서 이미지 + 비디오 + 추천수 + 조회수 + 댓글수 추출"""
        try:
            soup = self.fetch_html(url)

            # div.text2: 추천 203 조회 38,179 댓글 N
            like_count = 0
            view_count = 0
            comment_count = 0

            info_div = soup.select_one("div.text2")
            if info_div:
                # 추천수: #likeCnt (inside <a> wrapper)
                like_el = info_div.select_one("#likeCnt")
                if like_el:
                    nums = re.findall(r"\d+", like_el.get_text(strip=True).replace(",", ""))
                    if nums:
                        like_count = int(nums[0])
                # 조회수: span.val without id (not likeCnt/replyCnt)
                for val_span in info_div.select("span.val"):
                    if not val_span.get("id"):
                        nums = re.findall(r"\d+", val_span.get_text(strip=True).replace(",", ""))
                        if nums:
                            view_count = int(nums[0])
                            break
                # 댓글수: #replyCnt
                reply_el = info_div.select_one("#replyCnt")
                if reply_el:
                    nums = re.findall(r"\d+", reply_el.get_text(strip=True))
                    if nums:
                        comment_count = int(nums[0])

            images = []
            content = soup.select_one("div.ar_txt#contentDetail") or soup.select_one("div.ar_txt")
            if content:
                for img in content.select("img"):
                    src = img.get("src")
                    if src and self._is_valid_image(src):
                        if src.startswith("//"):
                            src = "https:" + src
                        elif not src.startswith("http"):
                            src = self.base_url + src
                        images.append(src)

            videos = self._extract_videos(content) if content else []
            return images[:50], videos, like_count, view_count, comment_count
        except Exception:
            return [], [], 0, 0, 0

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank", "loading"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
