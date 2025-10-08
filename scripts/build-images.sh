#!/bin/bash
# Build script for Actor Mesh Demo Docker images
# This script builds and tags Docker images for all components

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
IMAGE_NAME="actor-mesh/actor-mesh-demo"
REGISTRY_URL="${REGISTRY_URL:-localhost:5001}"
TAG="${TAG:-latest}"
BUILD_ARGS="${BUILD_ARGS:-}"
PUSH_IMAGES="${PUSH_IMAGES:-true}"
PARALLEL_BUILDS="${PARALLEL_BUILDS:-false}"
CACHE_FROM="${CACHE_FROM:-true}"
MULTI_ARCH="${MULTI_ARCH:-false}"

# Build targets
BUILD_TARGETS=(
    "production"
    "gateway"
    "actor"
    "mock-services"
    "allinone"
)

# Get version information
get_version_info() {
    local git_commit=""
    local git_branch=""
    local build_time=""

    if command -v git &> /dev/null && [ -d ".git" ]; then
        git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    else
        git_commit="unknown"
        git_branch="unknown"
    fi

    build_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    echo "GIT_COMMIT=${git_commit} GIT_BRANCH=${git_branch} BUILD_TIME=${build_time}"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    # Check if Docker is available
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi

    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        exit 1
    fi

    # Check if buildx is available for multi-arch builds
    if [[ "${MULTI_ARCH}" == "true" ]]; then
        if ! docker buildx version &> /dev/null; then
            print_error "Docker buildx is required for multi-architecture builds"
            exit 1
        fi
    fi

    print_success "Prerequisites check completed"
}

# Create buildx builder for multi-arch builds
setup_buildx() {
    if [[ "${MULTI_ARCH}" == "true" ]]; then
        print_status "Setting up Docker buildx for multi-architecture builds..."

        # Create builder if it doesn't exist
        if ! docker buildx ls | grep -q "actor-mesh-builder"; then
            docker buildx create --name actor-mesh-builder --use
            docker buildx inspect --bootstrap
        else
            docker buildx use actor-mesh-builder
        fi

        print_success "Docker buildx configured"
    fi
}

# Build single image
build_image() {
    local target=$1
    local image_tag="${REGISTRY_URL}/${IMAGE_NAME}:${TAG}-${target}"
    local latest_tag="${REGISTRY_URL}/${IMAGE_NAME}:${target}"

    print_status "Building image for target: ${target}"

    # Prepare build command
    local build_cmd="docker build"
    local build_args_str=""
    local cache_args=""

    # Add version info to build args
    local version_info=$(get_version_info)
    build_args_str="--build-arg ${version_info}"

    # Add custom build args
    if [[ -n "${BUILD_ARGS}" ]]; then
        build_args_str="${build_args_str} ${BUILD_ARGS}"
    fi

    # Add cache arguments
    if [[ "${CACHE_FROM}" == "true" ]]; then
        cache_args="--cache-from ${latest_tag}"
    fi

    # Multi-arch build
    if [[ "${MULTI_ARCH}" == "true" ]]; then
        build_cmd="docker buildx build --platform linux/amd64,linux/arm64"
        if [[ "${PUSH_IMAGES}" == "true" ]]; then
            build_cmd="${build_cmd} --push"
        else
            build_cmd="${build_cmd} --load"
        fi
    fi

    # Execute build
    ${build_cmd} \
        --target ${target} \
        ${build_args_str} \
        ${cache_args} \
        -t ${image_tag} \
        -t ${latest_tag} \
        -f Dockerfile \
        .

    if [[ $? -eq 0 ]]; then
        print_success "Built image: ${image_tag}"

        # Push images if not multi-arch (multi-arch pushes automatically)
        if [[ "${PUSH_IMAGES}" == "true" && "${MULTI_ARCH}" != "true" ]]; then
            push_image ${image_tag}
            push_image ${latest_tag}
        fi
    else
        print_error "Failed to build image for target: ${target}"
        return 1
    fi
}

# Push single image
push_image() {
    local image_tag=$1

    print_status "Pushing image: ${image_tag}"

    if docker push ${image_tag}; then
        print_success "Pushed image: ${image_tag}"
    else
        print_error "Failed to push image: ${image_tag}"
        return 1
    fi
}

# Build all images sequentially
build_sequential() {
    print_status "Building images sequentially..."

    for target in "${BUILD_TARGETS[@]}"; do
        build_image ${target}
        if [[ $? -ne 0 ]]; then
            print_error "Sequential build failed at target: ${target}"
            exit 1
        fi
    done
}

# Build all images in parallel
build_parallel() {
    print_status "Building images in parallel..."

    local pids=()

    for target in "${BUILD_TARGETS[@]}"; do
        build_image ${target} &
        pids+=($!)
    done

    # Wait for all builds to complete
    local failures=0
    for pid in "${pids[@]}"; do
        if ! wait ${pid}; then
            failures=$((failures + 1))
        fi
    done

    if [[ ${failures} -gt 0 ]]; then
        print_error "Parallel build failed with ${failures} failures"
        exit 1
    fi
}

