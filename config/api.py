from ninja import NinjaAPI
from ninja_extra import NinjaExtraAPI
from ninja_jwt.controller import NinjaJWTDefaultController
from leagues.api import router as leagues_router
from competition.api import router as competition_router
from profiles.api import router as profiles_router

from ninja import Schema
from ninja_extra import route, api_controller, NinjaExtraAPI
from ninja_jwt.controller import TokenObtainPairController
# Import the explicit input schema
from ninja_jwt.schema import TokenObtainPairInputSchema 

# 1. Your Custom Schemas (Keep these)
class UserPayloadSchema(Schema):
    id: int
    username: str
    roles: list[str]

class CustomTokenOutputSchema(Schema):
    access: str
    refresh: str
    user: UserPayloadSchema

# 2. The Controller
@api_controller("/token", tags=["Auth"])
class MyTokenController(TokenObtainPairController):
    
    # Use TokenObtainPairInputSchema directly here
    @route.post("/pair", response=CustomTokenOutputSchema, url_name="token_obtain_pair")
    def obtain_token(self, user_token: TokenObtainPairInputSchema):
        # The logic remains the same
        user = user_token._user 
        
        # Pull roles from Django Groups
        roles = list(user.groups.values_list('name', flat=True))
        if user.is_superuser:
            roles.append("OWNER")
            
        token_data = user_token.to_response_schema()
        
        return {
            "access": str(token_data.access),
            "refresh": str(token_data.refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "roles": roles
            }
        }


api = NinjaExtraAPI(
    title="Diamond Manager API",
    version="1.0.0",
    description="API for managing youth sports organizations, seasons, and games.",
)

# 1. Instantiate the controller
# 2. Access its internal router directly
api.register_controllers(MyTokenController)

# Standard routers remain the same
api.add_router("/profiles", profiles_router, tags=["Profiles"])
api.add_router("/leagues", leagues_router, tags=["Leagues"])
api.add_router("/competition", competition_router, tags=["Competition"])