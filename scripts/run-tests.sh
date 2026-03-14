#!/bin/bash

# Edge AI Reliability Monitor Test Runner
# This script runs all fault injection tests and validates results

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="edge-ai-monitor"
TEST_RESULTS_DIR="test-results"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

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

setup_test_environment() {
    log_info "Setting up test environment..."
    
    # Create test results directory
    mkdir -p $TEST_RESULTS_DIR
    
    # Check if namespace exists
    if ! kubectl get namespace $NAMESPACE &> /dev/null; then
        log_error "Namespace $NAMESPACE does not exist. Please deploy the application first."
        exit 1
    fi
    
    log_success "Test environment setup completed"
}

run_cpu_spike_test() {
    log_info "Running CPU Spike Test..."
    
    TEST_NAME="cpu-spike"
    TEST_START_TIME=$(date +%s)
    
    # Get baseline metrics
    log_info "Collecting baseline metrics..."
    kubectl top pods -n $NAMESPACE > $TEST_RESULTS_DIR/${TEST_NAME}_baseline.txt
    
    # Deploy CPU stress test
    log_info "Deploying CPU stress test..."
    kubectl apply -f tests/cpu-spike.yaml -n $NAMESPACE
    
    # Wait for stress test to start
    sleep 30
    
    # Monitor CPU usage during test
    log_info "Monitoring CPU usage..."
    for i in {1..12}; do
        kubectl top pods -n $NAMESPACE >> $TEST_RESULTS_DIR/${TEST_NAME}_during.txt
        sleep 10
    done
    
    # Check if anomalies were detected
    log_info "Checking for detected anomalies..."
    kubectl logs -n $NAMESPACE deployment/anomaly-detector --tail=50 > $TEST_RESULTS_DIR/${TEST_NAME}_anomalies.txt
    
    # Cleanup
    log_info "Cleaning up CPU stress test..."
    kubectl delete -f tests/cpu-spike.yaml -n $NAMESPACE --ignore-not-found
    
    TEST_END_TIME=$(date +%s)
    TEST_DURATION=$((TEST_END_TIME - TEST_START_TIME))
    
    # Evaluate test results
    if grep -q "CPU" $TEST_RESULTS_DIR/${TEST_NAME}_anomalies.txt; then
        log_success "CPU Spike Test PASSED - Anomalies detected"
        echo "PASS,CPU Spike,$TEST_DURATION,Anomalies detected" >> $TEST_RESULTS_DIR/test_summary.csv
    else
        log_warning "CPU Spike Test INCONCLUSIVE - No anomalies detected"
        echo "INCONCLUSIVE,CPU Spike,$TEST_DURATION,No anomalies detected" >> $TEST_RESULTS_DIR/test_summary.csv
    fi
}

run_crash_loop_test() {
    log_info "Running Crash Loop Test..."
    
    TEST_NAME="crash-loop"
    TEST_START_TIME=$(date +%s)
    
    # Deploy crash loop test
    log_info "Deploying crash loop test..."
    kubectl apply -f tests/crash-loop.yaml -n $NAMESPACE
    
    # Wait for crash loops to occur
    log_info "Waiting for crash loops to be detected..."
    sleep 90
    
    # Check pod restart counts
    log_info "Checking pod restart counts..."
    kubectl get pods -n $NAMESPACE -l test-type=fault-injection > $TEST_RESULTS_DIR/${TEST_NAME}_pods.txt
    
    # Check for anomaly detection
    log_info "Checking for detected anomalies..."
    kubectl logs -n $NAMESPACE deployment/anomaly-detector --tail=50 > $TEST_RESULTS_DIR/${TEST_NAME}_anomalies.txt
    
    # Get events
    kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' > $TEST_RESULTS_DIR/${TEST_NAME}_events.txt
    
    # Cleanup
    log_info "Cleaning up crash loop test..."
    kubectl delete -f tests/crash-loop.yaml -n $NAMESPACE --ignore-not-found
    
    TEST_END_TIME=$(date +%s)
    TEST_DURATION=$((TEST_END_TIME - TEST_START_TIME))
    
    # Evaluate test results
    if grep -q "restart\|crash\|error" $TEST_RESULTS_DIR/${TEST_NAME}_pods.txt; then
        log_success "Crash Loop Test PASSED - Restart events detected"
        echo "PASS,Crash Loop,$TEST_DURATION,Restart events detected" >> $TEST_RESULTS_DIR/test_summary.csv
    else
        log_warning "Crash Loop Test INCONCLUSIVE - No restart events detected"
        echo "INCONCLUSIVE,Crash Loop,$TEST_DURATION,No restart events detected" >> $TEST_RESULTS_DIR/test_summary.csv
    fi
}

