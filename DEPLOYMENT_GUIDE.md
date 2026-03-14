# Deployment Guide - Edge AI Reliability Monitor

## Overview

This guide provides step-by-step instructions for deploying the Edge AI Reliability Monitor on Kubernetes. The system demonstrates cloud-native observability and AI-assisted anomaly detection for telecom-style workloads.

## Prerequisites

### Required Tools
- **Kubernetes** (v1.24+)
- **Docker** (v20.10+)
- **kubectl** (configured to access your cluster)
- **Helm** (optional, for advanced deployments)

### Resource Requirements
- **CPU**: 4+ cores
- **Memory**: 8GB+ RAM
- **Storage**: 20GB+ persistent storage
- **Network**: ClusterIP and LoadBalancer support

## Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/harishgedi/edge-ai-reliability-monitor
cd edge-ai-reliability-monitor
```

### 2. Deploy Entire Stack
```bash
# Using the deployment script (recommended)
./scripts/deploy.sh

# Or manual deployment
kubectl create namespace edge-ai-monitor
kubectl apply -f monitoring/prometheus/
kubectl apply -f monitoring/grafana/
kubectl apply -f k8s/
```

### 3. Verify Deployment
```bash
./scripts/deploy.sh verify
```

### 4. Access Services
```bash
# Grafana Dashboard
kubectl port-forward -n edge-ai-monitor svc/grafana 3000:3000
# Open: http://localhost:3000 (admin/admin)

# Prometheus
kubectl port-forward -n edge-ai-monitor svc/prometheus 9090:9090
# Open: http://localhost:9090

# API Service
kubectl port-forward -n edge-ai-monitor svc/api-service 8000:8000
# Open: http://localhost:8000
```

## Detailed Deployment Steps

### Step 1: Environment Setup

#### Local Development (Minikube)
```bash
# Start Minikube
minikube start --cpus=4 --memory=8192 --disk-size=20g

# Enable required addons
minikube addons enable metrics-server
minikube addons enable ingress

# Set Docker environment
eval $(minikube docker-env)
```

#### Cloud Provider Setup
```bash
# For GKE
gcloud container clusters create edge-ai-monitor \
  --num-nodes=3 \
  --machine-type=e2-standard-4 \
  --enable-autoscaling \
  --min-nodes=1 \
  --max-nodes=5

# For EKS
eksctl create cluster --name edge-ai-monitor \
  --nodegroup-name standard-workers \
  --node-type t3.large \
  --nodes 3 \
  --nodes-min 1 \
  --nodes-max 5

# For AKS
az group create --name edge-ai-monitor-rg --location eastus
az aks create --resource-group edge-ai-monitor-rg \
  --name edge-ai-monitor \
  --node-count 3 \
  --node-vm-size Standard_D4s_v3 \
  --enable-cluster-autoscaler \
  --min-count 1 \
  --max-count 5
```

### Step 2: Build and Push Images

#### Build Images Locally
```bash
./scripts/deploy.sh build
```

#### Push to Registry
```bash
# For Docker Hub
docker tag edge-ai-monitor/api-service:latest yourusername/api-service:latest
docker push yourusername/api-service:latest

