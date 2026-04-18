from ninja import NinjaAPI
from leagues.api import router as leagues_router
from competition.api import router as competition_router

api = NinjaAPI(
    title="Diamond Manager API",
    version="1.0.0",
    description="API for managing youth sports organizations, seasons, and games."
)

# Mount the routers
api.add_router("/leagues", leagues_router, tags=["Leagues"])
api.add_router("/competition", competition_router, tags=["Competition"])