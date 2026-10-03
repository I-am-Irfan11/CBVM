from datetime import datetime, timezone
import re
from uuid import uuid4


class ScanStorage:
    """Private Cloudflare R2 storage for original ANPR snapshots."""

    def __init__(self, settings):
        self.settings = settings
        configured = all((settings.r2_endpoint_url, settings.r2_bucket,
                         settings.r2_access_key_id, settings.r2_secret_access_key))
        self.client = None
        if configured:
            import boto3

            self.client = boto3.client(
                "s3", endpoint_url=settings.r2_endpoint_url, region_name="auto",
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
            )

    @property
    def enabled(self):
        return self.client is not None

    def put(self, image: bytes, content_type: str, camera_id: str):
        if not self.enabled:
            return None
        extension = "png" if content_type == "image/png" else "jpg"
        safe_camera = re.sub(r"[^a-zA-Z0-9_-]", "-", camera_id)[:80]
        now = datetime.now(timezone.utc)
        key = f"scans/{now:%Y/%m/%d}/{safe_camera}/{uuid4()}.{extension}"
        self.client.put_object(
            Bucket=self.settings.r2_bucket,
            Key=key,
            Body=image,
            ContentType=content_type,
            CacheControl="private, no-store",
        )
        return key

    def put_frame(self, frame, camera_id: str):
        import cv2

        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            raise RuntimeError("Could not encode the camera frame")
        return self.put(encoded.tobytes(), "image/jpeg", camera_id)

    def signed_read_url(self, key: str):
        if not self.enabled:
            return None
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.settings.r2_bucket, "Key": key},
            ExpiresIn=self.settings.r2_presigned_url_expiry_seconds,
        )
