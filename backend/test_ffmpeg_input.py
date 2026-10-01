import asyncio
import os

from backend.app.streaming.input_source import (
    FFmpegVideoSource,
)


VIDEO_FILE = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "streaming",
        "recordings",
        "test-drone.mp4",
    )
)


async def main():

    print("=" * 70)
    print("DroneStream: FFMPEG INPUT TEST")
    print("=" * 70)

    print(f"Video file: {VIDEO_FILE}")

    source = FFmpegVideoSource(
        input_source=VIDEO_FILE,
        width=1280,
        height=720,
        fps=30,
    )

    print()
    print("Reading test frames...")

    try:

        for number in range(10):

            frame = await source.video.recv()

            print(
                f"Frame {number + 1}: "
                f"{frame.width}x{frame.height} "
                f"format={frame.format.name} "
                f"pts={frame.pts}"
            )

    finally:

        source.stop()

    print()
    print("=" * 70)
    print("DroneStream: FFMPEG INPUT TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())