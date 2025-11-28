from fastapi import FastAPI, Depends, HTTPException
from typing import AsyncGenerator
from psycopg import AsyncConnection
from redis.asyncio import Redis

from app.database import get_db_connection, get_redis_client
from app.schemas import (
    DocumentContext, 
    PolicyResponse, 
    LogRequest, 
    FeedbackRequest
)
from app.services.memory import MemoryService

app = FastAPI(title="AHMN: Adaptive Hierarchical Memory Network")

# Dependency to get MemoryService
async def get_memory_service(
    db: AsyncConnection = Depends(get_db_connection),
    redis: Redis = Depends(get_redis_client)
) -> MemoryService:
    return MemoryService(db, redis)

@app.post("/advice", response_model=PolicyResponse)
async def get_advice(
    context: DocumentContext,
    memory: MemoryService = Depends(get_memory_service)
):
    """
    Get processing advice based on document context.
    """
    return await memory.get_advice(context)

@app.post("/log")
async def log_outcome(
    request: LogRequest,
    memory: MemoryService = Depends(get_memory_service)
):
    """
    Log the outcome of a processing job to Mid-Term Memory.
    """
    await memory.log_outcome(
        request.advice_id, 
        request.policy_id_used, 
        request.metrics
    )
    return {"status": "logged"}

@app.post("/feedback")
async def log_feedback(
    request: FeedbackRequest,
    memory: MemoryService = Depends(get_memory_service)
):
    """
    Log human feedback (correction) for a specific advice.
    """
    await memory.log_feedback(request.advice_id, request.human_corrected)
    return {"status": "feedback_recorded"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
