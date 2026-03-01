import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.trend import Site, TrendArticle
from app.services.trend_service import TrendService
from app.services.image_service import ImageService
from crawlers.clien import ClienCrawler
from crawlers.theqoo import TheqooCrawler
from crawlers.ppomppu import PpomppuCrawler
from crawlers.instiz import InstizCrawler
from crawlers.todayhumor import TodayhumorCrawler
from crawlers.natepann import NatepannCrawler
from crawlers.bobaedream import BobaedreamCrawler
from crawlers.dcinside import DcinsideCrawler
from crawlers.mlbpark import MlbparkCrawler
from crawlers.inven import InvenCrawler
from crawlers.slrclub import SlrclubCrawler
from crawlers.cook82 import Cook82Crawler
from crawlers.orbi import OrbiCrawler
from crawlers.coinpan import CoinpanCrawler

logger = logging.getLogger(__name__)


class CrawlerService:
    """크롤링 서비스"""

    CRAWLERS = {
        "clien": ClienCrawler,
        "theqoo": TheqooCrawler,
        "ppomppu": PpomppuCrawler,
        "instiz": InstizCrawler,
        "todayhumor": TodayhumorCrawler,
        "natepann": NatepannCrawler,
        "bobaedream": BobaedreamCrawler,
        "dcinside": DcinsideCrawler,
        "mlbpark": MlbparkCrawler,
        "inven": InvenCrawler,
        "slrclub": SlrclubCrawler,
        "cook82": Cook82Crawler,
        "orbi": OrbiCrawler,
        "coinpan": CoinpanCrawler,
    }

    def __init__(self, db: Session = None):
        self.db = db
        self.trend_service = TrendService(db)
        self.image_service = ImageService()
        from app.core.config import get_settings
        settings = get_settings()
        self.supabase_url = settings.supabase_url
        self.supabase_service_role_key = settings.supabase_service_role_key

    def get_or_create_site(self, crawler) -> Site:
        """사이트 정보 조회 또는 생성"""
        site = self.db.execute(
            select(Site).where(Site.name == crawler.site_name)
        ).scalars().first()

        if not site:
            site = Site(
                name=crawler.site_name,
                display_name=crawler.display_name,
                base_url=crawler.base_url,
            )
            self.db.add(site)
            self.db.flush()

        return site

    def crawl_site(self, site_name: str) -> dict:
        """특정 사이트 크롤링"""
        if site_name not in self.CRAWLERS:
            return {"error": f"Unknown site: {site_name}"}

        crawler_class = self.CRAWLERS[site_name]

        with crawler_class() as crawler:
            site = self.get_or_create_site(crawler)
            self.db.commit()
            referer = crawler.base_url
            articles = crawler.get_popular_articles()

            # 0단계: 이미 DB에 있는 글 URL 필터링 (이미지 다운로드 절약)
            existing_urls = set(
                row[0] for row in self.db.execute(
                    select(TrendArticle.url).where(
                        TrendArticle.url.in_([a.url for a in articles])
                    )
                ).all()
            )
            new_articles = [a for a in articles if a.url not in existing_urls]
            logger.info(f"[{site_name}] {len(articles)} found, {len(new_articles)} new, {len(existing_urls)} skipped (already in DB)")

            # 1단계: 새 글만 이미지 다운로드 + pHash 병렬 처리
            image_results = self._prefetch_images(new_articles, referer)

            # 2단계: DB 저장
            processed = 0
            skipped = 0
            for article_data in new_articles:
                try:
                    image_result = image_results.get(article_data.url)
                    result = self._save_article(article_data, site, image_result)
                    if result:
                        self.db.commit()
                        processed += 1
                    else:
                        skipped += 1
                except Exception as e:
                    self.db.rollback()
                    logger.warning(f"Error processing article '{article_data.title[:30]}': {e}")
                    continue

            logger.info(f"[{site_name}] {len(articles)} found, {processed} saved, {skipped} skipped")

        return {
            "site": site_name,
            "articles_found": len(articles),
            "processed": processed,
            "skipped": skipped,
        }

    @staticmethod
    def crawl_all_parallel(max_workers: int = 5) -> list[dict]:
        """모든 사이트 병렬 크롤링 (각 스레드가 독립 DB 세션 사용)"""
        from app.core.database import SyncSessionLocal

        def _crawl_one(site_name: str) -> dict:
            with SyncSessionLocal() as db:
                service = CrawlerService(db)
                return service.crawl_site(site_name)

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_crawl_one, name): name
                for name in CrawlerService.CRAWLERS
            }
            for future in as_completed(futures):
                site_name = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    logger.warning(f"[{site_name}] crawl failed: {e}")
                    result = {"site": site_name, "error": str(e)}
                results.append(result)

        return results

    def crawl_all(self) -> list[dict]:
        """모든 활성 사이트 크롤링 (순차, 단일 세션)"""
        results = []
        for site_name in self.CRAWLERS:
            try:
                result = self.crawl_site(site_name)
            except Exception as e:
                logger.warning(f"[{site_name}] crawl failed: {e}")
                result = {"site": site_name, "error": str(e)}
            results.append(result)
        return results

    def _prefetch_images(self, articles, referer: str | None = None) -> dict:
        """모든 글의 이미지를 병렬 다운로드 + pHash 계산 + WebP 변환.
        Returns: {article_url: [image_result_dict, ...]} 매핑
        """
        # (article_url, index, image_url) 튜플 리스트
        tasks = []
        for article in articles:
            for i, img_url in enumerate(article.image_urls[:10]):
                tasks.append((article.url, i, img_url))

        if not tasks:
            return {}

        results = {}  # {article_url: [result, ...]}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self.image_service.process_image, img_url, referer): (art_url, i)
                for art_url, i, img_url in tasks
            }
            for future in as_completed(futures):
                art_url, idx = futures[future]
                try:
                    result = future.result()
                    if result:
                        if art_url not in results:
                            results[art_url] = []
                        results[art_url].append((idx, result))
                except Exception:
                    pass

        # 인덱스 순으로 정렬
        for art_url in results:
            results[art_url] = [r for _, r in sorted(results[art_url])]

        return results

    def _save_article(self, article_data, site: Site, image_results: list | None) -> bool:
        """글 DB 저장 (이미지 결과가 이미 있는 상태)."""
        if not image_results:
            return False

        # 첫 번째 이미지의 pHash로 트렌드 매칭
        first = image_results[0]
        if not first.get("phash"):
            return False

        trend = self.trend_service.find_or_create_trend(
            first["phash"],
            article_data.title,
        )

        self.trend_service.add_article_to_trend(
            trend,
            {
                "title": article_data.title,
                "url": article_data.url,
                "view_count": article_data.view_count,
                "like_count": article_data.like_count,
                "comment_count": article_data.comment_count,
                "published_at": article_data.published_at,
            },
            site.id,
        )

        # 모든 이미지 캐싱 + DB 저장
        from datetime import datetime
        now = datetime.utcnow()

        for i, img_result in enumerate(image_results):
            storage_key = None
            webp_data = img_result.get("webp_data")
            if webp_data and self.supabase_url and self.supabase_service_role_key:
                hash_prefix = (img_result.get("phash") or "nohash")[:8]
                storage_key = f"{now.year}/{now.month:02d}/{now.day:02d}/{trend.id}_{i}_{hash_prefix}.webp"
                if not self.image_service.upload_to_storage(
                    webp_data, storage_key, self.supabase_url, self.supabase_service_role_key
                ):
                    storage_key = None

            self.trend_service.add_image_to_trend(trend, {
                "url": img_result["url"],
                "phash": img_result.get("phash"),
                "width": img_result.get("width"),
                "height": img_result.get("height"),
                "storage_key": storage_key,
            })

        self.db.flush()
        self.db.refresh(trend)
        self.trend_service.update_trend_stats(trend)
        return True
