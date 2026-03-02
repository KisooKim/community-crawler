from io import BytesIO

import httpx
import imagehash
from PIL import Image


class ImageService:
    """이미지 처리 서비스 (pHash 계산만, 저장 안 함)"""

    HASH_THRESHOLD = 10  # 해밍 거리 임계값

    def download_image(self, url: str, referer: str | None = None) -> bytes | None:
        """이미지 다운로드 (pHash 계산용, 메모리에서만 사용)"""
        try:
            headers = {}
            if referer:
                headers["Referer"] = referer
            with httpx.Client(timeout=15.0, headers=headers) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.content
        except Exception:
            return None

    def compute_phash(self, image_data: bytes) -> str | None:
        """pHash 계산"""
        try:
            img = Image.open(BytesIO(image_data))
            phash = imagehash.phash(img)
            return str(phash)
        except Exception:
            return None

    def get_image_dimensions(self, image_data: bytes) -> tuple[int, int] | None:
        """이미지 크기 반환"""
        try:
            img = Image.open(BytesIO(image_data))
            return img.size
        except Exception:
            return None

    def hamming_distance(self, hash1: str, hash2: str) -> int:
        """두 pHash 간의 해밍 거리 계산"""
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        return h1 - h2

    def is_similar(self, hash1: str, hash2: str) -> bool:
        """두 이미지가 유사한지 판단"""
        distance = self.hamming_distance(hash1, hash2)
        return distance <= self.HASH_THRESHOLD

    def is_animated_gif(self, image_data: bytes) -> bool:
        """애니메이션 GIF인지 확인"""
        try:
            img = Image.open(BytesIO(image_data))
            if img.format != "GIF":
                return False
            try:
                img.seek(1)
                return True  # 2번째 프레임이 있으면 애니메이션
            except EOFError:
                return False  # 1프레임뿐 → 정적 GIF
        except Exception:
            return False

    def convert_to_webp(self, image_data: bytes, max_width: int = 800, quality: int = 75) -> bytes | None:
        """이미지를 WebP로 변환 (리사이즈 포함)"""
        try:
            img = Image.open(BytesIO(image_data))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="WEBP", quality=quality)
            return buf.getvalue()
        except Exception:
            return None

    def upload_to_storage(self, data: bytes, storage_key: str,
                          supabase_url: str, service_role_key: str,
                          content_type: str = "image/webp") -> bool:
        """Supabase Storage에 이미지 업로드"""
        try:
            url = f"{supabase_url}/storage/v1/object/trend-images/{storage_key}"
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, content=data, headers={
                    "Authorization": f"Bearer {service_role_key}",
                    "Content-Type": content_type,
                    "x-upsert": "true",
                })
                resp.raise_for_status()
                return True
        except Exception:
            return False

    MAX_VIDEO_SIZE = 10 * 1024 * 1024  # 10MB

    def process_video(self, url: str, referer: str | None = None) -> dict | None:
        """비디오 처리: 다운로드만 (pHash/변환 없음, 10MB 초과 시 스킵)"""
        video_data = self.download_image(url, referer=referer)
        if not video_data:
            return None
        if len(video_data) > self.MAX_VIDEO_SIZE:
            return None
        return {
            "url": url,
            "media_type": "video",
            "phash": None,
            "width": None,
            "height": None,
            "raw_data": video_data,
        }

    def process_image(self, url: str, referer: str | None = None) -> dict | None:
        """이미지 처리: 다운로드 → pHash 계산 → WebP 변환 (GIF는 원본 유지) → 반환"""
        image_data = self.download_image(url, referer=referer)
        if not image_data:
            return None

        phash = self.compute_phash(image_data)
        if not phash:
            return None

        dimensions = self.get_image_dimensions(image_data)
        width, height = dimensions if dimensions else (None, None)

        animated_gif = self.is_animated_gif(image_data)
        if animated_gif:
            webp_data = None
        else:
            webp_data = self.convert_to_webp(image_data)

        return {
            "url": url,
            "phash": phash,
            "width": width,
            "height": height,
            "webp_data": webp_data,
            "is_gif": animated_gif,
            "raw_data": image_data if animated_gif else None,
        }
