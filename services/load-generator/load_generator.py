import time
import random
import logging
import threading
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, Gauge, start_http_server, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.core import CollectorRegistry
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Custom registry
registry = CollectorRegistry()

# Prometheus Metrics
LOAD_GENERATOR_REQUESTS = Counter('load_generator_requests_total', 'Total requests sent by load generator',
                                 ['target_service', 'endpoint', 'method', 'status'], registry=registry)

LOAD_GENERATOR_RESPONSE_TIME = Histogram('load_generator_response_time_seconds', 'Response time of generated requests',
                                        ['target_service', 'endpoint'], registry=registry)

ACTIVE_THREADS = Gauge('load_generator_active_threads', 'Number of active load generation threads',
                      registry=registry)

REQUESTS_PER_SECOND = Gauge('load_generator_requests_per_second', 'Current requests per second rate',
                           registry=registry)

SIMULATED_USERS = Gauge('load_generator_simulated_users', 'Number of simulated users',
                       registry=registry)

class LoadGenerator:
    def __init__(self):
        self.targets = {
            'api_service': 'http://api-service:8000',
            'auth_service': 'http://auth-service:3001',
            'telemetry_service': 'http://telemetry-generator:8001'
        }
        
        self.endpoints = {
            'api_service': [
                {'path': '/', 'method': 'GET', 'weight': 30},
                {'path': '/health', 'method': 'GET', 'weight': 40},
                {'path': '/api/users', 'method': 'GET', 'weight': 20},
                {'path': '/api/network/status', 'method': 'GET', 'weight': 8},
                {'path': '/api/telemetry', 'method': 'GET', 'weight': 2}
            ],
            'auth_service': [
                {'path': '/', 'method': 'GET', 'weight': 30},
                {'path': '/health', 'method': 'GET', 'weight': 40},
                {'path': '/auth/login', 'method': 'POST', 'weight': 20},
                {'path': '/auth/stats', 'method': 'GET', 'weight': 10}
            ],
            'telemetry_service': [
                {'path': '/', 'method': 'GET', 'weight': 25},
                {'path': '/health', 'method': 'GET', 'weight': 35},
                {'path': '/metrics', 'method': 'GET', 'weight': 30},
                {'path': '/inject_anomaly/latency', 'method': 'GET', 'weight': 5},
                {'path': '/clear_anomalies', 'method': 'GET', 'weight': 5}
            ]
        }
        
        self.load_patterns = {
            'light': {'rps': 10, 'duration': 60, 'users': 5},
            'medium': {'rps': 50, 'duration': 120, 'users': 20},
            'heavy': {'rps': 200, 'duration': 180, 'users': 50},
            'burst': {'rps': 500, 'duration': 30, 'users': 100}
        }
        
        self.active_loads = {}
        self.session_tokens = {}
        self.executor = ThreadPoolExecutor(max_workers=100)
        
        logger.info("Load generator initialized")
    
    def get_auth_token(self):
        """Get authentication token for API requests"""
        try:
            if 'token' in self.session_tokens:
                # Check if token is still valid
                response = requests.get(
                    f"{self.targets['auth_service']}/auth/verify",
                    headers={'Authorization': f"Bearer {self.session_tokens['token']}"},
                    timeout=5
                )
                if response.status_code == 200:
                    return self.session_tokens['token']
            
            # Get new token
            response = requests.post(
                f"{self.targets['auth_service']}/auth/login",
                json={'username': 'user', 'password': 'password'},
                timeout=5
            )
            
            if response.status_code == 200:
                token = response.json()['token']
                self.session_tokens['token'] = token
                return token
            
        except Exception as e:
            logger.error(f"Error getting auth token: {e}")
        
        return None
    
    def make_request(self, service, endpoint_config, user_id=None):
        """Make a single request to target service"""
        try:
            target_url = f"{self.targets[service]}{endpoint_config['path']}"
            headers = {'User-Agent': f'LoadGenerator-User-{user_id}'}
            
            # Add auth token for protected endpoints
            if endpoint_config['path'].startswith('/api/') and endpoint_config['method'] == 'GET':
                token = self.get_auth_token()
                if token:
                    headers['Authorization'] = f'Bearer {token}'
            
            start_time = time.time()
            
            if endpoint_config['method'] == 'GET':
                response = requests.get(target_url, headers=headers, timeout=10)
            elif endpoint_config['method'] == 'POST':
                if endpoint_config['path'] == '/auth/login':
                    data = {'username': 'user', 'password': 'password'}
                else:
                    data = {'test': 'load_generation'}
                response = requests.post(target_url, json=data, headers=headers, timeout=10)
            else:
                response = requests.request(endpoint_config['method'], target_url, headers=headers, timeout=10)
            
            response_time = time.time() - start_time
            
            # Record metrics
            LOAD_GENERATOR_REQUESTS.labels(
                target_service=service,
                endpoint=endpoint_config['path'],
                method=endpoint_config['method'],
                status=response.status_code
            ).inc()
            
            LOAD_GENERATOR_RESPONSE_TIME.labels(
                target_service=service,
                endpoint=endpoint_config['path']
            ).observe(response_time)
            
            return {
                'success': True,
                'status_code': response.status_code,
                'response_time': response_time,
                'user_id': user_id
            }
            
        except Exception as e:
            logger.error(f"Request failed for {service}{endpoint_config['path']}: {e}")
            
            LOAD_GENERATOR_REQUESTS.labels(
                target_service=service,
                endpoint=endpoint_config['path'],
                method=endpoint_config['method'],
                status='error'
            ).inc()
            
            return {
                'success': False,
                'error': str(e),
                'user_id': user_id
            }
    
    def select_endpoint(self, service):
        """Select endpoint based on weights"""
        endpoints = self.endpoints[service]
        weights = [ep['weight'] for ep in endpoints]
        return random.choices(endpoints, weights=weights)[0]
    
    def simulate_user_behavior(self, user_id, duration, rps):
        """Simulate a single user's behavior"""
        end_time = time.time() + duration
        request_interval = 1.0 / rps if rps > 0 else 1.0
        
        while time.time() < end_time:
            # Select random service and endpoint
            service = random.choice(list(self.targets.keys()))
            endpoint = self.select_endpoint(service)
            
            # Make request
            result = self.make_request(service, endpoint, user_id)
            
            # Log interesting events
            if not result['success'] or (result.get('status_code', 200) >= 400):
                logger.warning(f"User {user_id} request failed: {result}")
            
            # Wait before next request
            time.sleep(request_interval + random.uniform(-0.1, 0.1))  # Add some randomness
    
    def start_load_test(self, pattern_name, custom_config=None):
        """Start a load test with specified pattern"""
        try:
            if custom_config:
                config = custom_config
            else:
                config = self.load_patterns.get(pattern_name, self.load_patterns['medium'])
            
            load_id = str(uuid.uuid4())
            
            logger.info(f"Starting load test {load_id} with pattern: {pattern_name}")
            logger.info(f"Config: {config}")
            
            # Start user simulation threads
            futures = []
            for i in range(config['users']):
                user_id = f"user_{load_id}_{i}"
                future = self.executor.submit(
                    self.simulate_user_behavior,
                    user_id,
                    config['duration'],
                    config['rps'] / config['users']
                )
                futures.append(future)
            
            # Store active load info
            self.active_loads[load_id] = {
                'pattern': pattern_name,
                'config': config,
                'start_time': datetime.now(),
                'futures': futures,
                'users': config['users']
            }
            
            # Update metrics
            SIMULATED_USERS.set(sum(load['users'] for load in self.active_loads.values()))
            ACTIVE_THREADS.set(len(self.active_loads))
            REQUESTS_PER_SECOND.set(config['rps'])
            
            return {
                'load_id': load_id,
                'status': 'started',
                'config': config,
                'message': f'Load test started with {config["users"]} users'
            }
            
        except Exception as e:
            logger.error(f"Error starting load test: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def stop_load_test(self, load_id):
        """Stop a specific load test"""
        try:
            if load_id not in self.active_loads:
                return {'status': 'error', 'message': 'Load test not found'}
            
            load_info = self.active_loads[load_id]
            
            # Cancel futures (this is a simplified approach)
            for future in load_info['futures']:
                future.cancel()
            
            # Remove from active loads
            del self.active_loads[load_id]
            
            # Update metrics
            SIMULATED_USERS.set(sum(load['users'] for load in self.active_loads.values()))
            ACTIVE_THREADS.set(len(self.active_loads))
            
            return {
                'status': 'stopped',
                'load_id': load_id,
                'message': 'Load test stopped successfully'
            }
            
        except Exception as e:
            logger.error(f"Error stopping load test: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def get_active_loads(self):
        """Get information about active load tests"""
        active_loads_info = {}
        for load_id, load_info in self.active_loads.items():
            runtime = datetime.now() - load_info['start_time']
            active_loads_info[load_id] = {
                'pattern': load_info['pattern'],
                'config': load_info['config'],
                'start_time': load_info['start_time'].isoformat(),
                'runtime_seconds': runtime.total_seconds(),
                'users': load_info['users']
            }
        
        return active_loads_info

# Initialize load generator
load_gen = LoadGenerator()

# Flask routes
@app.route('/')
def home():
    return {"message": "Load Generator Service", "status": "running"}

@app.route('/health')
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.route('/metrics')
def metrics():
    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)

@app.route('/load/start', methods=['POST'])
def start_load():
    data = request.get_json() or {}
    pattern = data.get('pattern', 'medium')
    custom_config = data.get('custom_config')
    
    result = load_gen.start_load_test(pattern, custom_config)
    return jsonify(result)

@app.route('/load/stop/<load_id>', methods=['POST'])
def stop_load(load_id):
    result = load_gen.stop_load_test(load_id)
    return jsonify(result)

@app.route('/load/active')
def active_loads():
    return jsonify(load_gen.get_active_loads())

@app.route('/load/patterns')
def get_patterns():
    return jsonify({
        'available_patterns': load_gen.load_patterns,
        'current_active': len(load_gen.active_loads)
    })

@app.route('/load/stop_all', methods=['POST'])
def stop_all_loads():
    """Stop all active load tests"""
    load_ids = list(load_gen.active_loads.keys())
    results = []
    
    for load_id in load_ids:
        result = load_gen.stop_load_test(load_id)
        results.append(result)
    
    return jsonify({
        'status': 'all_stopped',
        'stopped_tests': results
    })

def main():
    """Main function"""
    logger.info("Starting Load Generator Service...")
    
    # Start Prometheus metrics server
    start_http_server(8002, registry=registry)
    
    # Start Flask app
    app.run(host='0.0.0.0', port=8002, debug=False)

if __name__ == "__main__":
    main()
