from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
import time
import random
import logging
import requests
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Edge AI Reliability Monitor - API Service", version="1.0.0")

# Security
security = HTTPBearer()

# Prometheus Metrics
REQUEST_COUNT = Counter('api_requests_total', 'Total API requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('api_request_duration_seconds', 'API request duration')
CPU_USAGE = Gauge('api_cpu_usage_percent', 'API service CPU usage')
MEMORY_USAGE = Gauge('api_memory_usage_mb', 'API service memory usage')
ACTIVE_CONNECTIONS = Gauge('api_active_connections', 'Active connections')

# Simulated service state
active_connections = 0

@app.middleware("http")
async def metrics_middleware(request, call_next):
    start_time = time.time()
    
    # Increment active connections
    global active_connections
    active_connections += 1
    ACTIVE_CONNECTIONS.set(active_connections)
    
    try:
        response = await call_next(request)
        
        # Record metrics
        duration = time.time() - start_time
        REQUEST_DURATION.observe(duration)
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        
        # Simulate resource usage
        CPU_USAGE.set(random.uniform(20, 80))
        MEMORY_USAGE.set(random.uniform(100, 300))
        
        return response
    
    finally:
        active_connections -= 1
        ACTIVE_CONNECTIONS.set(active_connections)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Edge AI Reliability Monitor - API Service", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/api/users")
async def get_users(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get users endpoint - simulates telecom user management"""
    try:
        # Simulate database query delay
        time.sleep(random.uniform(0.1, 0.5))
        
        users = [
            {"id": 1, "name": "John Doe", "phone": "+353123456789", "plan": "premium"},
            {"id": 2, "name": "Jane Smith", "phone": "+353987654321", "plan": "standard"},
            {"id": 3, "name": "Mike Johnson", "phone": "+353456789123", "plan": "premium"}
        ]
        
        logger.info(f"Retrieved {len(users)} users")
        return {"users": users, "count": len(users)}
    
    except Exception as e:
        logger.error(f"Error retrieving users: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/network/status")
async def get_network_status(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get network status - simulates telecom network monitoring"""
    try:
        # Simulate network metrics
        network_status = {
            "base_stations": {
                "total": 50,
                "active": 47,
                "maintenance": 3
            },
            "connected_users": 12450,
            "average_latency_ms": random.uniform(15, 45),
            "packet_loss_percent": random.uniform(0.1, 2.0),
            "bandwidth_utilization": random.uniform(60, 90),
            "timestamp": time.time()
        }
        
        logger.info("Network status retrieved")
        return network_status
    
    except Exception as e:
        logger.error(f"Error retrieving network status: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/simulate/load")
async def simulate_load(load_config: Dict[str, Any]):
    """Simulate system load for testing"""
    try:
        duration = load_config.get("duration", 30)
        intensity = load_config.get("intensity", "medium")
        
        logger.info(f"Simulating {intensity} load for {duration} seconds")
        
        # Simulate CPU-intensive work
        end_time = time.time() + duration
        while time.time() < end_time:
            if intensity == "high":
                # More intensive computation
                sum(i * i for i in range(1000))
            else:
                # Lighter computation
                sum(i for i in range(100))
            time.sleep(0.1)
        
        return {"message": "Load simulation completed", "duration": duration, "intensity": intensity}
    
    except Exception as e:
        logger.error(f"Error in load simulation: {str(e)}")
        raise HTTPException(status_code=500, detail="Load simulation failed")

@app.get("/api/telemetry")
async def get_telemetry():
    """Get service telemetry data"""
    try:
        telemetry = {
            "service": "api-service",
            "version": "1.0.0",
            "uptime_seconds": time.time(),
            "requests_per_minute": random.randint(50, 200),
            "error_rate_percent": random.uniform(0.1, 2.0),
            "response_time_avg_ms": random.uniform(100, 500),
            "cpu_usage_percent": random.uniform(20, 80),
            "memory_usage_mb": random.uniform(100, 300),
            "disk_usage_percent": random.uniform(30, 70),
            "network_io_kb_per_sec": random.uniform(100, 1000)
        }
        
        return telemetry
    
    except Exception as e:
        logger.error(f"Error retrieving telemetry: {str(e)}")
        raise HTTPException(status_code=500, detail="Telemetry retrieval failed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
