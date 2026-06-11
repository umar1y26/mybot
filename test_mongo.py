
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test():
    client = AsyncIOMotorClient("mongodb://localhost:27017", serverSelectionTimeoutMS=5000)
    try:
        info = await client.server_info()
        print("MongoDB работает, версия:", info["version"])
    except Exception as e:
        print("MongoDB НЕ работает:", e)

asyncio.run(test())