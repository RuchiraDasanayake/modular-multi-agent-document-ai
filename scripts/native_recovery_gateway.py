"""Auth/readiness-only ASGI boundary for a passive local recovery copy."""
from gateway.main import app
from fastapi.responses import JSONResponse


@app.middleware("http")
async def passive_requests_only(request, call_next):
    allowed = (request.method, request.url.path) in {
        ("GET", "/health"), ("GET", "/api/auth/me"), ("POST", "/api/auth/login")}
    if not allowed or request.url.query:
        return JSONResponse({"error": "This recovery copy is read-only."}, status_code=423,
                            headers={"X-DocAI-Recovery": "read-only"})
    response = await call_next(request)
    response.headers["X-DocAI-Recovery"] = "read-only"
    return response
