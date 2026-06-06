"""SSE stream router — real-time log and progress events."""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from services.research_service import get_sse_queue

router = APIRouter(prefix="/api", tags=["stream"])


@router.get("/stream")
async def stream(request: Request):
    """SSE endpoint for real-time research logs and progress."""
    queue = get_sse_queue()

    async def event_generator():
        # Send initial connected event
        yield f"event: connected\ndata: {json.dumps({'message': 'SSE stream connected'})}\n\n"

        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                # Wait for next event with timeout (allows disconnect detection)
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
                    continue

                event_type = event.get("event", "message")
                data = event.get("data", {})

                yield f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
