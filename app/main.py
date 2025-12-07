import hmac
import hashlib
import logging
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import Optional

from app.config import settings, validate_settings
from app.models import WebhookMessage, MessagesListResponse, MessageResponse, StatsResponse
from app.storage import get_db
from app.logging_utils import setup_logging, LoggingMiddleware
from app.metrics import (
    record_http_request, record_webhook_request, record_latency,
    get_metrics
)

# Setup logging
logger = setup_logging(settings.log_level)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    try:
        # Validate settings on startup
        validate_settings()
        logger.info("Settings validated successfully")
        
        # Initialize database
        db = get_db()
        logger.info("Database initialized successfully")
        
        yield
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}")
        raise

app = FastAPI(
    title="Webhook API",
    description="WhatsApp-like webhook message processor",
    version="1.0.0",
    lifespan=lifespan
)

# Add logging middleware
app.add_middleware(LoggingMiddleware, logger=logger)

def verify_signature(body: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature"""
    expected = hmac.new(
        settings.webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    print("Expected signature:", expected)
    print("Received signature:", signature)
    print("Body bytes:", body)
    print("Webhook secret:", repr(settings.webhook_secret))

    return hmac.compare_digest(expected, signature)

import json
import re

def is_valid_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except Exception:
        return False


def pseudo_json_to_json_preserve_spaces(pseudo_json_str: str) -> str:
    # Step 1: Quote keys, preserve spaces
    s = re.sub(
        r'([{,])(\s*)([^":,\s]+)(\s*):(\s*)',
        lambda m: f'{m.group(1)}{m.group(2)}"{m.group(3)}"{m.group(4)}:{m.group(5)}',
        pseudo_json_str
    )
    
    def replacer(m):
        before_colon_spaces = m.group(1)
        val = m.group(2)
        after_val_spaces = m.group(3)
        
        if val is None:
            val = ''
        
        # Quote **every unquoted value**
        if val.startswith('"'):
            return f'{before_colon_spaces}{val}{after_val_spaces}'
        else:
            return f'{before_colon_spaces}"{val}"{after_val_spaces}'
    
    s = re.sub(
        r'(:\s*)([^",}{\s][^,}]*)?(\s*[,}])',
        replacer,
        s
    )
    
    return s

@app.post("/webhook")
async def webhook(request: Request):
    """Ingest WhatsApp-like messages with HMAC verification"""
    request_id = request.state.request_id
    
    # Get raw body and signature
    body = await request.body()
    signature = request.headers.get("X-Signature", "")
    raw = body.decode()
    if is_valid_json(raw):
        fixed = raw
    else:
        fixed = pseudo_json_to_json_preserve_spaces(raw)
    fixed_bytes = fixed.encode()
    # Verify signature
    if not verify_signature(fixed_bytes, signature):
        logger.error(
            "Invalid signature",
            extra={
                'request_id': request_id,
                'result': 'invalid_signature'
            }
        )
        record_webhook_request("invalid_signature")
        record_http_request("/webhook", 401)
        raise HTTPException(status_code=401, detail="invalid signature")
    
    # Parse and validate message
    try:
        message = WebhookMessage.model_validate_json(fixed_bytes)
    except Exception as e:
        logger.error(
            f"Validation error: {str(e)}",
            extra={
                'request_id': request_id,
                'result': 'validation_error'
            }
        )
        record_webhook_request("validation_error")
        record_http_request("/webhook", 422)
        raise HTTPException(status_code=422, detail=str(e))
    
    # Insert into database
    db = get_db()
    success, is_duplicate = db.insert_message(
        message.message_id,
        message.from_,
        message.to,
        message.ts,
        message.text
    )
    
    result = "duplicate" if is_duplicate else "created"
    
    logger.info(
        f"Webhook processed: {result}",
        extra={
            'request_id': request_id,
            'message_id': message.message_id,
            'dup': is_duplicate,
            'result': result
        }
    )
    
    record_webhook_request(result)
    record_http_request("/webhook", 200)
    
    return {"status": "ok"}

@app.get("/messages", response_model=MessagesListResponse)
async def get_messages(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    from_: Optional[str] = Query(None, alias="from"),
    since: Optional[str] = None,
    q: Optional[str] = None
):
    """List messages with pagination and filters"""
    db = get_db()
    messages, total = db.get_messages(
        limit=limit,
        offset=offset,
        from_msisdn=from_,
        since=since,
        q=q
    )
    
    # Convert to response format
    data = [
        MessageResponse(
            message_id=msg['message_id'],
            **{'from': msg['from_msisdn']},
            to=msg['to_msisdn'],
            ts=msg['ts'],
            text=msg['text']
        )
        for msg in messages
    ]
    
    record_http_request("/messages", 200)
    
    return MessagesListResponse(
        data=data,
        total=total,
        limit=limit,
        offset=offset
    )

@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get message statistics"""
    db = get_db()
    stats = db.get_stats()
    
    record_http_request("/stats", 200)
    
    return StatsResponse(**stats)

@app.get("/health/live")
async def health_live():
    """Liveness probe"""
    record_http_request("/health/live", 200)
    return {"status": "ok"}

@app.get("/health/ready")
async def health_ready():
    """Readiness probe"""
    try:
        # Check if WEBHOOK_SECRET is set
        if not settings.webhook_secret:
            raise HTTPException(status_code=503, detail="WEBHOOK_SECRET not set")
        
        # Check database
        db = get_db()
        if not db.is_ready():
            raise HTTPException(status_code=503, detail="Database not ready")
        
        record_http_request("/health/ready", 200)
        return {"status": "ok"}
    except HTTPException:
        record_http_request("/health/ready", 503)
        raise
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        record_http_request("/health/ready", 503)
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return get_metrics()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )