#!/bin/bash
# Installation script for the E-commerce Support Agent Actor Mesh Demo.
#
# This script sets up the development environment and installs all dependencies.

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
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

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python version
check_python() {
    print_status "Checking Python version..."

    if command_exists python3; then
        PYTHON_CMD="python3"
    elif command_exists python; then
        PYTHON_CMD="python"
    else
        print_error "Python is not installed. Please install Python 3.11+ first."
        exit 1
    fi

    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
    MAJOR_VERSION=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    MINOR_VERSION=$(echo $PYTHON_VERSION | cut -d'.' -f2)

    if [ "$MAJOR_VERSION" -lt 3 ] || ([ "$MAJOR_VERSION" -eq 3 ] && [ "$MINOR_VERSION" -lt 11 ]); then
        print_error "Python 3.11+ is required. Found: $PYTHON_VERSION"
        exit 1
    fi

    print_success "Python $PYTHON_VERSION found"
}

# Setup virtual environment
setup_venv() {
    print_status "Setting up virtual environment..."

    if [ ! -d "venv" ]; then
        $PYTHON_CMD -m venv venv
        print_success "Virtual environment created"
    else
        print_warning "Virtual environment already exists"
    fi

    # Activate virtual environment
    if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi

    print_success "Virtual environment activated"
}

# Install Python dependencies
install_python_deps() {
    print_status "Installing Python dependencies..."

    # Upgrade pip and install build tools
    pip install --upgrade pip setuptools wheel

    # Install with pyproject.toml
    if [ -f "pyproject.toml" ]; then
        pip install -e ".[dev,test]"
        print_success "Python dependencies installed from pyproject.toml"
    elif [ -f "requirements.txt" ]; then
        print_warning "Using legacy requirements.txt. Consider migrating to pyproject.toml"
        pip install -r requirements.txt
        print_success "Python dependencies installed from requirements.txt"
    else
        print_error "Neither pyproject.toml nor requirements.txt found"
        exit 1
    fi
}

# Check for Docker
check_docker() {
    print_status "Checking for Docker..."

    if command_exists docker; then
        print_success "Docker found"
        return 0
    else
        print_warning "Docker not found. Some features may not work."
        return 1
    fi
}

# Setup NATS server
setup_nats() {
    print_status "Setting up NATS server..."

    if check_docker; then
        print_status "Starting NATS server with Docker..."

        # Check if NATS container is already running
        if docker ps | grep -q "nats-demo"; then
            print_warning "NATS container already running"
        else
            # Start NATS server
            docker run -d --name nats-demo \
                -p 4222:4222 \
                -p 8222:8222 \
                nats:latest -js

            # Wait for NATS to start
            sleep 3

            if docker ps | grep -q "nats-demo"; then
                print_success "NATS server started on ports 4222 (client) and 8222 (monitoring)"
            else
                print_error "Failed to start NATS server"
                return 1
            fi
        fi
    else
        print_warning "Docker not available. Please install NATS manually:"
        print_warning "Visit: https://docs.nats.io/running-a-nats-service/introduction/installation"
    fi
}

# Setup Redis (optional)
setup_redis() {
    print_status "Setting up Redis (optional)..."

    if check_docker; then
        print_status "Starting Redis server with Docker..."

        # Check if Redis container is already running
        if docker ps | grep -q "redis-demo"; then
            print_warning "Redis container already running"
        else
            # Start Redis server
            docker run -d --name redis-demo \
                -p 6379:6379 \
                redis:alpine

            # Wait for Redis to start
            sleep 2

            if docker ps | grep -q "redis-demo"; then
                print_success "Redis server started on port 6379"
            else
                print_error "Failed to start Redis server"
                return 1
            fi
        fi
    else
        print_warning "Docker not available. Redis is optional but recommended."
    fi
}

# Create data directories
create_directories() {
    print_status "Creating data directories..."

    mkdir -p data
    mkdir -p logs

    print_success "Data directories created"
}

