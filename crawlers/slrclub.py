import re
import time
import random
from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright
from crawlers.base import BaseCrawler, ArticleData


class SlrclubCrawler(BaseCrawler):
    """SLR클럽 크롤러 (Patchright 브라우저, self-hosted runner 전용)"""

    @property
    def site_name(self) -> str:
        return "slrclub"

    @property
    def display_name(self) -> str:
        return "SLR클럽"

    @property
    def base_url(self) -> str:
        return "https://www.slrclub.com"

    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
        """인기글 수집 (JS 렌더링 필요 → Patchright)"""
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        page = context.new_page()

        articles = []
        try:
            # 1단계: 리스트 페이지에서 기본 정보 수집
            list_items = []
            for pg in range(1, self.MAX_PAGES + 1):
                url = f"{self.base_url}/bbs/zboard.php?id=hot_article&page={pg}"
                if pg > 1:
                    time.sleep(random.uniform(2.0, 4.0))
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # JS가 테이블을 렌더링할 시간 대기
                page.wait_for_selector("tbody tr td.sbj", timeout=10000)
                soup = BeautifulSoup(page.content(), "lxml")

                rows = soup.select("tbody tr")
                if not rows:
                    break

                for row in rows:
                    parsed = self._parse_list_item(row)
                    if parsed:
                        list_items.append(parsed)

            # 2단계: 새 글만 상세 페이지 방문
            for info in list_items:
                if skip_urls and info["url"] in skip_urls:
                    continue
                try:
                    article = self._build_article(info, page)
                    if article:
                        articles.append(article)
                except Exception:
                    continue
        finally:
            page.close()
            context.close()
            browser.close()
            pw.stop()

        return articles

    def _parse_list_item(self, row) -> dict | None:
        """리스트 행에서 기본 정보 추출"""
        title_td = row.select_one("td.sbj")
        if not title_td:
            return None

        title_link = title_td.select_one("a[href*='/bbs/vx2.php']")
        if not title_link:
            return None

        title = title_link.get_text(strip=True)
        if not title:
            return None

        href = title_link.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        view_count = 0
        view_td = row.select_one("td.list_click")
        if view_td:
            nums = re.findall(r"\d+", view_td.get_text(strip=True).replace(",", ""))
            if nums:
                view_count = int(nums[0])

        like_count = 0
        vote_td = row.select_one("td.list_vote")
        if vote_td:
            nums = re.findall(r"\d+", vote_td.get_text(strip=True))
            if nums:
                like_count = int(nums[0])

        comment_count = 0
        sbj_text = title_td.get_text()
        comment_match = re.search(r"\[(\d+)\]", sbj_text)
        if comment_match:
            comment_count = int(comment_match.group(1))

        return {
            "title": title,
            "url": href,
            "view_count": view_count,
            "like_count": like_count,
            "comment_count": comment_count,
        }

    def _build_article(self, info: dict, page) -> ArticleData | None:
        """상세 페이지 방문하여 이미지/비디오 추출"""
        image_urls, video_urls = self._get_article_detail(info["url"], page)

        return ArticleData(
            title=info["title"],
            url=info["url"],
            image_urls=image_urls,
            video_urls=video_urls,
            view_count=info["view_count"],
            like_count=info["like_count"],
            comment_count=info["comment_count"],
        )

    def _get_article_detail(self, url: str, page) -> tuple[list[str], list[str]]:
        """상세 페이지에서 이미지 + 비디오 추출 (브라우저 재사용)"""
        try:
            time.sleep(random.uniform(1.0, 2.0))
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            soup = BeautifulSoup(page.content(), "lxml")

            images = []
            content = soup.select_one("div#userct")
            if not content:
                return [], []

            for img in content.select("img"):
                src = img.get("src")
                if src and self._is_valid_image(src):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = self.base_url + src
                    images.append(src)

            videos = self._extract_videos(content)
            return images[:50], videos
        except Exception:
            return [], []

    def _is_valid_image(self, url: str) -> bool:
        exclude = ["emoticon", "icon", "btn_", "logo", "banner", "ad_", "blank",
                    "loading", "smile", "smiley"]
        url_lower = url.lower()
        return not any(p in url_lower for p in exclude)
