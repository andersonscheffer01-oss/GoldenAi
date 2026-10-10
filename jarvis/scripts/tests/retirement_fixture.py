"""TEST FIXTURE ONLY: no legacy imports, providers, production DBs or devices."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys

from fastapi import FastAPI
import uvicorn


@asynccontextmanager
async def lifespan(app):
    Path(sys.argv[2]).write_text("started", encoding="ascii")

    async def deadline():
        await asyncio.sleep(45)
        server.should_exit = True

    timer = asyncio.create_task(deadline())
    try:
        yield
    finally:
        timer.cancel()
        await asyncio.gather(timer, return_exceptions=True)
        Path(sys.argv[2]).write_text("lifespan_closed", encoding="ascii")


app = FastAPI(lifespan=lifespan)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=int(sys.argv[1])))
server.run()
