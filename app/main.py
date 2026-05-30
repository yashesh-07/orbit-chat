import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.services.cache_service import cache_service
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router

# Setup unified system root logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orbitchat.core")

# =========================================================================
# APPLICATION LIFECYCLE MANAGEMENT (Lifespan Events)
# =========================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages resource startup and shutdown cycles safely.
    Warms up shared microservice connection pools before accepting web traffic.
    """
    logger.info("Initializing OrbitChat enterprise engine components...")
    
    # 1. Connect to the distributed Redis cache layer
    cache_service.initialize()
    
    # Check connection health to Redis right away
    try:
        await cache_service.client.ping()
        logger.info("Redis cache cluster health-check passed successfully.")
    except Exception as error:
        logger.critical(f"FATAL: Redis cluster unreachable on boot! {str(error)}")
        raise SystemExit(1)

    logger.info("OrbitChat gateway initialization finalized. Open for incoming connections.")
    
    yield  # ─── Server is now fully online and processing user traffic ───

    logger.info("Application shutdown initiated. Tearing down stateful footprints...")
    
    # 2. Drain Redis connection pools cleanly on exit
    await cache_service.close()
    
    logger.info("OrbitChat system components safely deactivated.")


# =========================================================================
# APPLICATION INSTANTIATION & CONFIGURATION
# =========================================================================
app = FastAPI(
    title="OrbitChat Architecture Core",
    description="High-Performance Asynchronous Microservices Gateway handling 50M DAU.",
    version="1.0.0",
    lifespan=lifespan
)

# Cross-Origin Resource Sharing (CORS) Configuration
# Essential for letting our client-side frontend code securely talk to our backend API ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this to explicit production web domains in deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach domain-isolated endpoints
app.add_api_route("/", endpoint=lambda: {"status": "operational", "engine": "OrbitChat Core v1.0"})
app.include_router(auth_router)
app.include_router(chat_router)