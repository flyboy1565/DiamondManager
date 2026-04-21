from ninja import NinjaAPI
from ninja_extra import NinjaExtraAPI
from ninja_jwt.controller import NinjaJWTDefaultController
from leagues.api import router as leagues_router
from competition.api import router as competition_router
from profiles.api import router as profiles_router

api = NinjaExtraAPI(
    title="Diamond Manager API",
    version="1.0.0",
    description="API for managing youth sports organizations, seasons, and games.",
)

# 1. Instantiate the controller
# 2. Access its internal router directly
api.register_controllers(NinjaJWTDefaultController)

# Standard routers remain the same
api.add_router("/profiles", profiles_router, tags=["Profiles"])
api.add_router("/leagues", leagues_router, tags=["Leagues"])
api.add_router("/competition", competition_router, tags=["Competition"])