import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'method'):
            log_data['method'] = record.method
        if hasattr(record, 'path'):
            log_data['path'] = record.path
        if hasattr(record, 'status'):
            log_data['status'] = record.status
        if hasattr(record, 'latency_ms'):
            log_data['latency_ms'] = record.latency_ms
        if hasattr(record, 'message_id'):
            log_data['message_id'] = record.message_id
        if hasattr(record, 'dup'):
            log_data['dup'] = record.dup
        if hasattr(record, 'result'):
            log_data['result'] = record.result
            
        return json.dumps(log_data)

def setup_logging(log_level: str = "INFO"):
    """Setup JSON logging"""
    logger = logging.getLogger("webhook_api")
    logger.setLevel(log_level)
    
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    
    return logger

class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, logger):
        super().__init__(app)
        self.logger = logger
    
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        start_time = time.time()
        
        response = await call_next(request)
        
        latency_ms = round((time.time() - start_time) * 1000, 2)
        
        # Create log record
        extra = {
            'request_id': request_id,
            'method': request.method,
            'path': request.url.path,
            'status': response.status_code,
            'latency_ms': latency_ms
        }
        
        self.logger.info(f"{request.method} {request.url.path} {response.status_code}", extra=extra)
        
        return response