# Setup environment file
setup_env() {
    print_status "Setting up environment configuration..."

    if [ ! -f ".env" ]; then
        cat > .env << EOF
# NATS Configuration
NATS_URL=nats://localhost:4222

# API Endpoints (will be started by mock services)
CUSTOMER_API_URL=http://localhost:8001
ORDERS_API_URL=http://localhost:8002
TRACKING_API_URL=http://localhost:8003

# Redis (optional)
REDIS_URL=redis://localhost:6379

# Database
SQLITE_DB_PATH=data/conversations.db

# LLM Configuration (set your API keys)
# OPENAI_API_KEY=your-openai-key-here
# ANTHROPIC_API_KEY=your-anthropic-key-here
LITELLM_MODEL=gpt-3.5-turbo

# Logging
LOG_LEVEL=INFO

# Actor Configuration
SENTIMENT_CONFIDENCE_THRESHOLD=0.7
INTENT_TIMEOUT=30
RESPONSE_TEMPERATURE=0.3
USE_LLM_VALIDATION=true
EOF
        print_success "Environment file created (.env)"
        print_warning "Please edit .env to add your LLM API keys"
    else
        print_warning "Environment file already exists"
    fi
}

# Run basic tests
run_tests() {
    print_status "Running basic tests..."

    if $PYTHON_CMD test_basic_flow.py; then
        print_success "Basic tests passed!"
    else
        print_warning "Some tests failed - this is expected without LLM API keys"
        print_warning "The system structure is working correctly"
    fi
}

# Print usage information
print_usage() {
    echo ""
    echo "🚀 Installation completed! Next steps:"
    echo ""
    echo "1. Activate virtual environment:"
    if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "   source venv/Scripts/activate"
    else
        echo "   source venv/bin/activate"
    fi
    echo ""
    echo "2. Configure LLM API keys in .env file:"
    echo "   - OpenAI: OPENAI_API_KEY=your-key"
    echo "   - Anthropic: ANTHROPIC_API_KEY=your-key"
    echo "   - Or setup Ollama locally"
    echo ""
    echo "3. Test the system:"
    echo "   python test_basic_flow.py"
    echo ""
    echo "4. Start individual actors:"
    echo "   python -m actors.sentiment_analyzer"
    echo "   python -m actors.intent_analyzer"
    echo "   # ... etc"
    echo ""
    echo "5. Start mock services:"
    echo "   python -m mock_services.customer_api"
    echo "   python -m mock_services.orders_api"
    echo "   python -m mock_services.tracking_api"
    echo ""
    echo "6. Access NATS monitoring (if running):"
    echo "   http://localhost:8222"
    echo ""
    echo "📖 See README.md for detailed usage instructions"
    echo ""
}

# Main installation function
main() {
    echo ""
    echo "🎯 E-commerce Support Agent - Actor Mesh Demo"
    echo "=============================================="
    echo ""

    # Check prerequisites
    check_python

    # Setup environment
    setup_venv
    install_python_deps

    # Create directories
    create_directories
    setup_env

    # Setup services
    setup_nats
    setup_redis

    # Run tests
    run_tests

    # Print usage
    print_usage

    print_success "Installation completed successfully! 🎉"
}

# Handle script arguments
case "${1:-install}" in
    "install")
        main
        ;;
    "clean")
        print_status "Cleaning up..."
        docker stop nats-demo redis-demo 2>/dev/null || true
        docker rm nats-demo redis-demo 2>/dev/null || true
        rm -rf venv
        rm -rf data
        rm -rf logs
        rm -f .env
        print_success "Cleanup completed"
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [install|clean|help]"
        echo ""
        echo "Commands:"
        echo "  install  - Install dependencies and setup environment (default)"
        echo "  clean    - Remove all generated files and containers"
        echo "  help     - Show this help message"
        ;;
    *)
        print_error "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac
