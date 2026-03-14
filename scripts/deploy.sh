#!/bin/bash

# Edge AI Reliability Monitor Deployment Script
# This script deploys the entire monitoring stack to Kubernetes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="edge-ai-monitor"
DOCKER_REGISTRY="edge-ai-monitor"
VERSION="latest"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Please install kubectl first."
        exit 1
    fi
    
    # Check if docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check if cluster is accessible
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

create_namespace() {
    log_info "Creating namespace: $NAMESPACE"
    
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    log_success "Namespace created/verified"
}

build_images() {
    log_info "Building Docker images..."
    
    # Build API service image
    log_info "Building API service image..."
    docker build -t $DOCKER_REGISTRY/api-service:$VERSION ./services/api-service/
    
    # Build auth service image
    log_info "Building auth service image..."
    docker build -t $DOCKER_REGISTRY/auth-service:$VERSION ./services/auth-service/
    
    # Build telemetry generator image
    log_info "Building telemetry generator image..."
    docker build -t $DOCKER_REGISTRY/telemetry-generator:$VERSION ./services/telemetry-generator/
    
    # Build load generator image
    log_info "Building load generator image..."
    docker build -t $DOCKER_REGISTRY/load-generator:$VERSION ./services/load-generator/
    
    # Build anomaly detector image
    log_info "Building anomaly detector image..."
    docker build -t $DOCKER_REGISTRY/anomaly-detector:$VERSION ./ai/
    
    log_success "All images built successfully"
}

push_images() {
    log_info "Pushing Docker images to registry..."
    
    # Push API service image
    docker push $DOCKER_REGISTRY/api-service:$VERSION
    
    # Push auth service image
    docker push $DOCKER_REGISTRY/auth-service:$VERSION
    
    # Push telemetry generator image
    docker push $DOCKER_REGISTRY/telemetry-generator:$VERSION
    
    # Push load generator image
    docker push $DOCKER_REGISTRY/load-generator:$VERSION
    
    # Push anomaly detector image
    docker push $DOCKER_REGISTRY/anomaly-detector:$VERSION
    
    log_success "All images pushed successfully"
}

deploy_monitoring() {
    log_info "Deploying monitoring stack..."
    
    # Deploy Prometheus
    log_info "Deploying Prometheus..."
    kubectl apply -f monitoring/prometheus/ -n $NAMESPACE
    
    # Wait for Prometheus to be ready
    kubectl wait --for=condition=available --timeout=300s deployment/prometheus -n $NAMESPACE
    
    # Deploy Grafana
    log_info "Deploying Grafana..."
    kubectl apply -f monitoring/grafana/ -n $NAMESPACE
    
    # Wait for Grafana to be ready
    kubectl wait --for=condition=available --timeout=300s deployment/grafana -n $NAMESPACE
    
    log_success "Monitoring stack deployed successfully"
}

deploy_applications() {
    log_info "Deploying application services..."
    
    # Deploy secrets
    log_info "Deploying secrets..."
    kubectl apply -f k8s/secrets.yaml -n $NAMESPACE
    
    # Deploy services
    log_info "Deploying API service..."
    kubectl apply -f k8s/api-service.yaml -n $NAMESPACE
    
    log_info "Deploying auth service..."
    kubectl apply -f k8s/auth-service.yaml -n $NAMESPACE
    
    log_info "Deploying telemetry generator..."
    kubectl apply -f k8s/telemetry-service.yaml -n $NAMESPACE
    
    log_info "Deploying load generator..."
    kubectl apply -f k8s/load-generator.yaml -n $NAMESPACE
    
    # Wait for all deployments to be ready
    log_info "Waiting for all deployments to be ready..."
    kubectl wait --for=condition=available --timeout=600s deployment --all -n $NAMESPACE
    
    log_success "Application services deployed successfully"
}

deploy_anomaly_detector() {
    log_info "Deploying anomaly detection service..."
    
    # Create anomaly detector deployment
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: anomaly-detector
  namespace: $NAMESPACE
  labels:
    app: anomaly-detector
    component: ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: anomaly-detector
  template:
    metadata:
      labels:
        app: anomaly-detector
        component: ai
    spec:
      containers:
      - name: anomaly-detector
        image: $DOCKER_REGISTRY/anomaly-detector:$VERSION
        ports:
        - containerPort: 8003
          name: http
        env:
        - name: PROMETHEUS_URL
          value: "http://prometheus:9090"
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            memory: "512Mi"
            cpu: "300m"
          limits:
            memory: "1024Mi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /
            port: 8003
          initialDelaySeconds: 60
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /
            port: 8003
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: anomaly-detector
  namespace: $NAMESPACE
  labels:
    app: anomaly-detector
    component: ai
spec:
  selector:
    app: anomaly-detector
  ports:
  - name: http
    port: 8003
    targetPort: 8003
    protocol: TCP
  type: ClusterIP
EOF
    
    # Wait for anomaly detector to be ready
    kubectl wait --for=condition=available --timeout=300s deployment/anomaly-detector -n $NAMESPACE
    
    log_success "Anomaly detector deployed successfully"
}

verify_deployment() {
    log_info "Verifying deployment..."
    
    # Check all pods are running
    log_info "Checking pod status..."
    kubectl get pods -n $NAMESPACE
    
    # Check all services
    log_info "Checking services..."
    kubectl get services -n $NAMESPACE
    
    # Check deployments
    log_info "Checking deployments..."
    kubectl get deployments -n $NAMESPACE
    
    # Test API endpoints
    log_info "Testing API endpoints..."
    
    # Port forward API service
    kubectl port-forward -n $NAMESPACE svc/api-service 8000:8000 &
    API_PID=$!
    sleep 10
    
    # Test API health
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        log_success "API service health check passed"
    else
        log_error "API service health check failed"
    fi
    
    # Kill port forward
    kill $API_PID 2>/dev/null || true
    
    # Test auth service
    kubectl port-forward -n $NAMESPACE svc/auth-service 3001:3001 &
    AUTH_PID=$!
    sleep 10
    
    # Test auth health
    if curl -f http://localhost:3001/health > /dev/null 2>&1; then
        log_success "Auth service health check passed"
    else
        log_error "Auth service health check failed"
    fi
    
    # Kill port forward
    kill $AUTH_PID 2>/dev/null || true
    
    log_success "Deployment verification completed"
}

show_access_info() {
    log_info "Access Information:"
    echo ""
    echo "📊 Grafana Dashboard:"
    echo "   kubectl port-forward -n $NAMESPACE svc/grafana 3000:3000"
    echo "   Then open: http://localhost:3000 (admin/admin)"
    echo ""
    echo "📈 Prometheus:"
    echo "   kubectl port-forward -n $NAMESPACE svc/prometheus 9090:9090"
    echo "   Then open: http://localhost:9090"
    echo ""
    echo "🔍 API Service:"
    echo "   kubectl port-forward -n $NAMESPACE svc/api-service 8000:8000"
    echo "   Then open: http://localhost:8000"
    echo ""
    echo "🔐 Auth Service:"
    echo "   kubectl port-forward -n $NAMESPACE svc/auth-service 3001:3001"
    echo "   Then open: http://localhost:3001"
    echo ""
    echo "📡 Telemetry Generator:"
    echo "   kubectl port-forward -n $NAMESPACE svc/telemetry-generator 8001:8001"
    echo "   Then open: http://localhost:8001"
    echo ""
    echo "⚡ Load Generator:"
    echo "   kubectl port-forward -n $NAMESPACE svc/load-generator 8002:8002"
    echo "   Then open: http://localhost:8002"
    echo ""
    echo "🤖 Anomaly Detector:"
    echo "   kubectl port-forward -n $NAMESPACE svc/anomaly-detector 8003:8003"
    echo "   Then open: http://localhost:8003"
    echo ""
    echo "🧪 Run Tests:"
    echo "   kubectl apply -f tests/cpu-spike.yaml -n $NAMESPACE"
    echo "   kubectl apply -f tests/crash-loop.yaml -n $NAMESPACE"
    echo "   kubectl apply -f tests/latency-spike.yaml -n $NAMESPACE"
    echo "   kubectl apply -f tests/traffic-burst.yaml -n $NAMESPACE"
    echo ""
}

cleanup() {
    log_warning "Cleaning up deployment..."
    
    # Delete all resources
    kubectl delete namespace $NAMESPACE --ignore-not-found
    
    log_success "Cleanup completed"
}

# Main execution
main() {
    case "${1:-deploy}" in
        "deploy")
            check_prerequisites
            create_namespace
            build_images
            push_images
            deploy_monitoring
            deploy_applications
            deploy_anomaly_detector
            verify_deployment
            show_access_info
            ;;
        "build")
            check_prerequisites
            build_images
            ;;
        "push")
            check_prerequisites
            push_images
            ;;
        "monitoring")
            check_prerequisites
            create_namespace
            deploy_monitoring
            ;;
        "apps")
            check_prerequisites
            create_namespace
            deploy_applications
            ;;
        "verify")
            check_prerequisites
            verify_deployment
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|"-h"|"--help")
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  deploy    - Deploy the entire stack (default)"
            echo "  build     - Build Docker images only"
            echo "  push      - Push Docker images only"
            echo "  monitoring - Deploy monitoring stack only"
            echo "  apps      - Deploy application services only"
            echo "  verify    - Verify deployment health"
            echo "  cleanup   - Remove all deployed resources"
            echo "  help      - Show this help message"
            ;;
        *)
            log_error "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
