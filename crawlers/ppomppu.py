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

    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
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

    COMMERCIAL_BOARDS = {
        "ppomppu", "ppomppu2", "ppomppu4", "ppomppu8",
        "hotdeal", "pmarket", "pmarket2", "pmarket3",
        "card_market", "pmarket7", "pmarket8", "sponsor",
    }

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

        # 상업성 게시판 제외
        board_id_match = re.search(r"[?&]id=([^&]+)", href)
        if board_id_match and board_id_match.group(1) in self.COMMERCIAL_BOARDS:
            return None

        view_count = 0
        like_count = 0
        published_at = None
        # td.board_date: [0]=시간, [1]=추천-반대, [2]=조회수
        date_tds = row.select("td.board_date")
        if len(date_tds) >= 3:
            published_at = self._parse_date(date_tds[0].get_text(strip=True))
            nums = re.findall(r"\d+", date_tds[-1].get_text(strip=True).replace(",", ""))
            if nums:
                view_count = int(nums[0])
            like_nums = re.findall(r"\d+", date_tds[1].get_text(strip=True))
            if like_nums:
                like_count = int(like_nums[0])

        image_urls, video_urls = self._get_article_images(href)

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
            video_urls=video_urls,
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
            published_at=published_at,
        )

    def _get_article_images(self, url: str) -> tuple[list[str], list[str]]:
        """모바일 페이지에서 본문 이미지 + 비디오 추출 (데스크톱은 JS 렌더링 필요)"""
        try:
            # 데스크톱 URL → 모바일 URL 변환
            import re as _re
            m = _re.search(r"[?&]id=([^&]+)", url)
            n = _re.search(r"[?&]no=(\d+)", url)
            if not m or not n:
                return [], []
            mobile_url = f"https://m.ppomppu.co.kr/new/bbs_view.php?id={m.group(1)}&no={n.group(1)}"

            soup = self.fetch_html(mobile_url)
            content = soup.select_one("div.bbs.view")
            if not content:
                return [], []

            # 댓글/팝업 영역 제거
            for el in content.select(".comment-area, .hot-comment-preview, .comment-list, .popup-body"):
                el.decompose()

            images = []
            for img in content.select("img"):
                src = img.get("src") or img.get("data-src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = "https://m.ppomppu.co.kr" + src
                    images.append(src)

            videos = self._extract_videos(content)
            return images[:50], videos
        except Exception:
            return [], []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_",
                    "blank", "loading", "noimage", "/images/"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
