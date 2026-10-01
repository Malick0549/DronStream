import asyncio

from backend.app.database import Base, engine

from backend.app.models import (
    Admin,
    Stream,
    StreamLink,
    ViewerSession,
    ViewerEvent,
)


async def init_database():
    print("Creating DroneStream database tables...")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    print("Database tables created successfully.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())