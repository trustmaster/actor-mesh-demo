#!/bin/bash
# Start script for all-in-one Docker container
# This script starts all services in the correct order for the Actor Mesh Demo

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

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Cleanup function
cleanup() {
    print_status "Shutting down services..."

    # Kill all background jobs
    if [ ! -z "$MOCK_SERVICES_PID" ]; then
        print_status "Stopping mock services (PID: $MOCK_SERVICES_PID)"
        kill $MOCK_SERVICES_PID 2>/dev/null || true
    fi

    if [ ! -z "$ACTORS_PID" ]; then
        print_status "Stopping actors (PID: $ACTORS_PID)"
        kill $ACTORS_PID 2>/dev/null || true
    fi

    if [ ! -z "$GATEWAY_PID" ]; then
        print_status "Stopping gateway (PID: $GATEWAY_PID)"
        kill $GATEWAY_PID 2>/dev/null || true
    fi

    # Kill any remaining python processes
    pkill -f "python -m" 2>/dev/null || true

    print_status "Cleanup completed"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Wait for service to be ready
wait_for_service() {
    local service_name=$1
    local url=$2
    local max_attempts=30
    local attempt=0

    print_status "Waiting for $service_name to be ready..."

    while [ $attempt -lt $max_attempts ]; do
        if curl -s -f "$url" > /dev/null 2>&1; then
            print_success "$service_name is ready"
            return 0
        fi

        attempt=$((attempt + 1))
        sleep 2

        if [ $((attempt % 5)) -eq 0 ]; then
            print_status "Still waiting for $service_name... (attempt $attempt/$max_attempts)"
        fi
    done

    print_error "$service_name failed to start within $((max_attempts * 2)) seconds"
    return 1
}

# Wait for external dependencies
wait_for_dependencies() {
    print_status "Checking external dependencies..."

    # Wait for NATS
    if [ ! -z "$NATS_URL" ]; then
        local nats_host=$(echo $NATS_URL | sed 's|nats://||' | cut -d: -f1)
        local nats_port=$(echo $NATS_URL | sed 's|nats://||' | cut -d: -f2)
        nats_port=${nats_port:-4222}

        print_status "Waiting for NATS at $nats_host:$nats_port..."
        while ! nc -z $nats_host $nats_port 2>/dev/null; do
            sleep 2
        done
        print_success "NATS is available"
    fi

    # Wait for Redis (optional)
    if [ ! -z "$REDIS_URL" ]; then
        local redis_host=$(echo $REDIS_URL | sed 's|redis://||' | cut -d: -f1)
        local redis_port=$(echo $REDIS_URL | sed 's|redis://||' | cut -d: -f2)
        redis_port=${redis_port:-6379}

        print_status "Waiting for Redis at $redis_host:$redis_port..."
        timeout=30
        while [ $timeout -gt 0 ] && ! nc -z $redis_host $redis_port 2>/dev/null; do
            sleep 1
            timeout=$((timeout - 1))
        done

        if [ $timeout -gt 0 ]; then
            print_success "Redis is available"
        else
            print_error "Redis is not available, continuing without session storage"
        fi
    fi
}

# Start mock services
start_mock_services() {
    print_status "Starting mock services..."

    # Start all mock services in background
    python -c "
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, '/app')

async def start_services():
    from mock_services.customer_api import create_customer_api
    from mock_services.orders_api import create_orders_api
    from mock_services.tracking_api import create_tracking_api
    import uvicorn

    # Start services on different ports
    tasks = []

    # Customer API on port 8001
    customer_config = uvicorn.Config(
        create_customer_api(),
        host='0.0.0.0',
        port=8001,
        log_level='info'
    )
    customer_server = uvicorn.Server(customer_config)
    tasks.append(customer_server.serve())

    # Orders API on port 8002
    orders_config = uvicorn.Config(
        create_orders_api(),
        host='0.0.0.0',
        port=8002,
        log_level='info'
    )
    orders_server = uvicorn.Server(orders_config)
    tasks.append(orders_server.serve())

    # Tracking API on port 8003
    tracking_config = uvicorn.Config(
        create_tracking_api(),
        host='0.0.0.0',
        port=8003,
        log_level='info'
    )
    tracking_server = uvicorn.Server(tracking_config)
    tasks.append(tracking_server.serve())

    # Run all services concurrently
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(start_services())
" &

    MOCK_SERVICES_PID=$!
    print_success "Mock services started (PID: $MOCK_SERVICES_PID)"

    # Wait for mock services to be ready
    wait_for_service "Customer API" "http://localhost:8001/health" || return 1
    wait_for_service "Orders API" "http://localhost:8002/health" || return 1
    wait_for_service "Tracking API" "http://localhost:8003/health" || return 1
}

