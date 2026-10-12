from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .core.database import Base, SessionLocal, engine
from .core.errors import AppError
from .routers import api_router, webhooks_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.is_prod:
        Base.metadata.create_all(bind=engine)
        if settings.SEED_DEMO_DATA:
            from app.core.seed import seed_demo

            with SessionLocal() as db:
                seed_demo(db)
    yield


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description=(
        "REST API powering the Zaply VTU platform — airtime, data, electricity and cable "
        "payments behind a secure wallet. JWT bearer auth: click **Authorize** and paste "
        "`access_token` from `/auth/login`."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_prod else [],
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "message": exc.message, "code": exc.code})


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "message": str(exc.detail), "code": f"http_{exc.status_code}"})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "input"
    msg = first.get("msg", "Invalid input")
    # Pydantic v2 puts raw exception objects in `ctx`; they are not JSON serializable.
    errors = exc.errors()
    for err in errors:
        err.pop("url", None)
        if "ctx" in err:
            err["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
    return JSONResponse(status_code=422, content={"success": False, "message": f"{field}: {msg}", "code": "validation_error", "errors": errors})


app.include_router(api_router, prefix=settings.API_PREFIX)
app.include_router(webhooks_router, prefix=settings.API_PREFIX)


# ── Frontend (mobile-first SPA + responsive web) ─────────────────────────
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
