from fastapi import APIRouter

from app.api.endpoints import enroll, verify, search, health, speakers, models, reembed

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(models.router, tags=["models"])
api_router.include_router(speakers.router, tags=["speakers"])
api_router.include_router(enroll.router, tags=["enroll"])
api_router.include_router(verify.router, tags=["verify"])
api_router.include_router(search.router, tags=["search"])
api_router.include_router(reembed.router, tags=["reembed"])
