import redis.asyncio as redis
from functools import lru_cache
import os
from dotenv import load_dotenv

load_dotenv()

@lru_cache()
def get_redis_client():
    # Use the REDIS_URL from the environment, with a default for local development
    redis_url = os.getenv("REDIS_URL")
    return redis.from_url(redis_url, decode_responses=True)

async def get_redis():
    return get_redis_client()

