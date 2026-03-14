import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA
import joblib
import json
import schedule
from typing import Dict, List, Tuple, Any
import matplotlib.pyplot as plt
import seaborn as sns
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('anomaly_detector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AnomalyDetector:
    def __init__(self):
        self.prometheus_url = "http://prometheus:9090"
        self.models = {}
        self.scalers = {}
        self.anomaly_history = []
        self.metrics_buffer = []
        self.buffer_size = 1000
        
        # Initialize models for different metric types
        self.initialize_models()
        
        # Prometheus metrics for anomaly detection
        self.anomaly_counter = Counter('anomalies_detected_total', 'Total anomalies detected', 
                                     ['model', 'severity', 'metric_type'])
        self.model_accuracy = Gauge('anomaly_detection_accuracy', 'Model accuracy score')
        self.detection_latency = Histogram('anomaly_detection_latency_seconds', 'Anomaly detection latency')
        
        logger.info("Anomaly Detector initialized")
    
    def initialize_models(self):
        """Initialize machine learning models"""
        try:
            # Isolation Forest for general anomaly detection
            self.models['isolation_forest'] = IsolationForest(
                n_estimators=100,
                contamination=0.1,
                random_state=42
            )
            
            # DBSCAN for clustering-based anomaly detection
            self.models['dbscan'] = DBSCAN(
                eps=0.5,
                min_samples=5
            )
            
            # StandardScaler for data normalization
            self.scalers['standard'] = StandardScaler()
            
            logger.info("Machine learning models initialized")
            
        except Exception as e:
            logger.error(f"Error initializing models: {e}")
    
    def query_prometheus(self, query: str, start_time: str = None, end_time: str = None) -> List[Dict]:
        """Query Prometheus for metrics"""
        try:
            params = {'query': query}
            
            if start_time and end_time:
                params.update({
                    'start': start_time,
                    'end': end_time,
                    'step': '15s'
                })
            
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query_range",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'success':
                    return data['data']['result']
            
            logger.warning(f"Prometheus query failed: {response.status_code}")
            return []
            
        except Exception as e:
            logger.error(f"Error querying Prometheus: {e}")
            return []
    
    def collect_metrics(self) -> pd.DataFrame:
        """Collect metrics from Prometheus"""
        try:
            # Define queries for different metric types
            queries = {
                'api_response_time': 'histogram_quantile(0.95, rate(api_request_duration_seconds_bucket[5m]))',
                'api_error_rate': 'rate(api_requests_total{status_code=~"5.."}[5m]) / rate(api_requests_total[5m])',
                'cpu_usage': 'system_resource_usage_percent{resource_type="cpu"}',
                'memory_usage': 'system_resource_usage_percent{resource_type="memory"}',
                'network_latency': 'histogram_quantile(0.95, rate(network_latency_ms_bucket[5m]))',
                'packet_loss': 'packet_loss_percent',
                'connected_users': 'connected_users_total',
                'auth_failure_rate': 'rate(auth_attempts_total{result="failed"}[5m]) / rate(auth_attempts_total[5m])'
            }
            
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
            
            metrics_data = []
            
            for metric_name, query in queries.items():
                results = self.query_prometheus(
                    query,
                    start_time.isoformat(),
                    end_time.isoformat()
                )
                
                for result in results:
                    metric_data = {
                        'metric_name': metric_name,
                        'labels': result['metric'],
                        'values': result['values']
                    }
                    metrics_data.append(metric_data)
            
            # Convert to DataFrame
            df = pd.DataFrame(metrics_data)
            logger.info(f"Collected {len(df)} metric series")
            
            return df
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            return pd.DataFrame()
    
    def preprocess_data(self, df: pd.DataFrame) -> np.ndarray:
        """Preprocess data for anomaly detection"""
        try:
            # Extract numeric values from time series
            processed_data = []
            
            for _, row in df.iterrows():
                values = [float(val[1]) for val in row['values'] if val[1] != 'NaN']
                if values:
                    # Calculate statistical features
                    features = [
                        np.mean(values),
                        np.std(values),
                        np.percentile(values, 95),
                        np.percentile(values, 5),
                        np.max(values),
                        np.min(values),
                        len(values)
                    ]
                    processed_data.append(features)
            
            if not processed_data:
                return np.array([])
            
            # Convert to numpy array and scale
            X = np.array(processed_data)
            X_scaled = self.scalers['standard'].fit_transform(X)
            
            return X_scaled
            
        except Exception as e:
            logger.error(f"Error preprocessing data: {e}")
            return np.array([])
    
    def detect_anomalies_isolation_forest(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Detect anomalies using Isolation Forest"""
        try:
            if len(X) == 0:
                return np.array([]), np.array([])
            
            # Fit model and predict
            predictions = self.models['isolation_forest'].fit_predict(X)
            scores = self.models['isolation_forest'].decision_function(X)
            
            # Convert predictions to binary (1 = normal, -1 = anomaly)
            anomalies = predictions == -1
            
            return anomalies, scores
            
        except Exception as e:
            logger.error(f"Error in Isolation Forest detection: {e}")
            return np.array([]), np.array([])
    
    def detect_anomalies_statistical(self, df: pd.DataFrame) -> List[Dict]:
        """Detect anomalies using statistical methods"""
        try:
            anomalies = []
            
            for _, row in df.iterrows():
                values = [float(val[1]) for val in row['values'] if val[1] != 'NaN']
                
                if len(values) < 10:
                    continue
                
                # Calculate statistical thresholds
                mean_val = np.mean(values)
                std_val = np.std(values)
                threshold = mean_val + 3 * std_val
                
                # Check for anomalies
                recent_values = values[-10:]  # Last 10 data points
                for i, val in enumerate(recent_values):
                    if val > threshold:
                        anomaly = {
                            'metric_name': row['metric_name'],
                            'labels': row['labels'],
                            'value': val,
                            'threshold': threshold,
                            'timestamp': datetime.now().isoformat(),
                            'method': 'statistical',
                            'severity': 'high' if val > threshold * 1.5 else 'medium'
                        }
                        anomalies.append(anomaly)
            
            return anomalies
            
        except Exception as e:
            logger.error(f"Error in statistical anomaly detection: {e}")
            return []
    
    def detect_anomalies(self) -> List[Dict]:
        """Main anomaly detection method"""
        start_time = time.time()
        
        try:
            logger.info("Starting anomaly detection cycle")
            
            # Collect metrics
            df = self.collect_metrics()
            if df.empty:
                logger.warning("No metrics collected")
                return []
            
            # Preprocess data
            X = self.preprocess_data(df)
            if len(X) == 0:
                logger.warning("No valid data after preprocessing")
                return []
            
            anomalies = []
            
            # Isolation Forest detection
            if_anomalies, if_scores = self.detect_anomalies_isolation_forest(X)
            
            for i, (is_anomaly, score) in enumerate(zip(if_anomalies, if_scores)):
                if is_anomaly and i < len(df):
                    anomaly = {
                        'metric_name': df.iloc[i]['metric_name'],
                        'labels': df.iloc[i]['labels'],
                        'score': score,
                        'timestamp': datetime.now().isoformat(),
                        'method': 'isolation_forest',
                        'severity': 'high' if score < -0.5 else 'medium'
                    }
                    anomalies.append(anomaly)
                    self.anomaly_counter.labels(
                        model='isolation_forest',
                        severity=anomaly['severity'],
                        metric_type=anomaly['metric_name']
                    ).inc()
            
            # Statistical detection
            stat_anomalies = self.detect_anomalies_statistical(df)
            anomalies.extend(stat_anomalies)
            
            for anomaly in stat_anomalies:
                self.anomaly_counter.labels(
                    model='statistical',
                    severity=anomaly['severity'],
                    metric_type=anomaly['metric_name']
                ).inc()
            
            # Store anomalies
            self.anomaly_history.extend(anomalies)
            
            # Update metrics
            detection_time = time.time() - start_time
            self.detection_latency.observe(detection_time)
            
            logger.info(f"Detected {len(anomalies)} anomalies in {detection_time:.2f}s")
            
            return anomalies
            
        except Exception as e:
            logger.error(f"Error in anomaly detection: {e}")
            return []
    
    def generate_alert(self, anomaly: Dict) -> Dict:
        """Generate alert for anomaly"""
        try:
            alert = {
                'alert_name': f"Anomaly Detected - {anomaly['metric_name']}",
                'severity': anomaly['severity'],
                'status': 'firing',
                'timestamp': anomaly['timestamp'],
                'labels': {
                    'metric_name': anomaly['metric_name'],
                    'method': anomaly['method'],
                    'service': anomaly['labels'].get('instance', 'unknown')
                },
                'annotations': {
                    'summary': f"Anomaly detected in {anomaly['metric_name']}",
                    'description': f"Method: {anomaly['method']}, Score: {anomaly.get('score', 'N/A')}, Severity: {anomaly['severity']}"
                }
            }
            
            return alert
            
        except Exception as e:
            logger.error(f"Error generating alert: {e}")
            return {}
    
    def save_models(self):
        """Save trained models"""
        try:
            joblib.dump(self.models['isolation_forest'], 'models/isolation_forest.pkl')
            joblib.dump(self.scalers['standard'], 'models/scaler.pkl')
            logger.info("Models saved successfully")
            
        except Exception as e:
            logger.error(f"Error saving models: {e}")
    
    def load_models(self):
        """Load pre-trained models"""
        try:
            self.models['isolation_forest'] = joblib.load('models/isolation_forest.pkl')
            self.scalers['standard'] = joblib.load('models/scaler.pkl')
            logger.info("Models loaded successfully")
            
        except FileNotFoundError:
            logger.info("No pre-trained models found, using new models")
        except Exception as e:
            logger.error(f"Error loading models: {e}")
    
    def get_anomaly_summary(self) -> Dict:
        """Get summary of recent anomalies"""
        try:
            if not self.anomaly_history:
                return {"total_anomalies": 0, "recent_anomalies": []}
            
            # Get anomalies from last hour
            one_hour_ago = datetime.now() - timedelta(hours=1)
            recent_anomalies = [
                a for a in self.anomaly_history 
                if datetime.fromisoformat(a['timestamp']) > one_hour_ago
            ]
            
            # Group by severity
            severity_counts = {}
            for anomaly in recent_anomalies:
                severity = anomaly['severity']
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            summary = {
                "total_anomalies": len(self.anomaly_history),
                "recent_anomalies": len(recent_anomalies),
                "severity_breakdown": severity_counts,
                "methods": list(set(a['method'] for a in recent_anomalies)),
                "top_metrics": self.get_top_anomaly_metrics(recent_anomalies)
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating anomaly summary: {e}")
            return {}
    
    def get_top_anomaly_metrics(self, anomalies: List[Dict]) -> List[Dict]:
        """Get metrics with most anomalies"""
        try:
            metric_counts = {}
            for anomaly in anomalies:
                metric = anomaly['metric_name']
                metric_counts[metric] = metric_counts.get(metric, 0) + 1
            
            top_metrics = sorted(metric_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            return [{"metric": metric, "count": count} for metric, count in top_metrics]
            
        except Exception as e:
            logger.error(f"Error getting top anomaly metrics: {e}")
            return []
    
    def run_detection_cycle(self):
        """Run one complete detection cycle"""
        try:
            anomalies = self.detect_anomalies()
            
            # Generate alerts for high severity anomalies
            for anomaly in anomalies:
                if anomaly['severity'] == 'high':
                    alert = self.generate_alert(anomaly)
                    logger.warning(f"ALERT: {json.dumps(alert, indent=2)}")
            
            return anomalies
            
        except Exception as e:
            logger.error(f"Error in detection cycle: {e}")
            return []
    
    def start_continuous_detection(self):
        """Start continuous anomaly detection"""
        logger.info("Starting continuous anomaly detection")
        
        # Schedule detection every 5 minutes
        schedule.every(5).minutes.do(self.run_detection_cycle)
        
        # Run initial detection
        self.run_detection_cycle()
        
        # Keep the scheduler running
        while True:
            schedule.run_pending()
            time.sleep(1)

def main():
    """Main function"""
    logger.info("Starting AI Anomaly Detection Service...")
    
    # Initialize anomaly detector
    detector = AnomalyDetector()
    
    # Try to load existing models
    detector.load_models()
    
    # Start metrics server
    start_http_server(8003)
    logger.info("Metrics server started on port 8003")
    
    # Start continuous detection
    try:
        detector.start_continuous_detection()
    except KeyboardInterrupt:
        logger.info("Shutting down anomaly detector...")
        detector.save_models()

if __name__ == "__main__":
    main()
