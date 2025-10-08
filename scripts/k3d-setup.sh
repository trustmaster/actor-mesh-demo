#!/bin/bash
# k3d Cluster Setup Script for Actor Mesh Demo
# This script creates a complete k3d cluster with all necessary components

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
CLUSTER_NAME="actor-mesh"
REGISTRY_NAME="actor-mesh-registry"
REGISTRY_PORT="5001"
K3S_VERSION="v1.28.5-k3s1"
NGINX_VERSION="v1.9.4"

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    # Check if k3d is installed
    if ! command -v k3d &> /dev/null; then
        print_error "k3d is not installed. Please install it first:"
        print_error "curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash"
        exit 1
    fi

    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed. Please install it first:"
        print_error "https://kubernetes.io/docs/tasks/tools/install-kubectl/"
        exit 1
    fi

    # Check if docker is running
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi

    # Check if helm is installed (optional but recommended)
    if ! command -v helm &> /dev/null; then
        print_warning "Helm is not installed. Some features may not work."
        print_warning "Install with: curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"
    fi

    print_success "Prerequisites check completed"
}

# Create local registry
create_registry() {
    print_status "Creating local Docker registry..."

    # Check if registry already exists
    if docker ps -a --format "table {{.Names}}" | grep -q "^${REGISTRY_NAME}$"; then
        print_warning "Registry ${REGISTRY_NAME} already exists"

        # Check if it's running
        if ! docker ps --format "table {{.Names}}" | grep -q "^${REGISTRY_NAME}$"; then
            print_status "Starting existing registry..."
            docker start ${REGISTRY_NAME}
        fi
    else
        # Create new registry
        docker run -d \
            --restart=always \
            -p "127.0.0.1:${REGISTRY_PORT}:5000" \
            --name ${REGISTRY_NAME} \
            registry:2

        print_success "Registry created at localhost:${REGISTRY_PORT}"
    fi

    # Wait for registry to be ready
    print_status "Waiting for registry to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:${REGISTRY_PORT}/v2/ > /dev/null 2>&1; then
            print_success "Registry is ready"
            break
        fi

        if [ $i -eq 30 ]; then
            print_error "Registry failed to start"
            exit 1
        fi

        sleep 1
    done
}

# Create k3d cluster
create_cluster() {
    print_status "Creating k3d cluster..."

    # Check if cluster already exists
    if k3d cluster list | grep -q "^${CLUSTER_NAME}"; then
        print_warning "Cluster ${CLUSTER_NAME} already exists"

        # Check if it's running
        if ! k3d cluster list | grep "${CLUSTER_NAME}" | grep -q "running"; then
            print_status "Starting existing cluster..."
            k3d cluster start ${CLUSTER_NAME}
        fi
    else
        # Create new cluster
        k3d cluster create ${CLUSTER_NAME} \
            --image rancher/k3s:${K3S_VERSION} \
            --port "8080:80@loadbalancer" \
            --port "8443:443@loadbalancer" \
            --port "6443:6443" \
            --port "4222:4222@loadbalancer" \
            --port "8222:8222@loadbalancer" \
            --port "6379:6379@loadbalancer" \
            --registry-use k3d-${REGISTRY_NAME}:${REGISTRY_PORT} \
            --registry-config ./scripts/registry-config.yaml \
            --volume $(pwd)/data:/data \
            --agents 2 \
            --servers 1 \
            --wait \
            --timeout 300s

        print_success "Cluster ${CLUSTER_NAME} created"
    fi

    # Connect registry to cluster network
    if ! docker network ls | grep k3d-${CLUSTER_NAME} > /dev/null; then
        print_error "Cluster network not found"
        exit 1
    fi

    # Connect registry to cluster network if not already connected
    if ! docker inspect ${REGISTRY_NAME} | grep -q "k3d-${CLUSTER_NAME}"; then
        docker network connect k3d-${CLUSTER_NAME} ${REGISTRY_NAME} || true
    fi

    # Update kubeconfig
    k3d kubeconfig merge ${CLUSTER_NAME} --kubeconfig-switch-context

    print_success "Kubeconfig updated and context switched"
}

