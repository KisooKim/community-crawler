import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from crawlers.base import BaseCrawler, ArticleData


class DcinsideCrawler(BaseCrawler):
    """디시인사이드 크롤러"""

    @property
    def site_name(self) -> str:
        return "dcinside"

    @property
    def display_name(self) -> str:
        return "디시인사이드"

    @property
    def base_url(self) -> str:
        return "https://gall.dcinside.com"

    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
        """실시간 베스트 갤러리"""
        articles = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.base_url}/board/lists/?id=dcbest&page={page}"
            soup = self.fetch_html(url, delay=(page > 1))

            rows = soup.select("table.gall_list tbody tr.ub-content.us-post")
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
        # Skip surveys, notices, ads
        num_td = row.select_one("td.gall_num")
        if num_td:
            num_text = num_td.get_text(strip=True)
            if num_text in ("설문", "공지", "AD"):
                return None

        title_a = row.select_one("td.gall_tit a[view-msg]")
        if not title_a:
            return None

        # Get title text, strip gallery origin tags like [새갤]
        title = title_a.get_text(strip=True)
        title = re.sub(r"^\[.+?\]\s*", "", title).strip()
        if not title:
            return None

        href = title_a.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        # Strip list pagination param — same article gets different page= per list page
        parsed = urlparse(href)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params.pop("page", None)
        href = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

        view_count = 0
        count_td = row.select_one("td.gall_count")
        if count_td:
            nums = re.findall(r"\d+", count_td.get_text(strip=True))
            if nums:
                view_count = int(nums[0])

        like_count = 0
        recomm_td = row.select_one("td.gall_recommend")
        if recomm_td:
            nums = re.findall(r"\d+", recomm_td.get_text(strip=True))
            if nums:
                like_count = int(nums[0])

        comment_count = 0
        reply_span = row.select_one("td.gall_tit span.reply_num")
        if reply_span:
            nums = re.findall(r"\d+", reply_span.get_text())
            if nums:
                comment_count = int(nums[0])

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
            content = soup.select_one("div.write_div")
            if not content:
                return [], []

            for img in content.select("img"):
                # Handle lazy loading: data-original takes priority
                src = img.get("data-original") or img.get("src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    images.append(src)

            videos = self._extract_videos(content)
            return images[:50], videos
        except Exception:
            return [], []

    def _is_valid_image(self, url: str) -> bool:
        exclude = [
            "emoticon", "icon", "btn_", "logo", "banner", "ad_",
            "blank", "loading", "nstatic.dcinside.com",
        ]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
