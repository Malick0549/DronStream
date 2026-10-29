from dotenv import load_dotenv
load_dotenv()
import asyncio
from sqlalchemy import text
from backend.app.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as s:
        cols = await s.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'platform_settings' "
            "ORDER BY ordinal_position"
        ))
        print("COLUMNS:")
        for row in cols.fetchall():
            print(" ", row[0])

        try:
            r = await s.execute(text(
                "SELECT id, use_capture_card, capture_device_name, "
                "stream_input_mode, stream_quality "
                "FROM platform_settings ORDER BY id LIMIT 1"
            ))
            row = r.fetchone()
            print("ROW:", row)
        except Exception as e:
            print("ROW ERROR:", e)

asyncio.run(main())