run_latency_spike_test() {
    log_info "Running Latency Spike Test..."
    
    TEST_NAME="latency-spike"
    TEST_START_TIME=$(date +%s)
    
    # Get baseline latency metrics
    log_info "Collecting baseline latency metrics..."
    kubectl port-forward -n $NAMESPACE svc/prometheus 9090:9090 &
    PROM_PID=$!
    sleep 10
    
    curl -s "http://localhost:9090/api/v1/query?query=api_request_duration_seconds" > $TEST_RESULTS_DIR/${TEST_NAME}_baseline_latency.json
    
    # Deploy latency test
    log_info "Deploying latency spike test..."
    kubectl apply -f tests/latency-spike.yaml -n $NAMESPACE
    
    # Wait for latency injection
    sleep 60
    
    # Monitor latency during test
    log_info "Monitoring latency during test..."
    for i in {1..6}; do
        curl -s "http://localhost:9090/api/v1/query?query=api_request_duration_seconds" >> $TEST_RESULTS_DIR/${TEST_NAME}_during_latency.json
        sleep 20
    done
    
    # Check for anomaly detection
    log_info "Checking for detected anomalies..."
    kubectl logs -n $NAMESPACE deployment/anomaly-detector --tail=50 > $TEST_RESULTS_DIR/${TEST_NAME}_anomalies.txt
    
    # Cleanup
    log_info "Cleaning up latency spike test..."
    kubectl delete -f tests/latency-spike.yaml -n $NAMESPACE --ignore-not-found
    kill $PROM_PID 2>/dev/null || true
    
    TEST_END_TIME=$(date +%s)
    TEST_DURATION=$((TEST_END_TIME - TEST_START_TIME))
    
    # Evaluate test results
    if grep -q "latency\|response_time" $TEST_RESULTS_DIR/${TEST_NAME}_anomalies.txt; then
        log_success "Latency Spike Test PASSED - Latency anomalies detected"
        echo "PASS,Latency Spike,$TEST_DURATION,Latency anomalies detected" >> $TEST_RESULTS_DIR/test_summary.csv
    else
        log_warning "Latency Spike Test INCONCLUSIVE - No latency anomalies detected"
        echo "INCONCLUSIVE,Latency Spike,$TEST_DURATION,No latency anomalies detected" >> $TEST_RESULTS_DIR/test_summary.csv
    fi
}

run_traffic_burst_test() {
    log_info "Running Traffic Burst Test..."
    
    TEST_NAME="traffic-burst"
    TEST_START_TIME=$(date +%s)
    
    # Get baseline metrics
    log_info "Collecting baseline metrics..."
    kubectl get hpa -n $NAMESPACE > $TEST_RESULTS_DIR/${TEST_NAME}_baseline_hpa.txt
    kubectl top pods -n $NAMESPACE > $TEST_RESULTS_DIR/${TEST_NAME}_baseline_pods.txt
    
    # Deploy traffic burst test
    log_info "Deploying traffic burst test..."
    kubectl apply -f tests/traffic-burst.yaml -n $NAMESPACE
    
    # Wait for traffic burst and autoscaling
    log_info "Waiting for traffic burst and autoscaling..."
    for i in {1..18}; do
        kubectl get hpa -n $NAMESPACE >> $TEST_RESULTS_DIR/${TEST_NAME}_hpa_during.txt
        kubectl get pods -n $NAMESPACE >> $TEST_RESULTS_DIR/${TEST_NAME}_pods_during.txt
        sleep 10
    done
    
    # Check for anomaly detection
    log_info "Checking for detected anomalies..."
    kubectl logs -n $NAMESPACE deployment/anomaly-detector --tail=50 > $TEST_RESULTS_DIR/${TEST_NAME}_anomalies.txt
    
    # Cleanup
    log_info "Cleaning up traffic burst test..."
    kubectl delete -f tests/traffic-burst.yaml -n $NAMESPACE --ignore-not-found
    
    TEST_END_TIME=$(date +%s)
    TEST_DURATION=$((TEST_END_TIME - TEST_START_TIME))
    
    # Evaluate test results
    if grep -q "scale\|replicas\|traffic" $TEST_RESULTS_DIR/${TEST_NAME}_hpa_during.txt; then
        log_success "Traffic Burst Test PASSED - Autoscaling triggered"
        echo "PASS,Traffic Burst,$TEST_DURATION,Autoscaling triggered" >> $TEST_RESULTS_DIR/test_summary.csv
    else
        log_warning "Traffic Burst Test INCONCLUSIVE - No autoscaling detected"
        echo "INCONCLUSIVE,Traffic Burst,$TEST_DURATION,No autoscaling detected" >> $TEST_RESULTS_DIR/test_summary.csv
    fi
}

