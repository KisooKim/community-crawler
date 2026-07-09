import logging
import re as _re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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

    # ── Date parsing ──────────────────────────────────────────────────────
    KST = timezone(timedelta(hours=9))

    _RELATIVE_RE = _re.compile(r"(\d+)\s*(초|분|시간|일|개월|달)\s*전")
    _RELATIVE_UNITS = {"초": "seconds", "분": "minutes", "시간": "hours", "일": "days", "개월": "days", "달": "days"}
    _RELATIVE_MULTIPLIERS = {"초": 1, "분": 1, "시간": 1, "일": 1, "개월": 30, "달": 30}

    _DATE_PATTERNS = [
        (_re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?"), True),
        (_re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"), False),
        (_re.compile(r"(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})$"), False),
        (_re.compile(r"(\d{1,2})[.\-/](\d{1,2})\s+(\d{1,2}):(\d{2})"), True),
        (_re.compile(r"^(\d{1,2})[.\-/](\d{1,2})$"), False),
        (_re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$"), True),
    ]

    @classmethod
    def _parse_date(cls, text: str) -> datetime | None:
        if not text:
            return None
        text = text.strip()
        now_kst = datetime.now(cls.KST)

        if text in ("방금", "방금전", "방금 전"):
            return now_kst.astimezone(timezone.utc).replace(tzinfo=None)

        m = cls._RELATIVE_RE.search(text)
        if m:
            amount = int(m.group(1))
            unit_kr = m.group(2)
            unit = cls._RELATIVE_UNITS.get(unit_kr, "hours")
            mult = cls._RELATIVE_MULTIPLIERS.get(unit_kr, 1)
            delta = timedelta(**{unit: amount * mult})
            dt = now_kst - delta
            return dt.astimezone(timezone.utc).replace(tzinfo=None)

        for pattern, has_time in cls._DATE_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue
            groups = m.groups()

            if len(groups) >= 5:
                y, mo, d, h, mi = int(groups[0]), int(groups[1]), int(groups[2]), int(groups[3]), int(groups[4])
                s = int(groups[5]) if len(groups) > 5 and groups[5] else 0
            elif len(groups) == 4 and has_time:
                y = now_kst.year
                mo, d, h, mi, s = int(groups[0]), int(groups[1]), int(groups[2]), int(groups[3]), 0
                if mo > now_kst.month or (mo == now_kst.month and d > now_kst.day):
                    y -= 1
            elif len(groups) == 3 and not has_time:
                y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
                h, mi, s = 12, 0, 0
            elif len(groups) in (2, 3) and has_time and len(groups) <= 3:
                y, mo, d = now_kst.year, now_kst.month, now_kst.day
                h, mi = int(groups[0]), int(groups[1])
                s = int(groups[2]) if len(groups) > 2 and groups[2] else 0
            elif len(groups) == 2 and not has_time:
                y = now_kst.year
                mo, d = int(groups[0]), int(groups[1])
                h, mi, s = 12, 0, 0
                if mo > now_kst.month or (mo == now_kst.month and d > now_kst.day):
                    y -= 1
            else:
                continue

            if y < 100:
                y += 2000

            try:
                dt = datetime(y, mo, d, h, mi, s, tzinfo=cls.KST)
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                continue

        return None

    @staticmethod
    def _extract_text_content(content_elem) -> str | None:
        """content div에서 본문 텍스트 추출 (이미지 위치를 [IMG] 마커로 보존).

        이미지 사이의 설명 텍스트를 보존하고, 이미지 위치에 [IMG] 마커를 넣어
        원글의 이미지-텍스트 배치 구조를 보존한다.

        예: "설명글\\n[IMG]\\n다음 설명\\n[IMG]\\n[IMG]\\n마무리"
        → 텍스트-이미지 interleaving 패턴 분석 및 프론트엔드 표시에 활용
        """
        if not content_elem:
            return None

        from bs4 import NavigableString, Tag
        from bs4.element import PreformattedString
        from copy import copy
        elem = copy(content_elem)

        # 불필요한 태그 제거
        for tag in elem.select("script, style, iframe, noscript, .signature, .og-div"):
            tag.decompose()

        # 재귀적으로 순회하며 텍스트와 [IMG] 마커를 순서대로 수집
        parts = []

        def _walk(node):
            # Comment/Doctype/CData 등은 NavigableString 서브클래스라 먼저 걸러야 한다
            # (fmkorea의 <!--serverLog: fNN__LAZY__--> 주석이 본문에 섞여 들어왔음)
            if isinstance(node, PreformattedString):
                return
            if isinstance(node, NavigableString):
                text = str(node).strip()
                if text:
                    parts.append(text)
                return
            if not isinstance(node, Tag):
                return
            if node.name == "img":
                parts.append("[IMG]")
                return
            if node.name == "video":
                parts.append("[IMG]")  # 비디오도 미디어 마커
                return
            if node.name in ("br",):
                parts.append("\n")
                return
            # 블록 요소는 줄바꿈 추가
            is_block = node.name in (
                "div", "p", "h1", "h2", "h3", "h4", "h5", "h6",
                "li", "blockquote", "pre", "table", "tr", "td", "th",
                "section", "article", "header", "footer", "figcaption",
            )
            if is_block and parts and parts[-1] != "\n":
                parts.append("\n")
            for child in node.children:
                _walk(child)
            if is_block and parts and parts[-1] != "\n":
                parts.append("\n")

        _walk(elem)

        # 조합 + 정리
        raw = "".join(parts)
        # 연속 빈줄 정리, 앞뒤 공백
        import re
        result = re.sub(r'\n{3,}', '\n\n', raw).strip()

        # 너무 짧으면 (5자 미만, [IMG] 마커 제외) 의미 없음
        text_only = result.replace("[IMG]", "").strip()
        if len(text_only) < 5 and "[IMG]" not in result:
            return None

        # 최대 3000자 (구조 마커 포함이므로 여유 확보)
        return result[:3000] if result else None

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