# Install NGINX Ingress Controller
install_nginx_ingress() {
    print_status "Installing NGINX Ingress Controller..."

    # Check if already installed
    if kubectl get namespace ingress-nginx > /dev/null 2>&1; then
        print_warning "NGINX Ingress Controller already installed"
        return
    fi

    # Install NGINX Ingress Controller for k3d
    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-${NGINX_VERSION}/deploy/static/provider/cloud/deploy.yaml

    # Wait for NGINX Ingress Controller to be ready
    print_status "Waiting for NGINX Ingress Controller to be ready..."
    kubectl wait --namespace ingress-nginx \
        --for=condition=ready pod \
        --selector=app.kubernetes.io/component=controller \
        --timeout=300s

    print_success "NGINX Ingress Controller installed and ready"
}

# Install cert-manager (optional)
install_cert_manager() {
    print_status "Installing cert-manager..."

    # Check if already installed
    if kubectl get namespace cert-manager > /dev/null 2>&1; then
        print_warning "cert-manager already installed"
        return
    fi

    # Install cert-manager
    kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.2/cert-manager.yaml

    # Wait for cert-manager to be ready
    print_status "Waiting for cert-manager to be ready..."
    kubectl wait --namespace cert-manager \
        --for=condition=ready pod \
        --selector=app.kubernetes.io/instance=cert-manager \
        --timeout=300s

    print_success "cert-manager installed and ready"
}

# Create ClusterIssuer for cert-manager
create_cluster_issuer() {
    print_status "Creating ClusterIssuer for cert-manager..."

    kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-issuer
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: admin@actor-mesh.local
    privateKeySecretRef:
      name: letsencrypt-staging
    solvers:
    - http01:
        ingress:
          class: nginx
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@actor-mesh.local
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF

    print_success "ClusterIssuers created"
}

# Configure local DNS
configure_local_dns() {
    print_status "Configuring local DNS..."

    # Get the cluster's external IP
    CLUSTER_IP="127.0.0.1"

    # Create hosts entries
    cat << EOF

# Actor Mesh Demo - Local Development
# Add these entries to your /etc/hosts file:

${CLUSTER_IP} actor-mesh.local
${CLUSTER_IP} api.actor-mesh.local
${CLUSTER_IP} chat.actor-mesh.local
${CLUSTER_IP} mock.actor-mesh.local
${CLUSTER_IP} monitoring.actor-mesh.local

# To add automatically, run:
# sudo bash -c 'echo "${CLUSTER_IP} actor-mesh.local api.actor-mesh.local chat.actor-mesh.local mock.actor-mesh.local monitoring.actor-mesh.local" >> /etc/hosts'

EOF

    print_warning "Please add the above entries to your /etc/hosts file for local development"
}

# Build and push application image
build_and_push_image() {
    print_status "Building and pushing application image..."

    # Build the Docker image
    docker build -t localhost:${REGISTRY_PORT}/actor-mesh/actor-mesh-demo:latest .

    # Push to local registry
    docker push localhost:${REGISTRY_PORT}/actor-mesh/actor-mesh-demo:latest

    print_success "Application image built and pushed to local registry"
}

# Create monitoring namespace and auth secret
setup_monitoring() {
    print_status "Setting up monitoring..."

    # Create monitoring auth secret
    kubectl create secret generic monitoring-auth \
        --namespace=ingress-nginx \
        --from-literal=auth=$(echo -n "admin:$(openssl passwd -apr1 'admin123')" | base64 -w 0) \
        --dry-run=client -o yaml | kubectl apply -f -

    print_success "Monitoring setup completed"
}

