"""기존 이미지 중 storage_key 없는 것들을 Supabase Storage에 캐싱"""
import logging
from datetime import datetime

from app.core.config import get_settings
from app.core.database import SyncSessionLocal
from app.models.trend import TrendImage
from app.services.image_service import ImageService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

REFERER_MAP = {
    "dcinside.com": "https://gall.dcinside.com/",
    "dcimg": "https://gall.dcinside.com/",
}


def get_referer(url: str) -> str | None:
    for key, referer in REFERER_MAP.items():
        if key in url:
            return referer
    return None


def main():
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
        return

    image_service = ImageService()
    db = SyncSessionLocal()

    try:
        images = db.query(TrendImage).filter(
            TrendImage.storage_key.is_(None),
            TrendImage.url.isnot(None),
        ).all()

        logger.info(f"Found {len(images)} images without cache")

        success = 0
        fail = 0

        for img in images:
            referer = get_referer(img.url)
            raw = image_service.download_image(img.url, referer=referer)
            if not raw:
                fail += 1
                logger.warning(f"FAIL download: {img.url[:80]}")
                continue

            webp = image_service.convert_to_webp(raw)
            if not webp:
                fail += 1
                continue

            date = img.created_at or datetime.utcnow()
            phash_prefix = (img.phash or "unknown")[:8]
            storage_key = f"{date.strftime('%Y/%m/%d')}/{img.trend_id}_{img.id}_{phash_prefix}.webp"

            ok = image_service.upload_to_storage(
                webp, storage_key,
                settings.supabase_url, settings.supabase_service_role_key,
            )

            if ok:
                img.storage_key = storage_key
                db.commit()
                success += 1
            else:
                fail += 1
                logger.warning(f"FAIL upload: {storage_key}")

        logger.info(f"Done: {success} cached, {fail} failed (of {len(images)} total)")

    finally:
        db.close()


if __name__ == "__main__":
    main()
