import logging
import traceback

from fastapi import FastAPI

from config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

app = FastAPI(title="Axis Policy Sync", version="0.1.0")

# Import routers with error handling so one failure doesn't kill the whole app
try:
    from api.routes import router as jobs_router
    app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
except Exception as e:
    log.error("Failed to load jobs router: %s\n%s", e, traceback.format_exc())

try:
    from api.webhooks import router as webhooks_router
    app.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
except Exception as e:
    log.error("Failed to load webhooks router: %s\n%s", e, traceback.format_exc())

try:
    from api.test_sync import router as test_router
    app.include_router(test_router, prefix="/test", tags=["test"])
    print("TEST ROUTER LOADED OK")
except Exception as e:
    print(f"TEST ROUTER FAILED: {e}")
    traceback.print_exc()


@app.get("/health")
async def health():
    return {"status": "ok"}
