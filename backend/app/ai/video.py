from abc import ABC, abstractmethod


class VideoSource(ABC):
    @abstractmethod
    def read(self): ...

    @abstractmethod
    def close(self): ...


class MockVideoSource(VideoSource):
    def read(self):
        import numpy as np

        return np.zeros((360, 640, 3), dtype=np.uint8)

    def close(self):
        pass


class OpenCVVideoSource(VideoSource):
    def __init__(self, source):
        import cv2

        if source == "":
            raise ValueError("Configure the RTSP URL or MP4 path before starting capture")
        if isinstance(source, str) and source.lower().startswith("rtsp"):
            self.capture = cv2.VideoCapture(
                source,
                cv2.CAP_FFMPEG,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000],
            )
        else:
            self.capture = cv2.VideoCapture(source)
        if not self.capture.isOpened():
            self.capture.release()
            raise RuntimeError("Unable to open configured video source")

    def read(self):
        ok, frame = self.capture.read()
        if not ok:
            raise EOFError("Video ended or camera disconnected")
        return frame

    def close(self):
        self.capture.release()


def video_source(settings):
    if settings.video_source == "mock":
        return MockVideoSource()
    return OpenCVVideoSource(
        {"rtsp": settings.rtsp_url, "mp4": settings.video_file, "webcam": settings.webcam_index}[
            settings.video_source
        ]
    )