# Update image references in k8s/ manifests
sed -i 's|edge-ai-monitor/|yourusername/|g' k8s/*.yaml
```

#### Using GitHub Container Registry
```bash
# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_ACTOR --password-stdin

# Images are automatically built and pushed by GitHub Actions
```

### Step 3: Deploy Monitoring Stack

#### Deploy Prometheus
```bash
kubectl apply -f monitoring/prometheus/
kubectl wait --for=condition=available --timeout=300s deployment/prometheus -n edge-ai-monitor
```

#### Deploy Grafana
```bash
kubectl apply -f monitoring/grafana/
kubectl wait --for=condition=available --timeout=300s deployment/grafana -n edge-ai-monitor
```

#### Verify Monitoring
```bash
kubectl get pods -n edge-ai-monitor
kubectl get services -n edge-ai-monitor
```

### Step 4: Deploy Application Services

#### Deploy Secrets
```bash
kubectl apply -f k8s/secrets.yaml
```

#### Deploy Services
```bash
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/auth-service.yaml
kubectl apply -f k8s/telemetry-service.yaml
kubectl apply -f k8s/load-generator.yaml
```

#### Deploy Anomaly Detector
```bash
kubectl apply -f k8s/anomaly-detector.yaml
```

### Step 5: Configure Access

#### External Access (Ingress)
```yaml
# Create ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: edge-ai-monitor-ingress
  namespace: edge-ai-monitor
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: edge-ai-monitor.example.com
    http:
      paths:
      - path: /grafana
        pathType: Prefix
        backend:
          service:
            name: grafana
            port:
              number: 3000
      - path: /prometheus
        pathType: Prefix
        backend:
          service:
            name: prometheus
            port:
              number: 9090
```

#### LoadBalancer Services
```bash
# Expose Grafana via LoadBalancer
kubectl patch svc grafana -n edge-ai-monitor -p '{"spec":{"type":"LoadBalancer"}}'

# Get external IP
kubectl get svc grafana -n edge-ai-monitor
```

## Configuration

### Environment Variables

#### API Service
- `PORT`: Service port (default: 8000)
- `LOG_LEVEL`: Logging level (default: INFO)

#### Auth Service
- `PORT`: Service port (default: 3001)
- `JWT_SECRET`: JWT signing secret
- `NODE_ENV`: Environment (default: production)

#### Telemetry Generator
- `LOG_LEVEL`: Logging level (default: INFO)
- `GENERATION_INTERVAL`: Metrics generation interval in seconds (default: 10)

#### Anomaly Detector
- `PROMETHEUS_URL`: Prometheus server URL (default: http://prometheus:9090)
- `LOG_LEVEL`: Logging level (default: INFO)

### Customization

#### Modify Metrics Collection
Edit `services/telemetry-generator/telemetry_generator.py` to customize:
- Metric types and frequencies
- Anomaly injection patterns
- Base station simulation

#### Adjust Anomaly Detection
Edit `ai/anomaly_detector.py` to modify:
- Detection algorithms
- Thresholds and sensitivity
- Alerting rules

#### Update Grafana Dashboards
1. Access Grafana at http://localhost:3000
2. Import dashboard configurations
3. Customize panels and alerts

## Testing

### Run All Tests
```bash
./scripts/run-tests.sh all
```

### Individual Tests
```bash
./scripts/run-tests.sh cpu      # CPU spike test
./scripts/run-tests.sh crash    # Crash loop test
./scripts/run-tests.sh latency  # Latency spike test
./scripts/run-tests.sh traffic  # Traffic burst test
```

### Test Results
Test results are saved in the `test-results/` directory:
- `test_summary.csv`: Overall test summary
- `test_report_*.md`: Detailed test report
- Individual test logs and metrics

## Monitoring and Maintenance

### Health Checks
```bash
# Check all pods
kubectl get pods -n edge-ai-monitor

# Check services
kubectl get services -n edge-ai-monitor

# Check resource usage
kubectl top pods -n edge-ai-monitor
```

### Logs
```bash
# API Service logs
kubectl logs -n edge-ai-monitor deployment/api-service -f

# Anomaly Detector logs
kubectl logs -n edge-ai-monitor deployment/anomaly-detector -f

# All services logs
kubectl logs -n edge-ai-monitor -l app=api-service -f
```

### Scaling
```bash
# Scale API service
kubectl scale deployment api-service --replicas=3 -n edge-ai-monitor

# Enable autoscaling
kubectl autoscale deployment api-service --cpu-percent=70 --min=2 --max=10 -n edge-ai-monitor
```

### Updates
```bash
# Update images
kubectl set image deployment/api-service api-service=edge-ai-monitor/api-service:v2.0.0 -n edge-ai-monitor

# Rolling restart
kubectl rollout restart deployment/api-service -n edge-ai-monitor

# Check rollout status
kubectl rollout status deployment/api-service -n edge-ai-monitor
```

## Troubleshooting

### Common Issues

#### Pods Not Starting
```bash
# Check pod status
kubectl describe pod <pod-name> -n edge-ai-monitor

# Check events
kubectl get events -n edge-ai-monitor --sort-by='.lastTimestamp'
```

#### Service Not Accessible
```bash
# Check service endpoints
kubectl get endpoints -n edge-ai-monitor

# Test pod connectivity
kubectl exec -it <pod-name> -n edge-ai-monitor -- curl http://service-name:port
```

#### High Resource Usage
```bash
# Check resource limits
kubectl describe pod <pod-name> -n edge-ai-monitor

# Monitor resource usage
kubectl top nodes
kubectl top pods -n edge-ai-monitor
```

#### Anomaly Detection Not Working
```bash
# Check Prometheus connectivity
kubectl exec -it deployment/anomaly-detector -n edge-ai-monitor -- curl http://prometheus:9090/api/v1/query?query=up

# Check anomaly detector logs
kubectl logs deployment/anomaly-detector -n edge-ai-monitor
```

### Performance Tuning

#### Resource Allocation
Adjust resource requests and limits in deployment manifests based on usage patterns.

#### Prometheus Configuration
Modify `monitoring/prometheus/configmap.yaml` to optimize:
- Scrape intervals
- Retention periods
- Storage limits

#### Anomaly Detection Sensitivity
Tune parameters in `ai/anomaly_detector.py`:
- `contamination` parameter in IsolationForest
- Statistical thresholds
- Detection intervals

## Security Considerations

### Network Policies
```yaml
# Example network policy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: edge-ai-monitor-netpol
  namespace: edge-ai-monitor
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: edge-ai-monitor
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: edge-ai-monitor
```

### RBAC
The deployment includes appropriate RBAC configurations for Prometheus and other components.

### Secrets Management
- Use Kubernetes secrets for sensitive data
- Rotate secrets regularly
- Consider external secret management tools

## Backup and Recovery

### Backup Persistent Data
```bash
# Backup Prometheus data
kubectl exec -it prometheus-0 -n edge-ai-monitor -- tar czf /tmp/prometheus-backup.tar.gz /prometheus

# Backup Grafana data
kubectl exec -it deployment/grafana -n edge-ai-monitor -- tar czf /tmp/grafana-backup.tar.gz /var/lib/grafana
```

### Disaster Recovery
1. Re-deploy from manifests
2. Restore persistent volumes
3. Import Grafana dashboards
4. Verify monitoring and alerting

## Support

For issues and questions:
1. Check this deployment guide
2. Review test results and logs
3. Consult the main README.md
4. Create an issue in the GitHub repository

## Next Steps

After successful deployment:
1. Explore the Grafana dashboards
2. Run the fault injection tests
3. Customize metrics and alerts
4. Integrate with your existing monitoring stack
5. Extend the anomaly detection models
