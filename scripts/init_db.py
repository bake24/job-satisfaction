import asyncio

from app.db.schema import bootstrap_schema
from app.db.session import engine


async def main() -> None:
    async with engine.begin() as conn:
        await bootstrap_schema(conn)


if __name__ == "__main__":
    asyncio.run(main())
