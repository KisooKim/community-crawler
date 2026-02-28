import math
import re
from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.trend import Trend, TrendImage, TrendArticle
from app.services.image_service import ImageService


class TrendService:
    """트렌드 관리 서비스"""

    HALF_LIFE_HOURS = 4  # 점수 반감기 (시간)

    def __init__(self, db: Session = None):
        self.db = db
        self.image_service = ImageService()

    MATCH_WINDOW_HOURS = 72  # 최근 3일 이미지만 비교

    MIN_OVERLAP_WORDS = 2  # 제목 매칭 최소 겹침 단어 수

    @staticmethod
    def _title_similar(title1: str, title2: str) -> bool:
        """두 제목의 유사도 확인 (2글자 이상 단어 겹침 기반, 최소 2개 겹침)"""
        words1 = set(w for w in re.split(r'\W+', title1) if len(w) >= 2)
        words2 = set(w for w in re.split(r'\W+', title2) if len(w) >= 2)
        if not words1 or not words2:
            return True  # 단어 추출 실패 시 이미지 매칭만 사용
        overlap = len(words1 & words2)
        return overlap >= TrendService.MIN_OVERLAP_WORDS

    def find_or_create_trend(self, image_phash: str, title: str) -> Trend:
        """유사한 트렌드 찾기 또는 새로 생성"""
        cutoff = datetime.utcnow() - timedelta(hours=self.MATCH_WINDOW_HOURS)
        existing_images = self.db.execute(
            select(TrendImage).where(
                TrendImage.phash.isnot(None),
                TrendImage.created_at > cutoff,
            )
        ).scalars().all()

        for img in existing_images:
            if self.image_service.is_similar(image_phash, img.phash):
                if self._title_similar(title, img.trend.title):
                    return img.trend

        # 새 트렌드 생성
        trend = Trend(title=title, score=1.0, site_count=1)
        self.db.add(trend)
        self.db.flush()
        return trend

    def add_article_to_trend(
        self,
        trend: Trend,
        article_data: dict,
        site_id: int,
    ) -> TrendArticle:
        """트렌드에 원본 글 추가 (같은 URL이면 스킵)"""
        existing = self.db.execute(
            select(TrendArticle).where(
                TrendArticle.trend_id == trend.id,
                TrendArticle.url == article_data["url"],
            )
        ).scalar_one_or_none()

        if existing:
            return existing

        article = TrendArticle(
            trend_id=trend.id,
            site_id=site_id,
            title=article_data["title"],
            url=article_data["url"],
            view_count=article_data.get("view_count", 0),
            like_count=article_data.get("like_count", 0),
            comment_count=article_data.get("comment_count", 0),
            published_at=article_data.get("published_at"),
        )
        self.db.add(article)
        return article

    def add_image_to_trend(
        self,
        trend: Trend,
        image_data: dict,
    ) -> TrendImage:
        """트렌드에 이미지 추가 (URL 또는 pHash 중복 시 스킵)"""
        # URL 중복 체크
        existing = self.db.execute(
            select(TrendImage).where(
                TrendImage.trend_id == trend.id,
                TrendImage.url == image_data["url"],
            )
        ).scalar_one_or_none()

        if existing:
            if not existing.storage_key and image_data.get("storage_key"):
                existing.storage_key = image_data["storage_key"]
            return existing

        # pHash 유사도 체크 (같은 이미지, 다른 URL/압축)
        phash = image_data.get("phash")
        if phash:
            existing_images = self.db.execute(
                select(TrendImage).where(
                    TrendImage.trend_id == trend.id,
                    TrendImage.phash.isnot(None),
                )
            ).scalars().all()
            for existing_img in existing_images:
                if self.image_service.is_similar(phash, existing_img.phash):
                    if not existing_img.storage_key and image_data.get("storage_key"):
                        existing_img.storage_key = image_data["storage_key"]
                    return existing_img

        image = TrendImage(
            trend_id=trend.id,
            url=image_data["url"],
            storage_key=image_data.get("storage_key"),
            phash=image_data.get("phash"),
            width=image_data.get("width"),
            height=image_data.get("height"),
            order=len(trend.images),
        )
        self.db.add(image)
        return image

    def calculate_score(self, trend: Trend) -> float:
        """트렌드 점수 계산"""
        # 기본 점수: 글 수 × 사이트 다양성 보너스
        article_count = len(trend.articles)
        site_count = trend.site_count

        base_score = article_count * (1 + math.log(max(site_count, 1)))

        # 시간 감쇠
        hours_old = (datetime.utcnow() - trend.created_at).total_seconds() / 3600
        decay = 0.5 ** (hours_old / self.HALF_LIFE_HOURS)

        return base_score * decay

    def update_trend_stats(self, trend: Trend):
        """트렌드 통계 업데이트"""
        # 고유 사이트 수 계산
        site_ids = set(a.site_id for a in trend.articles)
        trend.site_count = len(site_ids)

        # 점수 재계산
        trend.score = self.calculate_score(trend)
        trend.updated_at = datetime.utcnow()

    def update_scores(self) -> int:
        """모든 트렌드 점수 업데이트 (시간 감쇠 적용)"""
        # 최근 48시간 내 트렌드만 업데이트
        cutoff = datetime.utcnow() - timedelta(hours=48)

        trends = self.db.execute(
            select(Trend).where(Trend.created_at > cutoff)
        ).scalars().all()

        for trend in trends:
            trend.score = self.calculate_score(trend)

        self.db.commit()
        return len(trends)
