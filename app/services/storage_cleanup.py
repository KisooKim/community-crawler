import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from app.models.trend import TrendImage

logger = logging.getLogger(__name__)


def cleanup_old_images(
    database_url: str,
    supabase_url: str,
    service_role_key: str,
    max_age_days: int = 7,
) -> int:
    """7일 이전 캐시 이미지를 Supabase Storage에서 삭제하고 storage_key를 NULL로."""
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)

    with Session() as db:
        old_images = db.execute(
            select(TrendImage).where(
                TrendImage.storage_key.isnot(None),
                TrendImage.created_at < cutoff,
            )
        ).scalars().all()

        if not old_images:
            return 0

        storage_keys = [img.storage_key for img in old_images]

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.delete(
                    f"{supabase_url}/storage/v1/object/trend-images",
                    headers={
                        "Authorization": f"Bearer {service_role_key}",
                        "Content-Type": "application/json",
                    },
                    json={"prefixes": storage_keys},
                )
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Storage 삭제 실패: {e}")

        image_ids = [img.id for img in old_images]
        db.execute(
            update(TrendImage)
            .where(TrendImage.id.in_(image_ids))
            .values(storage_key=None)
        )
        db.commit()

        return len(image_ids)
