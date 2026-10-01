import asyncio

from sqlalchemy import text

from backend.app.database import AsyncSessionLocal


async def check_database():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
        )

        tables = result.scalars().all()

        print("\nDroneStream database tables:")
        for table in tables:
            print(f"  - {table}")

        print(f"\nTotal tables: {len(tables)}")


if __name__ == "__main__":
    asyncio.run(check_database())