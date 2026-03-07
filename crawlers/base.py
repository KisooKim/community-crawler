import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import time
import random
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
]


@dataclass
class ArticleData:
    """크롤링된 글 데이터"""
    title: str
    url: str
    image_urls: list[str]
    video_urls: list[str] = field(default_factory=list)
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    published_at: datetime | None = None
    content: str | None = None


class BaseCrawler(ABC):
    """크롤러 베이스 클래스"""

    # 페이지네이션
    MAX_PAGES = 3  # 최대 크롤링 페이지 수

    # 429/503 시 재시도 설정
    RETRY_STATUS_CODES = {429, 503}
    MAX_RETRIES = 2
    BACKOFF_BASE = 10  # 초

    def __init__(self):
        ua = random.choice(USER_AGENTS)
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            follow_redirects=True,
        )
        self._session_initialized = False

    def _init_session(self):
        """메인 페이지 방문으로 쿠키 세션 초기화"""
        if self._session_initialized:
            return
        try:
            self.client.get(self.base_url)
            time.sleep(random.uniform(2.0, 4.0))
            self._session_initialized = True
        except Exception:
            pass

    @property
    @abstractmethod
    def site_name(self) -> str:
        """사이트 식별자 (예: fmkorea)"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """사이트 표시명 (예: 에펨코리아)"""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """사이트 기본 URL"""
        pass

    @abstractmethod
    def get_popular_articles(self, skip_urls: set[str] | None = None) -> list[ArticleData]:
        """인기글 목록 수집. skip_urls가 주어지면 해당 URL은 상세 페이지 방문 생략."""
        pass

    def fetch_html(self, url: str, delay: bool = True) -> BeautifulSoup:
        """HTML 가져오기 (429/503 시 백오프 재시도)"""
        self._init_session()
        if delay:
            time.sleep(random.uniform(2.0, 5.0))

        for attempt in range(self.MAX_RETRIES + 1):
            response = self.client.get(url, headers={"Referer": self.base_url})

            if response.status_code not in self.RETRY_STATUS_CODES:
                response.raise_for_status()
                return BeautifulSoup(response.text, "lxml")

            # 재시도 가능한 에러
            if attempt < self.MAX_RETRIES:
                wait = self.BACKOFF_BASE * (2 ** attempt) + random.uniform(1, 5)
                logger.warning(
                    f"[{self.site_name}] {response.status_code} on {url}, "
                    f"retry {attempt + 1}/{self.MAX_RETRIES} after {wait:.0f}s"
                )
                time.sleep(wait)
            else:
                logger.warning(
                    f"[{self.site_name}] {response.status_code} on {url}, "
                    f"giving up after {self.MAX_RETRIES} retries"
                )
                response.raise_for_status()

    def _extract_videos(self, content) -> list[str]:
        """본문에서 <video> 태그의 MP4/WebM URL 추출"""
        videos = []
        if not content:
            return videos
        for video in content.select("video"):
            src = video.get("src")
            if src:
                videos.append(src)
                continue
            source = video.select_one("source")
            if source:
                src = source.get("src")
                if src:
                    videos.append(src)
        # URL 정규화
        result = []
        for src in videos:
            if src.startswith("//"):
                src = "https:" + src
            elif not src.startswith("http"):
                src = self.base_url + src
            result.append(src)
        return result[:5]

    def close(self):
        """리소스 정리"""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
