#!/bin/bash
# Deployment script for Actor Mesh Demo on Kubernetes
# This script deploys the complete Actor Mesh application to a Kubernetes cluster

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
NAMESPACE="actor-mesh"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ENVIRONMENT="${ENVIRONMENT:-development}"
REGISTRY_URL="${REGISTRY_URL:-localhost:5001}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300s}"

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    # Check if kubectl is available
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed or not in PATH"
        exit 1
    fi

    # Check if cluster is accessible
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster"
        print_error "Make sure your kubeconfig is set up correctly"
        exit 1
    fi

    # Check if the environment overlay exists
    if [ ! -d "k8s/overlays/${ENVIRONMENT}" ]; then
        print_warning "Environment overlay k8s/overlays/${ENVIRONMENT} not found"
        print_warning "Using base manifests only"
        ENVIRONMENT="base"
    fi

    print_success "Prerequisites check completed"
}

# Create namespace if it doesn't exist
create_namespace() {
    print_status "Creating namespace ${NAMESPACE}..."

    if kubectl get namespace ${NAMESPACE} &> /dev/null; then
        print_warning "Namespace ${NAMESPACE} already exists"
    else
        kubectl apply -f k8s/base/namespace.yaml
        print_success "Namespace ${NAMESPACE} created"
    fi
}

# Deploy infrastructure components
deploy_infrastructure() {
    print_status "Deploying infrastructure components..."

    # Deploy NATS
    print_status "Deploying NATS JetStream..."
    kubectl apply -f k8s/base/nats.yaml

    # Deploy Redis
    print_status "Deploying Redis..."
    kubectl apply -f k8s/base/redis.yaml

    # Wait for infrastructure to be ready
    print_status "Waiting for infrastructure to be ready..."

    kubectl wait --for=condition=ready pod -l app=nats -n ${NAMESPACE} --timeout=${WAIT_TIMEOUT}
    kubectl wait --for=condition=ready pod -l app=redis -n ${NAMESPACE} --timeout=${WAIT_TIMEOUT}

    print_success "Infrastructure deployed and ready"
}

# Deploy configuration
deploy_configuration() {
    print_status "Deploying configuration..."

    # Apply ConfigMaps
    kubectl apply -f k8s/configmaps/

    # Apply Secrets (with warning about production)
    kubectl apply -f k8s/base/secrets.yaml
    print_warning "Default secrets applied. Update with real values for production!"

    print_success "Configuration deployed"
}

# Build and push Docker image
build_and_push_image() {
    print_status "Building and pushing Docker image..."

    local image_name="${REGISTRY_URL}/actor-mesh/actor-mesh-demo:${IMAGE_TAG}"

    # Build the image
    docker build -t ${image_name} .

    # Push to registry
    docker push ${image_name}

    print_success "Image built and pushed: ${image_name}"
}

# Deploy application components
deploy_application() {
    print_status "Deploying application components..."

    # Update image references in manifests
    local image_name="${REGISTRY_URL}/actor-mesh/actor-mesh-demo:${IMAGE_TAG}"

    # Create temporary directory for processed manifests
    local temp_dir=$(mktemp -d)

    # Process manifests and update image references
    find k8s/deployments/ -name "*.yaml" -exec cp {} ${temp_dir}/ \;

    # Replace image references
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        find ${temp_dir} -name "*.yaml" -exec sed -i '' "s|actor-mesh/actor-mesh-demo:latest|${image_name}|g" {} \;
    else
        # Linux
        find ${temp_dir} -name "*.yaml" -exec sed -i "s|actor-mesh/actor-mesh-demo:latest|${image_name}|g" {} \;
    fi

    # Deploy mock services first
    print_status "Deploying mock services..."
    kubectl apply -f ${temp_dir}/mock-services.yaml

    # Wait for mock services to be ready
    kubectl wait --for=condition=available deployment/mock-services -n ${NAMESPACE} --timeout=${WAIT_TIMEOUT}

    # Deploy actors
    print_status "Deploying actors..."
    kubectl apply -f ${temp_dir}/actors.yaml

    # Deploy gateway
    print_status "Deploying API gateway..."
    kubectl apply -f ${temp_dir}/gateway.yaml

    # Clean up temporary directory
    rm -rf ${temp_dir}

    print_success "Application components deployed"
}