generate_test_report() {
    log_info "Generating test report..."
    
    REPORT_FILE="$TEST_RESULTS_DIR/test_report_$TIMESTAMP.md"
    
    cat > $REPORT_FILE << EOF
# Edge AI Reliability Monitor - Test Report

**Generated:** $(date)
**Namespace:** $NAMESPACE

## Test Summary

| Test | Status | Duration | Notes |
|------|--------|----------|-------|
EOF
    
    # Add test results to report
    while IFS=',' read -r status test duration notes; do
        echo "| $test | $status | ${duration}s | $notes |" >> $REPORT_FILE
    done < $TEST_RESULTS_DIR/test_summary.csv
    
    cat >> $REPORT_FILE << EOF

## Detailed Results

### CPU Spike Test
- Baseline metrics: [${TEST_NAME}_baseline.txt](${TEST_NAME}_baseline.txt)
- During test: [${TEST_NAME}_during.txt](${TEST_NAME}_during.txt)
- Anomalies detected: [${TEST_NAME}_anomalies.txt](${TEST_NAME}_anomalies.txt)

### Crash Loop Test
- Pod status: [${TEST_NAME}_pods.txt](${TEST_NAME}_pods.txt)
- Events: [${TEST_NAME}_events.txt](${TEST_NAME}_events.txt)
- Anomalies detected: [${TEST_NAME}_anomalies.txt](${TEST_NAME}_anomalies.txt)

### Latency Spike Test
- Baseline latency: [${TEST_NAME}_baseline_latency.json](${TEST_NAME}_baseline_latency.json)
- During test: [${TEST_NAME}_during_latency.json](${TEST_NAME}_during_latency.json)
- Anomalies detected: [${TEST_NAME}_anomalies.txt](${TEST_NAME}_anomalies.txt)

### Traffic Burst Test
- Baseline HPA: [${TEST_NAME}_baseline_hpa.txt](${TEST_NAME}_baseline_hpa.txt)
- HPA during test: [${TEST_NAME}_hpa_during.txt](${TEST_NAME}_hpa_during.txt)
- Pods during test: [${TEST_NAME}_pods_during.txt](${TEST_NAME}_pods_during.txt)
- Anomalies detected: [${TEST_NAME}_anomalies.txt](${TEST_NAME}_anomalies.txt)

## Recommendations

EOF
    
    # Add recommendations based on test results
    PASSED_TESTS=$(grep -c "PASS" $TEST_RESULTS_DIR/test_summary.csv || echo "0")
    TOTAL_TESTS=$(wc -l < $TEST_RESULTS_DIR/test_summary.csv)
    
    if [ "$PASSED_TESTS" -eq "$TOTAL_TESTS" ]; then
        echo "✅ All tests passed! The system is working as expected." >> $REPORT_FILE
    elif [ "$PASSED_TESTS" -gt 0 ]; then
        echo "⚠️  Some tests passed. Review the failed tests for potential issues." >> $REPORT_FILE
    else
        echo "❌ No tests passed. The system may need configuration adjustments." >> $REPORT_FILE
    fi
    
    log_success "Test report generated: $REPORT_FILE"
}

main() {
    case "${1:-all}" in
        "all")
            setup_test_environment
            
            # Initialize test summary
            echo "Test,Status,Duration,Notes" > $TEST_RESULTS_DIR/test_summary.csv
            
            run_cpu_spike_test
            sleep 30
            
            run_crash_loop_test
            sleep 30
            
            run_latency_spike_test
            sleep 30
            
            run_traffic_burst_test
            
            generate_test_report
            
            log_success "All tests completed!"
            ;;
        "cpu")
            setup_test_environment
            echo "Test,Status,Duration,Notes" > $TEST_RESULTS_DIR/test_summary.csv
            run_cpu_spike_test
            ;;
        "crash")
            setup_test_environment
            echo "Test,Status,Duration,Notes" > $TEST_RESULTS_DIR/test_summary.csv
            run_crash_loop_test
            ;;
        "latency")
            setup_test_environment
            echo "Test,Status,Duration,Notes" > $TEST_RESULTS_DIR/test_summary.csv
            run_latency_spike_test
            ;;
        "traffic")
            setup_test_environment
            echo "Test,Status,Duration,Notes" > $TEST_RESULTS_DIR/test_summary.csv
            run_traffic_burst_test
            ;;
        "report")
            generate_test_report
            ;;
        "help"|"-h"|"--help")
            echo "Usage: $0 [test_type]"
            echo ""
            echo "Test types:"
            echo "  all      - Run all tests (default)"
            echo "  cpu      - Run CPU spike test only"
            echo "  crash    - Run crash loop test only"
            echo "  latency  - Run latency spike test only"
            echo "  traffic  - Run traffic burst test only"
            echo "  report   - Generate test report only"
            echo "  help     - Show this help message"
            ;;
        *)
            log_error "Unknown test type: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
