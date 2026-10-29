from dotenv import load_dotenv
load_dotenv()

import asyncio
from sqlalchemy import select
from backend.app.database import AsyncSessionLocal
from backend.app.models.settings import PlatformSettings

async def main():
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(PlatformSettings).order_by(PlatformSettings.id.asc()).limit(1)
        )
        row = r.scalar_one_or_none()
        if not row:
            print("NO SETTINGS ROW")
            return

        print("BEFORE:", row.stream_input_mode, row.use_capture_card)

        row.stream_input_mode = "capture_card"
        row.use_capture_card = True
        await s.commit()
        await s.refresh(row)

        print("AFTER:", row.stream_input_mode, row.use_capture_card)
        print("HAS ATTR:", hasattr(row, "stream_input_mode"))

asyncio.run(main())