# Deploy ingress
deploy_ingress() {
    print_status "Deploying ingress..."

    kubectl apply -f k8s/base/ingress.yaml

    print_success "Ingress deployed"
}

# Wait for all deployments to be ready
wait_for_deployments() {
    print_status "Waiting for all deployments to be ready..."

    local deployments=(
        "mock-services"
        "gateway"
        "sentiment-analyzer"
        "intent-analyzer"
        "context-retriever"
        "response-generator"
        "guardrail-validator"
        "execution-coordinator"
        "decision-router"
        "escalation-router"
        "response-aggregator"
    )

    for deployment in "${deployments[@]}"; do
        print_status "Waiting for ${deployment}..."
        kubectl wait --for=condition=available deployment/${deployment} -n ${NAMESPACE} --timeout=${WAIT_TIMEOUT}
    done

    print_success "All deployments are ready"
}

# Run post-deployment checks
post_deployment_checks() {
    print_status "Running post-deployment checks..."

    # Check pod status
    print_status "Pod status:"
    kubectl get pods -n ${NAMESPACE}

    # Check service status
    print_status "Service status:"
    kubectl get svc -n ${NAMESPACE}

    # Check ingress status
    print_status "Ingress status:"
    kubectl get ingress -n ${NAMESPACE}

    # Test health endpoints
    print_status "Testing health endpoints..."

    # Port forward for health check
    kubectl port-forward svc/gateway 8080:80 -n ${NAMESPACE} &
    local port_forward_pid=$!

    sleep 5

    if curl -s http://localhost:8080/api/health > /dev/null; then
        print_success "Health endpoint is responding"
    else
        print_warning "Health endpoint is not responding yet"
    fi

    # Kill port forward
    kill ${port_forward_pid} 2>/dev/null || true

    print_success "Post-deployment checks completed"
}

# Show deployment information
show_deployment_info() {
    print_success "🎉 Deployment completed successfully!"
    echo ""
    echo "📊 Deployment Information:"
    echo "========================="
    echo "Namespace: ${NAMESPACE}"
    echo "Environment: ${ENVIRONMENT}"
    echo "Image Tag: ${IMAGE_TAG}"
    echo "Registry: ${REGISTRY_URL}"
    echo ""
    echo "🔍 Monitoring Commands:"
    echo "======================"
    echo "View pods:       kubectl get pods -n ${NAMESPACE}"
    echo "View services:   kubectl get svc -n ${NAMESPACE}"
    echo "View ingress:    kubectl get ingress -n ${NAMESPACE}"
    echo "View logs:       kubectl logs -f deployment/gateway -n ${NAMESPACE}"
    echo "Port forward:    kubectl port-forward svc/gateway 8080:80 -n ${NAMESPACE}"
    echo ""
    echo "🌐 Access URLs:"
    echo "=============="
    echo "Local (port-forward): http://localhost:8080"
    echo "Via Ingress:         http://actor-mesh.local:8080"
    echo "Health Check:        http://localhost:8080/api/health"
    echo "API Docs:           http://localhost:8080/docs"
    echo "Chat Widget:        http://localhost:8080/widget"
    echo ""
    echo "🔧 Troubleshooting:"
    echo "=================="
    echo "Check events:    kubectl get events -n ${NAMESPACE} --sort-by=.metadata.creationTimestamp"
    echo "Describe pod:    kubectl describe pod <pod-name> -n ${NAMESPACE}"
    echo "Pod logs:        kubectl logs <pod-name> -n ${NAMESPACE}"
    echo "Exec into pod:   kubectl exec -it <pod-name> -n ${NAMESPACE} -- /bin/bash"
    echo ""
}

