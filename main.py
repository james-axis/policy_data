import logging

from fastapi import FastAPI

from config import settings
from api.routes import router as jobs_router
from api.webhooks import router as webhooks_router

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

app = FastAPI(title="Axis Policy Sync", version="0.1.0")
app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
app.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])


@app.get("/health")
async def health():
    return {"status": "ok"}
