import asyncio
from datetime import datetime, timezone
from pathlib import Path

import av
from aiortc import MediaStreamTrack


SCREENSHOTS_DIRECTORY = (
    Path("backend")
    / "screenshots"
    / "saved"
)

SCREENSHOTS_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True,
)


class ScreenshotService:
    """
    Captures individual video frames from the
    active DroneStream media source and saves
    them as PNG image files.
    """

    async def capture(
        self,
        source_track: MediaStreamTrack,
        stream_id: int,
        admin_id: int | None = None,
    ):
        """
        Capture one frame from the supplied
        media track and save it as a PNG file.
        """

        frame = await source_track.recv()

        timestamp = datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        file_name = (
            f"stream_{stream_id}_"
            f"{timestamp}.png"
        )

        output_path = (
            SCREENSHOTS_DIRECTORY
            / file_name
        )

        container = None

        try:

            container = av.open(
                str(output_path),
                mode="w",
            )

            image_stream = (
                container.add_stream(
                    "png"
                )
            )

            image_stream.width = frame.width
            image_stream.height = frame.height
            image_stream.pix_fmt = "rgb24"

            rgb_frame = frame.reformat(
                format="rgb24"
            )

            for packet in image_stream.encode(
                rgb_frame
            ):
                container.mux(packet)

            for packet in image_stream.encode(
                None
            ):
                container.mux(packet)

        finally:

            if container is not None:
                container.close()

        file_size = (
            output_path.stat().st_size
            if output_path.exists()
            else 0
        )

        return {
            "stream_id": stream_id,
            "file_name": file_name,
            "file_path": str(
                output_path
            ),
            "file_size_bytes": file_size,
            "captured_at": datetime.now(
                timezone.utc
            ),
            "admin_id": admin_id,
            "width": frame.width,
            "height": frame.height,
        }


screenshot_service = ScreenshotService()