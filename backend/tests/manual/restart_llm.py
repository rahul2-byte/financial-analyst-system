import asyncio
import logging
from app.core.llama_manager import llama_manager


async def test_restart():
    logging.basicConfig(level=logging.INFO)
    print("Ensuring server is running...")
    try:
        await llama_manager.ensure_server_running()
        print("Server is running and healthy!")
    except Exception as e:
        print(f"Restart failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_restart())
