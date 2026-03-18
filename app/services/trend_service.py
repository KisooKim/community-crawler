import math
import re
from datetime import datetime, timedelta
from sqlalchemy import select, update, func, text
from sqlalchemy.orm import Session

from app.models.trend import Trend, TrendImage, TrendArticle
from app.services.image_service import ImageService


class TrendService:
    """트렌드 관리 서비스"""

    HALF_LIFE_HOURS = 4  # 점수 반감기 (시간)

    def __init__(self, db: Session = None):
        self.db = db
        self.image_service = ImageService()
        self._site_stats_cache = None

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

        # DB에서 해밍 거리 직접 계산 → 매칭되는 이미지만 반환 (egress 절감)
        rows = self.db.execute(
            text("""
                SELECT ti.id, ti.trend_id, ti.phash, t.title AS trend_title
                FROM trend_images ti
                JOIN trends t ON t.id = ti.trend_id
                WHERE ti.phash IS NOT NULL
                  AND ti.created_at > :cutoff
                  AND bit_count(('x' || ti.phash)::bit(64) # ('x' || :input_phash)::bit(64)) <= :threshold
            """),
            {"cutoff": cutoff, "input_phash": image_phash,
             "threshold": ImageService.HASH_THRESHOLD},
        ).all()

        for row in rows:
            if self._title_similar(title, row.trend_title):
                trend = self.db.get(Trend, row.trend_id)
                if trend:
                    return trend

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
    ) -> TrendArticle | None:
        """트렌드에 원본 글 추가 (같은 URL 또는 같은 사이트면 스킵)"""
        existing = self.db.execute(
            select(TrendArticle).where(
                TrendArticle.trend_id == trend.id,
                TrendArticle.url == article_data["url"],
            )
        ).scalar_one_or_none()

        if existing:
            return existing

        # 같은 사이트에서 이미 글이 있으면 스킵 (리포스트 중복 방지)
        same_site = self.db.execute(
            select(TrendArticle).where(
                TrendArticle.trend_id == trend.id,
                TrendArticle.site_id == site_id,
            )
        ).scalar_one_or_none()

        if same_site:
            return None

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

        # pHash 유사도 체크 (같은 이미지, 다른 URL/압축) — DB에서 해밍 거리 계산
        phash = image_data.get("phash")
        if phash:
            match = self.db.execute(
                text("""
                    SELECT id FROM trend_images
                    WHERE trend_id = :trend_id
                      AND phash IS NOT NULL
                      AND bit_count(('x' || phash)::bit(64) # ('x' || :input_phash)::bit(64)) <= :threshold
                    LIMIT 1
                """),
                {"trend_id": trend.id, "input_phash": phash,
                 "threshold": ImageService.HASH_THRESHOLD},
            ).first()
            if match:
                existing_img = self.db.get(TrendImage, match.id)
                if existing_img:
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
            media_type=image_data.get("media_type", "image"),
            order=len(trend.images),
        )
        self.db.add(image)
        return image

    def _get_site_stats(self) -> dict:
        """각 사이트의 최근 engagement 평균 (정규화용, 세션 내 캐싱)"""
        if self._site_stats_cache is not None:
            return self._site_stats_cache

        cutoff = datetime.utcnow() - timedelta(hours=72)
        rows = self.db.execute(
            select(
                TrendArticle.site_id,
                func.avg(TrendArticle.view_count),
                func.avg(TrendArticle.like_count),
                func.avg(TrendArticle.comment_count),
            )
            .where(TrendArticle.created_at > cutoff)
            .group_by(TrendArticle.site_id)
        ).all()

        stats = {}
        for site_id, avg_views, avg_likes, avg_comments in rows:
            stats[site_id] = {
                "avg_views": max(float(avg_views or 0), 1),
                "avg_likes": max(float(avg_likes or 0), 1),
                "avg_comments": max(float(avg_comments or 0), 1),
            }
        self._site_stats_cache = stats
        return stats

    def calculate_score(self, trend: Trend) -> float:
        """트렌드 점수 계산 (사이트별 정규화 + 다양성 + 시간 감쇠)"""
        articles = trend.articles
        site_stats = self._get_site_stats()

        # 사이트별 정규화: 각 글의 engagement를 해당 사이트 평균으로 나눔
        # → "사이트 내에서 얼마나 핫한가" (1.0 = 평균, 2.0 = 평균의 2배)
        norm_views = 0.0
        norm_likes = 0.0
        norm_comments = 0.0
        for a in articles:
            s = site_stats.get(a.site_id)
            if s:
                norm_views += a.view_count / s["avg_views"]
                norm_likes += a.like_count / s["avg_likes"]
                norm_comments += a.comment_count / s["avg_comments"]
            else:
                # 새 사이트 (통계 없음) → 기본값 사용
                norm_views += math.log1p(a.view_count / 100)
                norm_likes += math.log1p(a.like_count)
                norm_comments += math.log1p(a.comment_count)

        engagement = (
            1
            + math.log1p(norm_views) * 1.0
            + math.log1p(norm_likes) * 2.0
            + math.log1p(norm_comments) * 1.5
        )

        # 사이트 다양성 보너스
        diversity = 1 + math.log(max(trend.site_count, 1))

        base_score = engagement * diversity

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
