from fastapi import FastAPI
from app.api.v1 import ownership

app = FastAPI(title="ThinkRealty Ownership Transfer System")

@app.get("/", tags=["Health Check"])
async def read_root():
    return {"status": "ok", "message": "Welcome to ThinkRealty Ownership Transfer System"}

app.include_router(ownership.router, prefix="/api/v1")
