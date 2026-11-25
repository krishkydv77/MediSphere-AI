from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

# 1. Rate Limiting Setup (100-200 users ke liye spam protection)
limiter = Limiter(key_func=get_remote_address)

SECRET_KEY = "your_super_secret_jwt_key_here"
ALGORITHM = "HS256"
security = HTTPBearer()

# 2. JWT Token Generation & Verification
def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=12)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid or expired token")

# 3. RBAC (Role-Based Access Control) Middleware / Dependency
def require_role(required_role: str):
    def role_dependency(payload: dict = Depends(verify_jwt_token)):
        user_role = payload.get("role")
        if user_role != required_role and user_role != "Super Admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail=f"Access denied: Role '{user_role}' lacks permission.")
        return payload
    return role_dependency

# 4. OAuth Integration (Google Login Setup)
# Apne Google Client ID aur Secret yahan daalein ya environment variables se lein
config = Config(environ={
    "GOOGLE_CLIENT_ID": "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "YOUR_GOOGLE_CLIENT_SECRET"
})
oauth = OAuth(config)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_options={'scope': 'openid email profile'}
)




#Admin Login ke liye:Email: admin@sanjeevani.com   Password: admin123   System Login ke liye:System User ID: SYS_MONITOR_01   Password: syspass123