# Test built images
test_images() {
    print_status "Testing built images..."

    for target in "${BUILD_TARGETS[@]}"; do
        local image_tag="${REGISTRY_URL}/${IMAGE_NAME}:${target}"

        print_status "Testing image: ${image_tag}"

        # Basic image inspection
        if ! docker inspect ${image_tag} &> /dev/null; then
            print_error "Image not found: ${image_tag}"
            continue
        fi

        # Test image can run
        case ${target} in
            "gateway")
                if docker run --rm --entrypoint python ${image_tag} -c "import api.gateway; print('Gateway module OK')"; then
                    print_success "Gateway image test passed"
                else
                    print_error "Gateway image test failed"
                fi
                ;;
            "actor")
                if docker run --rm --entrypoint python ${image_tag} -c "import actors.base; print('Actor module OK')"; then
                    print_success "Actor image test passed"
                else
                    print_error "Actor image test failed"
                fi
                ;;
            "mock-services")
                if docker run --rm --entrypoint python ${image_tag} -c "import mock_services; print('Mock services OK')"; then
                    print_success "Mock services image test passed"
                else
                    print_error "Mock services image test failed"
                fi
                ;;
        esac
    done
}

# Show image information
show_image_info() {
    print_success "🎉 Image build completed!"
    echo ""
    echo "📊 Built Images:"
    echo "==============="

    for target in "${BUILD_TARGETS[@]}"; do
        local image_tag="${REGISTRY_URL}/${IMAGE_NAME}:${TAG}-${target}"
        local latest_tag="${REGISTRY_URL}/${IMAGE_NAME}:${target}"

        echo "Target: ${target}"
        echo "  Tagged: ${image_tag}"
        echo "  Latest: ${latest_tag}"

        # Show image size
        if docker inspect ${latest_tag} &> /dev/null; then
            local size=$(docker inspect ${latest_tag} --format='{{.Size}}' | numfmt --to=iec-i --suffix=B)
            echo "  Size: ${size}"
        fi
        echo ""
    done

    echo "🔧 Usage Examples:"
    echo "=================="
    echo "Run gateway:       docker run -p 8000:8000 ${REGISTRY_URL}/${IMAGE_NAME}:gateway"
    echo "Run actor:         docker run ${REGISTRY_URL}/${IMAGE_NAME}:actor python -m actors.sentiment_analyzer"
    echo "Run mock services: docker run -p 8001-8003:8001-8003 ${REGISTRY_URL}/${IMAGE_NAME}:mock-services"
    echo "Run all-in-one:    docker run -p 8000:8000 ${REGISTRY_URL}/${IMAGE_NAME}:allinone"
    echo ""
    echo "🚀 Kubernetes Deployment:"
    echo "========================="
    echo "kubectl apply -k k8s/overlays/development"
    echo ""
}

# Clean up build artifacts
cleanup() {
    print_status "Cleaning up build artifacts..."

    # Remove dangling images
    if docker images -f "dangling=true" -q | grep -q .; then
        docker rmi $(docker images -f "dangling=true" -q) 2>/dev/null || true
        print_success "Removed dangling images"
    fi

    # Clean build cache (optional)
    if [[ "${CLEAN_CACHE:-false}" == "true" ]]; then
        docker builder prune -f
        print_success "Cleaned build cache"
    fi
}

# Main build function
build() {
    print_status "🔨 Building Actor Mesh Demo Docker Images"
    print_status "=========================================="

    check_prerequisites
    setup_buildx

    if [[ "${PARALLEL_BUILDS}" == "true" ]]; then
        build_parallel
    else
        build_sequential
    fi

    test_images
    cleanup
    show_image_info
}

# Handle script arguments
main() {
    case "${1:-build}" in
        "build")
            build
            ;;

        "test")
            check_prerequisites
            test_images
            ;;

        "push")
            check_prerequisites
            for target in "${BUILD_TARGETS[@]}"; do
                local image_tag="${REGISTRY_URL}/${IMAGE_NAME}:${TAG}-${target}"
                local latest_tag="${REGISTRY_URL}/${IMAGE_NAME}:${target}"
                push_image ${image_tag}
                push_image ${latest_tag}
            done
            ;;

        "clean")
            cleanup
            # Also remove all actor-mesh images
            if docker images "${REGISTRY_URL}/${IMAGE_NAME}" -q | grep -q .; then
                docker rmi $(docker images "${REGISTRY_URL}/${IMAGE_NAME}" -q) 2>/dev/null || true
                print_success "Removed all actor-mesh images"
            fi
            ;;

        "list")
            print_status "Available images:"
            docker images "${REGISTRY_URL}/${IMAGE_NAME}"
            ;;

        "help"|"-h"|"--help")
            echo "Usage: $0 [build|test|push|clean|list|help]"
            echo ""
            echo "Commands:"
            echo "  build  - Build all Docker images (default)"
            echo "  test   - Test built images"
            echo "  push   - Push images to registry"
            echo "  clean  - Clean up build artifacts and images"
            echo "  list   - List built images"
            echo "  help   - Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  REGISTRY_URL      - Docker registry URL (default: localhost:5001)"
            echo "  TAG               - Image tag (default: latest)"
            echo "  BUILD_ARGS        - Additional build arguments"
            echo "  PUSH_IMAGES       - Push images after build (default: true)"
            echo "  PARALLEL_BUILDS   - Build images in parallel (default: false)"
            echo "  CACHE_FROM        - Use cache from previous builds (default: true)"
            echo "  MULTI_ARCH        - Build multi-architecture images (default: false)"
            echo "  CLEAN_CACHE       - Clean build cache after build (default: false)"
            echo ""
            echo "Examples:"
            echo "  $0 build                           # Build all images"
            echo "  TAG=v1.2.3 $0 build              # Build with specific tag"
            echo "  PARALLEL_BUILDS=true $0 build     # Build in parallel"
            echo "  MULTI_ARCH=true $0 build          # Build multi-arch images"
            echo "  REGISTRY_URL=my-registry.com $0    # Use custom registry"
            ;;

        *)
            print_error "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Handle script interruption
trap 'print_error "Build interrupted"; exit 1' INT TERM

# Run main function
main "$@"