# Rollback deployment
rollback_deployment() {
    print_status "Rolling back deployment..."

    local deployments=(
        "gateway"
        "mock-services"
        "sentiment-analyzer"
        "intent-analyzer"
        "context-retriever"
        "response-generator"
        "guardrail-validator"
        "execution-coordinator"
        "decision-router"
        "escalation-router"
        "response-aggregator"
    )

    for deployment in "${deployments[@]}"; do
        if kubectl get deployment ${deployment} -n ${NAMESPACE} &> /dev/null; then
            print_status "Rolling back ${deployment}..."
            kubectl rollout undo deployment/${deployment} -n ${NAMESPACE}
            kubectl rollout status deployment/${deployment} -n ${NAMESPACE}
        fi
    done

    print_success "Rollback completed"
}

# Clean up deployment
cleanup_deployment() {
    print_status "Cleaning up deployment..."

    # Delete application resources
    kubectl delete -f k8s/deployments/ --ignore-not-found=true
    kubectl delete -f k8s/base/ingress.yaml --ignore-not-found=true
    kubectl delete -f k8s/configmaps/ --ignore-not-found=true

    # Optionally delete infrastructure (commented out for safety)
    # kubectl delete -f k8s/base/nats.yaml --ignore-not-found=true
    # kubectl delete -f k8s/base/redis.yaml --ignore-not-found=true
    # kubectl delete -f k8s/base/secrets.yaml --ignore-not-found=true

    # Optionally delete namespace (commented out for safety)
    # kubectl delete namespace ${NAMESPACE} --ignore-not-found=true

    print_success "Cleanup completed"
    print_warning "Infrastructure and namespace were preserved"
    print_warning "To delete everything, run: kubectl delete namespace ${NAMESPACE}"
}

# Main deployment function
deploy() {
    print_status "🚀 Deploying Actor Mesh Demo to Kubernetes"
    print_status "==========================================="

    check_prerequisites
    create_namespace
    deploy_configuration
    deploy_infrastructure

    if [[ "${BUILD_IMAGE:-true}" == "true" ]]; then
        build_and_push_image
    fi

    deploy_application
    deploy_ingress
    wait_for_deployments
    post_deployment_checks
    show_deployment_info
}

# Handle script arguments
main() {
    case "${1:-deploy}" in
        "deploy")
            deploy
            ;;

        "build")
            check_prerequisites
            build_and_push_image
            ;;

        "rollback")
            check_prerequisites
            rollback_deployment
            ;;

        "cleanup")
            check_prerequisites
            cleanup_deployment
            ;;

        "status")
            check_prerequisites
            post_deployment_checks
            ;;

        "info")
            show_deployment_info
            ;;

        "help"|"-h"|"--help")
            echo "Usage: $0 [deploy|build|rollback|cleanup|status|info|help]"
            echo ""
            echo "Commands:"
            echo "  deploy   - Deploy complete application (default)"
            echo "  build    - Build and push Docker image only"
            echo "  rollback - Rollback to previous deployment"
            echo "  cleanup  - Remove application components"
            echo "  status   - Check deployment status"
            echo "  info     - Show deployment information"
            echo "  help     - Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  ENVIRONMENT    - Deployment environment (default: development)"
            echo "  IMAGE_TAG      - Docker image tag (default: latest)"
            echo "  REGISTRY_URL   - Docker registry URL (default: localhost:5001)"
            echo "  NAMESPACE      - Kubernetes namespace (default: actor-mesh)"
            echo "  BUILD_IMAGE    - Build image before deploy (default: true)"
            echo "  WAIT_TIMEOUT   - Timeout for waiting operations (default: 300s)"
            echo ""
            echo "Examples:"
            echo "  $0 deploy                           # Deploy with defaults"
            echo "  ENVIRONMENT=production $0 deploy    # Deploy to production"
            echo "  IMAGE_TAG=v1.2.3 $0 deploy         # Deploy specific version"
            echo "  BUILD_IMAGE=false $0 deploy        # Deploy without building"
            ;;

        *)
            print_error "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Handle script interruption
trap 'print_error "Deployment interrupted"; exit 1' INT TERM

# Run main function
main "$@"
