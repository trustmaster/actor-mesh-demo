#!/bin/bash

# E-commerce Support Agent - Actor Mesh Demo
# Reliable startup script to avoid common issues

set -e  # Exit on any error

echo "🚀 E-commerce Support Agent - Actor Mesh Demo"
echo "=============================================="
echo ""



# Function to cleanup and exit gracefully
cleanup() {
    echo ""
    echo "🛑 Cleaning up on exit..."
    make stop 2>/dev/null || true
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Function to check if port is in use and kill processes
kill_port() {
    local port=$1
    echo "🔍 Checking port $port..."
    if lsof -ti :$port >/dev/null 2>&1; then
        echo "⚠️  Port $port is in use, killing processes..."
        lsof -ti :$port | xargs -r kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Function to wait for service to be ready
wait_for_service() {
    local service=$1
    local port=$2
    local max_attempts=30
    local attempt=1

    echo "⏳ Waiting for $service to be ready on port $port..."

    while [ $attempt -le $max_attempts ]; do
        if nc -z localhost $port 2>/dev/null; then
            echo "✅ $service is ready!"
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done

    echo "❌ $service failed to start within $max_attempts seconds"
    return 1
}

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please run 'make install' first."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "Makefile" ] || [ ! -f "pyproject.toml" ]; then
    echo "❌ Please run this script from the actor-mesh-demo directory"
    exit 1
fi

echo "🧹 Cleaning up any existing processes..."
make stop 2>/dev/null || true

echo "🔍 Checking for port conflicts..."
kill_port 8000  # API Gateway
kill_port 4222  # NATS
kill_port 6379  # Redis

echo ""
echo "🔧 Starting infrastructure..."
make start-infrastructure

# Wait for infrastructure to be ready
wait_for_service "NATS" 4222
wait_for_service "Redis" 6379

echo ""
echo "🌐 Starting mock services..."
make start-services

echo ""
echo "🤖 Starting actors..."
make start-actors

echo ""
echo "🌐 Starting API Gateway..."
make start-gateway

# Wait for API Gateway to be ready
wait_for_service "API Gateway" 8000

echo ""
echo "✅ All services started successfully!"
echo ""
echo "🌐 Available endpoints:"
echo "  Main widget:     http://localhost:8000/widget"
echo "  Enhanced widget: http://localhost:8000/static/chat.html"
echo "  API docs:        http://localhost:8000/docs"
echo ""
echo "💡 Tips:"
echo "  - Press Ctrl+C to stop all services"
echo "  - Run 'make stop' to stop manually"
echo "  - Run 'make clean' for a complete cleanup"
echo ""
echo "🎯 Demo is ready! Try sending a message through the web interface."
echo ""

# Keep the script running until interrupted
echo "📡 Services are running... Press Ctrl+C to stop."
while true; do
    sleep 1
done
