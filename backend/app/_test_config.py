from app.core.config import settings

print("DATABASE_URL:", settings.DATABASE_URL)
print("JWT_ALG:", settings.JWT_ALG)
print("JWT_EXPIRE_MIN:", settings.JWT_EXPIRE_MIN)
print("JWT_SECRET (len):", len(settings.JWT_SECRET))