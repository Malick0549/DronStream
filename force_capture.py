from dotenv import load_dotenv
load_dotenv()
import asyncio
from sqlalchemy import text
from backend.app.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "UPDATE platform_settings SET "
            "stream_input_mode = 'capture_card', "
            "use_capture_card = true "
            "WHERE id = 1"
        ))
        await s.commit()
        r = await s.execute(text(
            "SELECT use_capture_card, stream_input_mode "
            "FROM platform_settings WHERE id = 1"
        ))
        print("ROW:", r.fetchone())

asyncio.run(main())