# Start all actors
start_actors() {
    print_status "Starting all actors..."

    # Start all actors in background
    python -c "
import asyncio
import sys
import logging

# Add current directory to path
sys.path.insert(0, '/app')

# Set up logging
logging.basicConfig(level=logging.INFO)

async def start_all_actors():
    from actors.sentiment_analyzer import create_sentiment_analyzer
    from actors.intent_analyzer import create_intent_analyzer
    from actors.context_retriever import create_context_retriever
    from actors.response_generator import create_response_generator
    from actors.guardrail_validator import create_guardrail_validator
    from actors.execution_coordinator import create_execution_coordinator
    from actors.decision_router import create_decision_router
    from actors.escalation_router import create_escalation_router
    from actors.response_aggregator import create_response_aggregator

    # Create all actors
    actors = [
        create_sentiment_analyzer(),
        create_intent_analyzer(),
        create_context_retriever(),
        create_response_generator(),
        create_guardrail_validator(),
        create_execution_coordinator(),
        create_decision_router(),
        create_escalation_router(),
        create_response_aggregator(),
    ]

    # Start all actors concurrently
    tasks = [actor.start() for actor in actors]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(start_all_actors())
" &

    ACTORS_PID=$!
    print_success "All actors started (PID: $ACTORS_PID)"

    # Give actors time to initialize
    sleep 5
}

# Start API Gateway
start_gateway() {
    print_status "Starting API Gateway..."

    # Start gateway in background
    python -m api.gateway &
    GATEWAY_PID=$!

    print_success "API Gateway started (PID: $GATEWAY_PID)"

    # Wait for gateway to be ready
    wait_for_service "API Gateway" "http://localhost:8000/api/health" || return 1
}

# Initialize data directories
init_directories() {
    print_status "Initializing data directories..."

    mkdir -p /app/data /app/logs

    # Initialize SQLite database if needed
    if [ ! -f "/app/data/conversations.db" ]; then
        python -c "
import sys
sys.path.insert(0, '/app')
from storage.sqlite_client import init_sqlite
import asyncio
asyncio.run(init_sqlite())
" || true
        print_success "SQLite database initialized"
    fi
}

# Main startup sequence
main() {
    print_status "Starting E-commerce Support Agent - All-in-One Container"
    print_status "========================================================="

    # Initialize
    init_directories
    wait_for_dependencies

    # Start services in order
    if ! start_mock_services; then
        print_error "Failed to start mock services"
        exit 1
    fi

    sleep 3  # Brief pause between service groups

    if ! start_actors; then
        print_error "Failed to start actors"
        exit 1
    fi

    sleep 3  # Brief pause before gateway

    if ! start_gateway; then
        print_error "Failed to start API gateway"
        exit 1
    fi

    print_success "All services started successfully!"
    print_status ""
    print_status "Service URLs:"
    print_status "- API Gateway: http://localhost:8000"
    print_status "- Web Widget: http://localhost:8000/widget"
    print_status "- API Docs: http://localhost:8000/docs"
    print_status "- Health Check: http://localhost:8000/api/health"
    print_status "- Customer API: http://localhost:8001"
    print_status "- Orders API: http://localhost:8002"
    print_status "- Tracking API: http://localhost:8003"
    print_status ""
    print_status "System is ready! Press Ctrl+C to stop all services."

    # Wait for any service to exit or signal
    wait
}

# Run main function
main "$@"
