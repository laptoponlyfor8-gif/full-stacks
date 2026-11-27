from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.ai import router as ai_router
from app.api.v1.automations import router as automations_router
from app.api.v1.billing import router as billing_router
from app.api.v1.billing import webhook_router as razorpay_webhook_router
from app.api.v1.crm import router as crm_router
from app.api.v1.health import router as health_router
from app.api.v1.meta import router as meta_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.webhooks import router as webhooks_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(ai_router)
api_router.include_router(billing_router)
api_router.include_router(razorpay_webhook_router)
api_router.include_router(meta_router)
api_router.include_router(automations_router)
api_router.include_router(crm_router)
api_router.include_router(webhooks_router)
api_router.include_router(organizations_router)
