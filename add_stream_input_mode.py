from dotenv import load_dotenv
load_dotenv()

import asyncio
from sqlalchemy import text
from backend.app.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as s:
        await s.execute(text(
            "ALTER TABLE platform_settings "
            "ADD COLUMN IF NOT EXISTS stream_input_mode "
            "VARCHAR(40) NOT NULL DEFAULT 'test_video'"
        ))
        await s.commit()
        print("OK")

asyncio.run(main())
