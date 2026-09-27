from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .analyze import analyze
from .config import CORS_ALLOW_ORIGINS
from .models.analysis import AnalyzeRequest, AnalyzeResponse
from .routes.employees import router as employees_router
from .routes.plane import integration_router as plane_integration_router
from .routes.plane import router as plane_router
from .routes.projects import router as projects_router
from .routes.slack import router as slack_router

app = FastAPI(title="PulseGuard AI Twins Engine")

if CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

app.include_router(employees_router)
app.include_router(slack_router)
app.include_router(projects_router)
app.include_router(plane_integration_router)
app.include_router(plane_router)


@app.post("/api/ai-twins/analyze", response_model=AnalyzeResponse)
def ai_twins_analyze(request: AnalyzeRequest) -> dict:
    return analyze(request.model_dump())
