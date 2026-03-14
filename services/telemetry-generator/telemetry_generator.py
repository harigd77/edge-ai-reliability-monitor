import time
import random
import logging
import psutil
import schedule
import requests
import json
import numpy as np
from datetime import datetime, timedelta
from prometheus_client import Counter, Histogram, Gauge, start_http_server, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.core import CollectorRegistry
from flask import Flask, Response
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app for metrics endpoint
app = Flask(__name__)

# Custom registry
registry = CollectorRegistry()

# Prometheus Metrics for generated telemetry
NETWORK_LATENCY = Histogram('network_latency_ms', 'Network latency in milliseconds', 
                           ['source', 'destination', 'protocol'], registry=registry)

PACKET_LOSS = Gauge('packet_loss_percent', 'Packet loss percentage', 
                   ['interface'], registry=registry)

BANDWIDTH_UTILIZATION = Gauge('bandwidth_utilization_percent', 'Bandwidth utilization percentage',
                             ['interface'], registry=registry)

BASE_STATION_STATUS = Gauge('base_station_status', 'Base station operational status',
                           ['station_id', 'location'], registry=registry)

CONNECTED_USERS = Gauge('connected_users_total', 'Total connected users',
                       ['cell_tower'], registry=registry)

SIGNAL_STRENGTH = Histogram('signal_strength_dbm', 'Signal strength in dBm',
                           ['user_id', 'cell_tower'], registry=registry)

API_RESPONSE_TIME = Histogram('api_response_time_seconds', 'API response time in seconds',
                             ['endpoint', 'method'], registry=registry)

ERROR_RATE = Gauge('error_rate_percent', 'Error rate percentage',
                  ['service', 'error_type'], registry=registry)

SYSTEM_RESOURCES = Gauge('system_resource_usage_percent', 'System resource usage',
                       ['resource_type', 'instance'], registry=registry)

# Counters for events
CONNECTION_EVENTS = Counter('connection_events_total', 'Connection events',
                           ['event_type', 'result'], registry=registry)

ANOMALY_EVENTS = Counter('anomaly_events_total', 'Anomaly detection events',
                         ['anomaly_type', 'severity'], registry=registry)