# Display cluster information
show_cluster_info() {
    print_success "k3d cluster setup completed!"
    echo ""
    echo "🎯 Cluster Information:"
    echo "======================"
    echo "Cluster Name: ${CLUSTER_NAME}"
    echo "Registry: localhost:${REGISTRY_PORT}"
    echo "Kubeconfig: ~/.kube/config"
    echo ""
    echo "📊 Service Endpoints:"
    echo "===================="
    echo "HTTP Load Balancer: http://localhost:8080"
    echo "HTTPS Load Balancer: https://localhost:8443"
    echo "NATS Client: localhost:4222"
    echo "NATS Monitoring: http://localhost:8222"
    echo "Redis: localhost:6379"
    echo ""
    echo "🌐 Web Access (after deployment):"
    echo "================================="
    echo "Main App: http://actor-mesh.local:8080"
    echo "API Docs: http://actor-mesh.local:8080/docs"
    echo "Chat Widget: http://actor-mesh.local:8080/widget"
    echo "Health Check: http://actor-mesh.local:8080/api/health"
    echo ""
    echo "🔧 Useful Commands:"
    echo "=================="
    echo "View cluster: k3d cluster list"
    echo "Stop cluster: k3d cluster stop ${CLUSTER_NAME}"
    echo "Start cluster: k3d cluster start ${CLUSTER_NAME}"
    echo "Delete cluster: k3d cluster delete ${CLUSTER_NAME}"
    echo "View pods: kubectl get pods -A"
    echo "View services: kubectl get svc -A"
    echo "View ingress: kubectl get ingress -A"
    echo ""
    echo "📝 Next Steps:"
    echo "============="
    echo "1. Add DNS entries to /etc/hosts (see above)"
    echo "2. Deploy the application:"
    echo "   kubectl apply -k k8s/overlays/development"
    echo "3. Build and push images:"
    echo "   ./scripts/build-images.sh"
    echo "4. Check deployment status:"
    echo "   kubectl get pods -n actor-mesh"
    echo ""
}

# Cleanup function
cleanup() {
    print_status "Cleaning up..."

    # Stop cluster if exists
    if k3d cluster list | grep -q "^${CLUSTER_NAME}"; then
        k3d cluster delete ${CLUSTER_NAME}
        print_success "Cluster ${CLUSTER_NAME} deleted"
    fi

    # Stop and remove registry if exists
    if docker ps -a --format "table {{.Names}}" | grep -q "^${REGISTRY_NAME}$"; then
        docker stop ${REGISTRY_NAME}
        docker rm ${REGISTRY_NAME}
        print_success "Registry ${REGISTRY_NAME} removed"
    fi

    print_success "Cleanup completed"
}

# Main function
main() {
    case "${1:-setup}" in
        "setup")
            print_status "🚀 Setting up k3d cluster for Actor Mesh Demo"
            print_status "=============================================="

            check_prerequisites
            create_registry
            create_cluster
            install_nginx_ingress
            install_cert_manager
            create_cluster_issuer
            setup_monitoring
            configure_local_dns
            show_cluster_info
            ;;

        "build")
            print_status "🔨 Building and pushing application image"
            check_prerequisites
            build_and_push_image
            ;;

        "cleanup")
            cleanup
            ;;

        "info")
            show_cluster_info
            ;;

        "help"|"-h"|"--help")
            echo "Usage: $0 [setup|build|cleanup|info|help]"
            echo ""
            echo "Commands:"
            echo "  setup   - Create k3d cluster with all components (default)"
            echo "  build   - Build and push application image to local registry"
            echo "  cleanup - Delete cluster and registry"
            echo "  info    - Show cluster information"
            echo "  help    - Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 setup    # Create complete development environment"
            echo "  $0 build    # Build and push application image"
            echo "  $0 cleanup  # Clean up everything"
            ;;

        *)
            print_error "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Handle script interruption
trap 'print_error "Script interrupted"; exit 1' INT TERM

# Run main function
main "$@"