class TelemetryGenerator:
    def __init__(self):
        self.base_stations = [
            {'id': 'BS001', 'location': 'Dublin', 'lat': 53.3498, 'lon': -6.2603},
            {'id': 'BS002', 'location': 'Cork', 'lat': 51.8969, 'lon': -8.4863},
            {'id': 'BS003', 'location': 'Galway', 'lat': 53.2707, 'lon': -9.0568},
            {'id': 'BS004', 'location': 'Limerick', 'lat': 52.6631, 'lon': -8.6249},
            {'id': 'BS005', 'location': 'Waterford', 'lat': 52.2593, 'lon': -7.1101}
        ]
        
        self.interfaces = ['eth0', 'wlan0', '5g-interface']
        self.services = ['api-service', 'auth-service', 'telemetry-generator']
        self.endpoints = ['/api/users', '/api/network/status', '/api/telemetry', '/auth/login']
        
        # Anomaly injection flags
        self.inject_latency_spike = False
        self.inject_packet_loss = False
        self.inject_error_rate = False
        
        logger.info("Telemetry generator initialized")
    
    def generate_network_metrics(self):
        """Generate network-related telemetry"""
        try:
            # Network latency simulation
            for source in ['user', 'base_station', 'core_network']:
                for dest in ['api_service', 'auth_service', 'database']:
                    base_latency = random.uniform(10, 50)
                    
                    # Inject latency spike anomaly
                    if self.inject_latency_spike and random.random() < 0.3:
                        base_latency *= random.uniform(3, 10)
                        ANOMALY_EVENTS.labels(anomaly_type='latency_spike', severity='high').inc()
                        logger.warning(f"Latency spike anomaly injected: {base_latency:.2f}ms")
                    
                    NETWORK_LATENCY.labels(source=source, destination=dest, protocol='HTTP').observe(base_latency)
                    NETWORK_LATENCY.labels(source=source, destination=dest, protocol='5G').observe(base_latency * 0.8)
            
            # Packet loss simulation
            for interface in self.interfaces:
                base_loss = random.uniform(0.1, 2.0)
                
                # Inject packet loss anomaly
                if self.inject_packet_loss and random.random() < 0.2:
                    base_loss = random.uniform(5.0, 15.0)
                    ANOMALY_EVENTS.labels(anomaly_type='packet_loss', severity='medium').inc()
                    logger.warning(f"Packet loss anomaly injected: {base_loss:.2f}%")
                
                PACKET_LOSS.labels(interface=interface).set(base_loss)
            
            # Bandwidth utilization
            for interface in self.interfaces:
                utilization = random.uniform(40, 85)
                BANDWIDTH_UTILIZATION.labels(interface=interface).set(utilization)
            
        except Exception as e:
            logger.error(f"Error generating network metrics: {e}")
    
    def generate_telecom_metrics(self):
        """Generate telecom-specific telemetry"""
        try:
            # Base station status (1 = active, 0 = maintenance, -1 = down)
            for station in self.base_stations:
                status_weights = [0.9, 0.08, 0.02]  # 90% active, 8% maintenance, 2% down
                status = random.choices([1, 0, -1], weights=status_weights)[0]
                BASE_STATION_STATUS.labels(station_id=station['id'], location=station['location']).set(status)
            
            # Connected users per cell tower
            for station in self.base_stations:
                users = random.randint(100, 2000)
                CONNECTED_USERS.labels(cell_tower=station['id']).set(users)
            
            # Signal strength for sample users
            for i in range(10):  # Sample 10 users
                user_id = f"user_{i+1}"
                tower = random.choice(self.base_stations)['id']
                
                # Signal strength typically ranges from -120 to -70 dBm
                signal_strength = random.uniform(-120, -70)
                SIGNAL_STRENGTH.labels(user_id=user_id, cell_tower=tower).observe(signal_strength)
            
        except Exception as e:
            logger.error(f"Error generating telecom metrics: {e}")
    
    def generate_application_metrics(self):
        """Generate application performance metrics"""
        try:
            # API response times
            for endpoint in self.endpoints:
                for method in ['GET', 'POST']:
                    base_response_time = random.uniform(0.1, 2.0)
                    
                    # Inject response time anomaly
                    if self.inject_latency_spike and random.random() < 0.2:
                        base_response_time *= random.uniform(2, 5)
                        ANOMALY_EVENTS.labels(anomaly_type='response_time', severity='medium').inc()
                    
                    API_RESPONSE_TIME.labels(endpoint=endpoint, method=method).observe(base_response_time)
            
            # Error rates
            for service in self.services:
                for error_type in ['4xx', '5x', 'timeout']:
                    base_error_rate = random.uniform(0.1, 3.0)
                    
                    # Inject error rate anomaly
                    if self.inject_error_rate and random.random() < 0.15:
                        base_error_rate = random.uniform(5.0, 20.0)
                        ANOMALY_EVENTS.labels(anomaly_type='error_rate', severity='high').inc()
                        logger.warning(f"Error rate anomaly injected for {service}: {base_error_rate:.2f}%")
                    
                    ERROR_RATE.labels(service=service, error_type=error_type).set(base_error_rate)
            
        except Exception as e:
            logger.error(f"Error generating application metrics: {e}")
    
    def generate_system_metrics(self):
        """Generate system resource metrics"""
        try:
            # Get actual system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # System resources
            SYSTEM_RESOURCES.labels(resource_type='cpu', instance='telemetry-generator').set(cpu_percent)
            SYSTEM_RESOURCES.labels(resource_type='memory', instance='telemetry-generator').set(memory.percent)
            SYSTEM_RESOURCES.labels(resource_type='disk', instance='telemetry-generator').set(disk.percent)
            
            # Simulate other instances
            for instance in ['api-service', 'auth-service', 'database']:
                SYSTEM_RESOURCES.labels(resource_type='cpu', instance=instance).set(random.uniform(20, 80))
                SYSTEM_RESOURCES.labels(resource_type='memory', instance=instance).set(random.uniform(30, 70))
                SYSTEM_RESOURCES.labels(resource_type='disk', instance=instance).set(random.uniform(40, 60))
            
        except Exception as e:
            logger.error(f"Error generating system metrics: {e}")
    
    def generate_connection_events(self):
        """Generate connection events"""
        try:
            # Simulate user connections/disconnections
            for _ in range(random.randint(1, 5)):
                event_type = random.choice(['connect', 'disconnect'])
                result = random.choice(['success', 'failure'])
                CONNECTION_EVENTS.labels(event_type=event_type, result=result).inc()
            
        except Exception as e:
            logger.error(f"Error generating connection events: {e}")
    
    def inject_anomalies(self, anomaly_type=None):
        """Control anomaly injection"""
        if anomaly_type == 'latency':
            self.inject_latency_spike = True
            logger.info("Latency spike anomaly injection enabled")
        elif anomaly_type == 'packet_loss':
            self.inject_packet_loss = True
            logger.info("Packet loss anomaly injection enabled")
        elif anomaly_type == 'error_rate':
            self.inject_error_rate = True
            logger.info("Error rate anomaly injection enabled")
        elif anomaly_type == 'clear':
            self.inject_latency_spike = False
            self.inject_packet_loss = False
            self.inject_error_rate = False
            logger.info("All anomaly injections cleared")
    
    def generate_all_metrics(self):
        """Generate all telemetry metrics"""
        logger.info("Generating telemetry metrics...")
        self.generate_network_metrics()
        self.generate_telecom_metrics()
        self.generate_application_metrics()
        self.generate_system_metrics()
        self.generate_connection_events()
        logger.info("Telemetry generation completed")

# Initialize telemetry generator
telemetry_gen = TelemetryGenerator()

# Flask routes
@app.route('/')
def home():
    return {"message": "Telemetry Generator Service", "status": "running"}

@app.route('/health')
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.route('/metrics')
def metrics():
    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)

@app.route('/inject_anomaly/<anomaly_type>')
def inject_anomaly(anomaly_type):
    telemetry_gen.inject_anomalies(anomaly_type)
    return {"message": f"Anomaly injection {anomaly_type} processed"}

@app.route('/clear_anomalies')
def clear_anomalies():
    telemetry_gen.inject_anomalies('clear')
    return {"message": "All anomaly injections cleared"}

def run_telemetry_generation():
    """Run telemetry generation in background"""
    while True:
        try:
            telemetry_gen.generate_all_metrics()
            time.sleep(10)  # Generate metrics every 10 seconds
        except Exception as e:
            logger.error(f"Error in telemetry generation loop: {e}")
            time.sleep(5)

def main():
    """Main function"""
    logger.info("Starting Telemetry Generator Service...")
    
    # Start telemetry generation in background thread
    telemetry_thread = threading.Thread(target=run_telemetry_generation, daemon=True)
    telemetry_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=8001, debug=False)

if __name__ == "__main__":
    main()
