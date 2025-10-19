# Makefile for E-commerce Support Agent - Actor Mesh Demo
# Provides convenient CLI commands for running services and usage scenarios

.PHONY: help install clean start stop test test-unit test-integration test-coverage test-verbose test-e2e test-e2e-setup test-e2e-health test-e2e-angry test-e2e-happy test-e2e-performance test-e2e-resilience test-e2e-persistence test-e2e-routing test-e2e-quality test-e2e-all test-e2e-cleanup demo actors services monitor logs health web-widget demo-web

# Default target
help: ## Show this help message
	@echo "E-commerce Support Agent - Actor Mesh Demo"
	@echo "=========================================="
	@echo ""
	@echo "Available commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Usage Examples:"
	@echo "  make install       # Initial setup"
	@echo "  make start         # Start all services"
	@echo "  make demo          # Run interactive demo"
	@echo "  make test          # Run all tests"
	@echo "  make test-unit     # Run unit tests only"
	@echo "  make test-e2e      # Run E2E tests with Docker"
	@echo "  make test-e2e-fast # Run E2E tests (no setup)"
	@echo "  make test-coverage # Run tests with coverage"
	@echo "  make validate      # Validate test setup"
	@echo "  make stop          # Stop all services"

# Installation and Setup
install: ## Install dependencies and setup environment
	@echo "🚀 Setting up E-commerce Support Agent..."
	chmod +x install.sh
	./install.sh

clean: ## Clean up containers, virtual environment, and generated files
	@echo "🧹 Cleaning up..."
	docker stop nats-demo redis-demo 2>/dev/null || true
	docker rm nats-demo redis-demo 2>/dev/null || true
	rm -rf venv data logs .env __pycache__ */__pycache__ */*/__pycache__
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	find . -name "*~" -delete

# Service Management
start: start-infrastructure start-services start-actors start-gateway ## Start all services (infrastructure + services + actors + gateway)

start-infrastructure: ## Start NATS and Redis containers
	@echo "🔧 Starting infrastructure..."
	@docker rm -f nats-demo redis-demo 2>/dev/null || true
	@if ! docker ps | grep -q nats-demo; then \
		echo "Starting NATS server..."; \
		docker run -d --name nats-demo -p 4222:4222 -p 8222:8222 nats:latest -js; \
		sleep 2; \
	else \
		echo "NATS already running"; \
	fi
	@if ! docker ps | grep -q redis-demo; then \
		echo "Starting Redis server..."; \
		docker run -d --name redis-demo -p 6379:6379 redis:alpine; \
		sleep 1; \
	else \
		echo "Redis already running"; \
	fi

start-services: ## Start mock API services in background
	@echo "🌐 Starting mock services..."
	@if [ -f .env ]; then source .env; fi
	@source venv/bin/activate && \
	{ python -m mock_services.customer_api & echo $$! > .customer_api.pid; } && \
	{ python -m mock_services.orders_api & echo $$! > .orders_api.pid; } && \
	{ python -m mock_services.tracking_api & echo $$! > .tracking_api.pid; }
	@echo "Mock services started (PIDs saved)"
	@sleep 3

start-actors: ## Start all actor processes in background
	@echo "🤖 Starting actors..."
	@if [ -f .env ]; then source .env; fi
	@source venv/bin/activate && \
	{ python -m actors.sentiment_analyzer & echo $$! > .sentiment.pid; } && \
	{ python -m actors.intent_analyzer & echo $$! > .intent.pid; } && \
	{ python -m actors.context_retriever & echo $$! > .context.pid; } && \
	{ python -m actors.decision_router & echo $$! > .decision_router.pid; } && \
	{ python -m actors.response_generator & echo $$! > .response.pid; } && \
	{ python -m actors.guardrail_validator & echo $$! > .guardrail.pid; } && \
	{ python -m actors.execution_coordinator & echo $$! > .execution.pid; } && \
	{ python -m actors.escalation_router & echo $$! > .escalation_router.pid; } && \
	{ python -m actors.response_aggregator & echo $$! > .response_aggregator.pid; }
	@echo "All actors started (PIDs saved)"
	@sleep 2

start-gateway: ## Start API Gateway
	@echo "🌐 Starting API Gateway..."
	@if [ -f .env ]; then source .env; fi
	@source venv/bin/activate && \
	{ python -m api.gateway & echo $$! > .gateway.pid; }
	@echo "API Gateway started on port 8000 (PID saved)"
	@sleep 2

stop: ## Stop all services and actors
	@echo "🛑 Stopping all services..."
	@for pidfile in .*.pid; do \
		if [ -f "$$pidfile" ]; then \
			pid=$$(cat "$$pidfile"); \
			echo "Stopping process $$pid..."; \
			kill $$pid 2>/dev/null || true; \
			rm "$$pidfile"; \
		fi; \
	done
	@docker stop nats-demo redis-demo 2>/dev/null || true
	@docker rm nats-demo redis-demo 2>/dev/null || true
	@echo "All services stopped"

restart: stop start ## Restart all services

# Development and Testing
test: ## Run all tests
	@echo "🧪 Running tests..."
	@source venv/bin/activate && python tests/test_basic_flow.py

test-integration: start-infrastructure start-services ## Run integration tests with full setup
	@echo "🔬 Running integration tests..."
	@sleep 5  # Wait for services to be ready
	@source venv/bin/activate && python tests/test_basic_flow.py
	@$(MAKE) stop-services

test-actors: ## Test individual actors without NATS
	@echo "🎭 Testing individual actors..."
	@source venv/bin/activate && \
	echo "Testing SentimentAnalyzer..." && \
	timeout 5 python -m actors.sentiment_analyzer || true && \
	echo "Testing IntentAnalyzer..." && \
	timeout 5 python -m actors.intent_analyzer || true && \
	echo "Testing ContextRetriever..." && \
	timeout 5 python -m actors.context_retriever || true

# Test Setup and Validation
validate: ## Validate test environment and setup
	@echo "🔍 Validating test environment..."
	@source venv/bin/activate && python tests/test_setup_validation.py

test-setup: validate ## Alias for validate command
	@echo "✅ Test setup validation complete"

# Comprehensive Testing Framework
test-unit: ## Run unit tests only
	@echo "🧪 Running unit tests..."
	@source venv/bin/activate && python -m pytest tests/unit -v

test-unit-fast: ## Run unit tests with minimal output
	@echo "⚡ Running unit tests (fast)..."
	@source venv/bin/activate && python -m pytest tests/unit -q

test-coverage: ## Run unit tests with coverage report
	@echo "📊 Running tests with coverage..."
	@source venv/bin/activate && python -m pytest tests/unit --cov=actors --cov=models --cov=storage --cov=mock_services --cov-report=term-missing --cov-report=html

test-verbose: ## Run all tests with verbose output
	@echo "🔍 Running all tests (verbose)..."
	@source venv/bin/activate && python tests/test_runner.py --verbose

test-comprehensive: ## Run comprehensive test suite with coverage and quality checks
	@echo "🏆 Running comprehensive test suite..."
	@source venv/bin/activate && python tests/test_runner.py --verbose --coverage

test-models: ## Run tests for message models only
	@echo "📋 Testing message models..."
	@source venv/bin/activate && python -m pytest tests/unit/test_message_models.py -v

test-actors-unit: ## Run tests for actor classes only
	@echo "🎭 Testing actor classes..."
	@source venv/bin/activate && python -m pytest tests/unit/test_base_actor.py tests/unit/test_sentiment_analyzer.py -v

test-storage: ## Run tests for storage clients only
	@echo "💾 Testing storage clients..."
	@source venv/bin/activate && python -m pytest tests/unit/test_storage.py -v

test-services: ## Run tests for mock services only
	@echo "🔧 Testing mock services..."
	@source venv/bin/activate && python -m pytest tests/unit/test_mock_services.py -v

test-integration-full: start-infrastructure start-services ## Run integration tests with full system
	@echo "🔬 Running integration tests..."
	@sleep 5  # Wait for services to be ready
	@source venv/bin/activate && python -m pytest tests/integration -v
	@$(MAKE) stop-services

# E2E Testing Commands (replaces run_e2e_tests.sh functionality)
test-e2e-setup: ## Test E2E infrastructure setup only
	@echo "🔧 Testing E2E infrastructure setup..."
	@source venv/bin/activate && python tests/test_e2e_setup.py

test-e2e-health: test-e2e-setup ## Run E2E health monitoring test
	@echo "🏥 Running E2E health test..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py::TestSystemEndToEnd::test_system_health_and_monitoring -v --tb=short

test-e2e-angry: test-e2e-setup ## Run E2E angry customer flow test
	@echo "😠 Running E2E angry customer test..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py::TestSystemEndToEnd::test_complete_support_flow_angry_customer -v --tb=short

test-e2e-happy: test-e2e-setup ## Run E2E happy customer flow test
	@echo "😊 Running E2E happy customer test..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py::TestSystemEndToEnd::test_complete_support_flow_happy_customer -v --tb=short

test-e2e-performance: test-e2e-setup ## Run E2E performance test
	@echo "⚡ Running E2E performance test..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py::TestSystemEndToEnd::test_system_performance_under_load -v --tb=short

test-e2e-resilience: test-e2e-setup ## Run E2E error recovery test
	@echo "🛡️ Running E2E resilience test..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py::TestSystemEndToEnd::test_error_recovery_and_resilience -v --tb=short

test-e2e-persistence: test-e2e-setup ## Run E2E data persistence test
	@echo "💾 Running E2E persistence test..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py::TestSystemEndToEnd::test_data_persistence_and_session_management -v --tb=short

test-e2e-routing: test-e2e-setup ## Run E2E message routing test
	@echo "🔀 Running E2E routing test..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py::TestSystemEndToEnd::test_message_routing_and_flow_control -v --tb=short

test-e2e-quality: test-e2e-setup ## Run E2E response quality test
	@echo "🎯 Running E2E quality test..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py::TestSystemEndToEnd::test_end_to_end_response_quality -v --tb=short

test-e2e-all: test-e2e-setup ## Run complete E2E test suite
	@echo "🚀 Running complete E2E test suite..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py -v --tb=short

test-e2e: test-e2e-all ## Alias for test-e2e-all

test-e2e-cleanup: ## Clean up E2E Docker services
	@echo "🧹 Cleaning up E2E Docker services..."
	@docker-compose -f docker-compose.test.yml down -v 2>/dev/null || true
	@echo "✅ E2E Docker cleanup completed"

# E2E Testing with Options
test-e2e-verbose: test-e2e-setup ## Run E2E tests with verbose output
	@echo "🔍 Running E2E tests (verbose)..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py -v -s --tb=long

test-e2e-coverage: test-e2e-setup ## Run E2E tests with coverage
	@echo "📊 Running E2E tests with coverage..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py --cov=actors --cov=models --cov=storage --cov-report=term-missing -v

test-e2e-fast: ## Run E2E tests without setup validation (faster)
	@echo "⚡ Running E2E tests (fast mode)..."
	@source venv/bin/activate && python -m pytest tests/integration/test_system_e2e.py -v --tb=short

test-phase4-5: start-infrastructure ## Test Phase 4 & 5 components (routers + gateway)
	@echo "🧠 Testing Phase 4 & 5 components..."
	@source venv/bin/activate && python demo.py --mode=routing

test-routers: start-infrastructure ## Test Phase 4 router actors only
	@echo "🧭 Testing router actors..."
	@source venv/bin/activate && python demo.py --mode=routing

test-gateway: start-gateway ## Test Phase 5 API Gateway
	@echo "🌐 Testing API Gateway..."
	@sleep 2  # Allow gateway to start
	@curl -s http://localhost:8000/api/health > /dev/null && echo "✅ Gateway health check passed" || echo "❌ Gateway not running"
	@curl -s http://localhost:8000/ > /dev/null && echo "✅ Gateway root endpoint accessible" || echo "❌ Gateway root endpoint failed"

test-performance: start-infrastructure ## Run performance and load tests
	@echo "⚡ Running performance tests..."
	@source venv/bin/activate && python demo.py --mode=integration

test-all: ## Run all tests (unit + integration + system validation)
	@echo "🚀 Running all tests..."
	@$(MAKE) test-unit
	@$(MAKE) test-integration-full
	@$(MAKE) test

test-ci: ## Run tests suitable for CI/CD pipeline
	@echo "🤖 Running CI tests..."
	@source venv/bin/activate && python tests/test_runner.py --output test-results.json

test-watch: ## Run tests in watch mode (requires entr)
	@echo "👀 Running tests in watch mode..."
	@if command -v entr >/dev/null 2>&1; then \
		find . -name "*.py" | entr -c make test-unit-fast; \
	else \
		echo "Install 'entr' for watch mode: brew install entr (macOS) or apt install entr (Ubuntu)"; \
	fi

test-clean: ## Clean test artifacts and cache
	@echo "🧹 Cleaning test artifacts..."
	@rm -rf .pytest_cache htmlcov .coverage test-results.json
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true

# Demo and Usage Scenarios
demo: start-infrastructure ## Run comprehensive system demonstration
	@echo "🎬 Starting comprehensive Actor Mesh demonstration..."
	@source venv/bin/activate && python demo.py --mode=all

demo-actors: start-infrastructure ## Demo: Core actor pipeline
	@echo "🎭 Demo: Core actor pipeline processing..."
	@source venv/bin/activate && python demo.py --mode=actors

demo-routing: start-infrastructure ## Demo: Smart routing capabilities
	@echo "🧠 Demo: Smart routing and escalation logic..."
	@source venv/bin/activate && python demo.py --mode=routing

demo-integration: start-infrastructure ## Demo: Integration testing
	@echo "🔧 Demo: Integration tests and system validation..."
	@source venv/bin/activate && python demo.py --mode=integration

demo-all: start-infrastructure ## Run all demo modes in sequence
	@echo "🎭 Running complete system demonstration..."
	@$(MAKE) demo-actors
	@sleep 2
	@$(MAKE) demo-routing
	@sleep 2
	@$(MAKE) demo-web
	@sleep 2
	@$(MAKE) demo-integration

# Individual Service Management
actors: start-infrastructure ## Start only actor processes (requires infrastructure)
	@$(MAKE) start-actors

services: start-infrastructure ## Start only mock API services (requires infrastructure)
	@$(MAKE) start-services

stop-services: ## Stop only mock API services
	@echo "🛑 Stopping mock services..."
	@for pidfile in .customer_api.pid .orders_api.pid .tracking_api.pid; do \
		if [ -f "$$pidfile" ]; then \
			pid=$$(cat "$$pidfile"); \
			echo "Stopping service $$pid..."; \
			kill $$pid 2>/dev/null || true; \
			rm "$$pidfile"; \
		fi; \
	done

stop-actors: ## Stop only actor processes
	@echo "🛑 Stopping actors..."
	@for pidfile in .sentiment.pid .intent.pid .context.pid .response.pid .guardrail.pid .execution.pid; do \
		if [ -f "$$pidfile" ]; then \
			pid=$$(cat "$$pidfile"); \
			echo "Stopping actor $$pid..."; \
			kill $$pid 2>/dev/null || true; \
			rm "$$pidfile"; \
		fi; \
	done

# Monitoring and Debugging
status: ## Show status of all services
	@echo "📊 Service Status:"
	@echo "=================="
	@echo "Docker containers:"
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(nats-demo|redis-demo)" || echo "No containers running"
	@echo ""
	@echo "Process PIDs:"
	@for pidfile in .*.pid; do \
		if [ -f "$$pidfile" ]; then \
			pid=$$(cat "$$pidfile"); \
			name=$$(basename "$$pidfile" .pid | sed 's/^\.//'); \
			if ps -p $$pid > /dev/null 2>&1; then \
				echo "✅ $$name (PID: $$pid)"; \
			else \
				echo "❌ $$name (PID: $$pid - not running)"; \
				rm "$$pidfile"; \
			fi; \
		fi; \
	done

health: ## Check health of all services
	@echo "🏥 Health Check:"
	@echo "================"
	@printf "NATS Server: "
	@curl -s http://localhost:8222/healthz > /dev/null 2>&1 && echo "✅ Healthy" || echo "❌ Unhealthy"
	@printf "Redis Server: "
	@redis-cli -h localhost -p 6379 ping 2>/dev/null | grep -q PONG && echo "✅ Healthy" || echo "❌ Unhealthy"
	@printf "Customer API: "
	@curl -s http://localhost:8001/health > /dev/null 2>&1 && echo "✅ Healthy" || echo "❌ Unhealthy"
	@printf "Orders API: "
	@curl -s http://localhost:8002/health > /dev/null 2>&1 && echo "✅ Healthy" || echo "❌ Unhealthy"
	@printf "Tracking API: "
	@curl -s http://localhost:8003/health > /dev/null 2>&1 && echo "✅ Healthy" || echo "❌ Unhealthy"
	@printf "API Gateway: "
	@curl -s http://localhost:8000/api/health > /dev/null 2>&1 && echo "✅ Healthy" || echo "❌ Unhealthy"

monitor: ## Open monitoring dashboards
	@echo "🖥️  Opening monitoring dashboards..."
	@echo "NATS Monitoring: http://localhost:8222"
	@echo "API Gateway: http://localhost:8000/docs"
	@echo "API Gateway Health: http://localhost:8000/api/health"
	@echo "Customer API: http://localhost:8001/docs"
	@echo "Orders API: http://localhost:8002/docs"
	@echo "Tracking API: http://localhost:8003/docs"
	@if command -v open >/dev/null 2>&1; then \
		open http://localhost:8222; \
		open http://localhost:8001/docs; \
		open http://localhost:8002/docs; \
		open http://localhost:8003/docs; \
	elif command -v xdg-open >/dev/null 2>&1; then \
		xdg-open http://localhost:8222; \
		xdg-open http://localhost:8001/docs; \
		xdg-open http://localhost:8002/docs; \
		xdg-open http://localhost:8003/docs; \
	else \
		echo "Please open the URLs manually in your browser"; \
	fi

logs: ## Show logs from all services
	@echo "📋 Service Logs:"
	@echo "================"
	@echo "Docker logs (NATS):"
	@docker logs nats-demo --tail 10 2>/dev/null || echo "NATS not running"
	@echo ""
	@echo "Docker logs (Redis):"
	@docker logs redis-demo --tail 10 2>/dev/null || echo "Redis not running"
	@echo ""
	@echo "Application logs:"
	@tail -20 logs/*.log 2>/dev/null || echo "No application logs found"

# Configuration and Environment
config: ## Show current configuration
	@echo "⚙️  Current Configuration:"
	@echo "========================="
	@if [ -f .env ]; then \
		echo "Environment file (.env):"; \
		cat .env | grep -v "API_KEY" | grep -v "PASSWORD"; \
		echo ""; \
	fi
	@echo "Python version:"
	@source venv/bin/activate && python --version
	@echo ""
	@echo "Installed packages:"
	@source venv/bin/activate && pip list | grep -E "(fastapi|nats|redis|litellm|pydantic)"

setup-env: ## Setup environment variables interactively
	@echo "🔧 Setting up environment variables..."
	@if [ ! -f .env ]; then cp .env.example .env 2>/dev/null || true; fi
	@echo "Please edit .env file to configure:"
	@echo "- LLM API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY)"
	@echo "- Model preferences (LITELLM_MODEL)"
	@echo "- Log levels and other settings"
	@echo ""
	@echo "Opening .env file..."
	@${EDITOR:-nano} .env

# Development Helpers
dev-setup: install setup-env ## Complete development setup
	@echo "🛠️  Development setup complete!"
	@echo "Next steps:"
	@echo "1. Configure API keys in .env"
	@echo "2. Run 'make start' to start all services"
	@echo "3. Run 'make demo' for interactive demo"

quick-start: install start demo ## One-command quick start (install, start, demo)

format: ## Format code using black and isort
	@echo "🎨 Formatting code..."
	@source venv/bin/activate && \
	black --line-length 100 . && \
	isort --profile black .

lint: ## Run linting checks
	@echo "🔍 Running linting checks..."
	@source venv/bin/activate && \
	flake8 --max-line-length 100 --ignore E203,W503 . && \
	mypy --ignore-missing-imports .

quality: ## Run code quality checks (format + lint + test)
	@echo "🏆 Running comprehensive quality checks..."
	@make format
	@make lint
	@make test-unit

validate-system: ## Validate entire system (quality + integration tests)
	@echo "✅ Running full system validation..."
	@make quality
	@make test-integration
	@make test-basic

# Docker and Deployment
docker-build: ## Build Docker images
	@echo "🐳 Building Docker images..."
	docker build -t ecommerce-agent:latest .

docker-run: ## Run with Docker Compose
	@echo "🐳 Running with Docker Compose..."
	docker-compose up -d

docker-stop: ## Stop Docker Compose services
	@echo "🐳 Stopping Docker Compose..."
	docker-compose down

k8s-deploy: ## Deploy to Kubernetes
	@echo "☸️  Deploying to Kubernetes..."
	kubectl apply -f k8s/

k8s-status: ## Check Kubernetes deployment status
	@echo "☸️  Kubernetes Status:"
	kubectl get pods -l app=ecommerce-agent
	kubectl get services -l app=ecommerce-agent

# Cleanup helpers
clean-logs: ## Clean log files
	@echo "🧹 Cleaning logs..."
	rm -rf logs/*.log

clean-data: ## Clean data files
	@echo "🧹 Cleaning data..."
	rm -rf data/*

reset: clean install ## Complete reset (clean + reinstall)

# Performance and Load Testing
load-test: start ## Run load test against the system
	@echo "⚡ Running load test..."
	@source venv/bin/activate && python -c "\
import asyncio; \
import aiohttp; \
import time; \
async def send_request(): \
    async with aiohttp.ClientSession() as session: \
        async with session.get('http://localhost:8001/health') as resp: \
            return await resp.text(); \
async def load_test(): \
    tasks = []; \
    start_time = time.time(); \
    for i in range(50): \
        task = asyncio.create_task(send_request()); \
        tasks.append(task); \
    results = await asyncio.gather(*tasks, return_exceptions=True); \
    end_time = time.time(); \
    successful = len([r for r in results if not isinstance(r, Exception)]); \
    failed = len(results) - successful; \
    print(f'Load test completed in {end_time - start_time:.2f} seconds'); \
    print(f'Successful requests: {successful}'); \
    print(f'Failed requests: {failed}'); \
    print(f'Requests per second: {len(results) / (end_time - start_time):.2f}'); \
asyncio.run(load_test()); \
"

# Utility targets
check-deps: ## Check if all dependencies are installed
	@echo "🔍 Checking dependencies..."
	@command -v docker >/dev/null 2>&1 || echo "❌ Docker not installed"
	@command -v python3 >/dev/null 2>&1 || echo "❌ Python 3 not installed"
	@command -v curl >/dev/null 2>&1 || echo "❌ curl not installed"
	@command -v redis-cli >/dev/null 2>&1 || echo "⚠️  redis-cli not installed (optional)"
	@[ -d venv ] && echo "✅ Virtual environment exists" || echo "❌ Virtual environment not found"
	@[ -f pyproject.toml ] && echo "✅ Project configuration file exists" || echo "❌ pyproject.toml not found"

ports: ## Show which ports are in use
	@echo "🌐 Port Usage:"
	@echo "=============="
	@echo "Port 4222 (NATS client):"
	@lsof -i :4222 || echo "  Not in use"
	@echo "Port 8222 (NATS monitoring):"
	@lsof -i :8222 || echo "  Not in use"
	@echo "Port 6379 (Redis):"
	@lsof -i :6379 || echo "  Not in use"
	@echo "Port 8000 (API Gateway):"
	@lsof -i :8000 || echo "  Not in use"
	@echo "Port 8001 (Customer API):"
	@lsof -i :8001 || echo "  Not in use"
	@echo "Port 8002 (Orders API):"
	@lsof -i :8002 || echo "  Not in use"
	@echo "Port 8003 (Tracking API):"
	@lsof -i :8003 || echo "  Not in use"

# Help and documentation
docs: ## Open documentation
	@echo "📖 Opening documentation..."
	@if command -v open >/dev/null 2>&1; then \
		open README.md; \
	elif command -v xdg-open >/dev/null 2>&1; then \
		xdg-open README.md; \
	else \
		echo "Please open README.md manually"; \
	fi

examples: ## Show usage examples
	@echo "💡 Usage Examples:"
	@echo "=================="
	@echo ""
	@echo "Quick Start:"
	@echo "  make quick-start          # Install, start, and run demo"
	@echo ""
	@echo "Development Workflow:"
	@echo "  make install              # Initial setup"
	@echo "  make dev-setup           # Complete dev environment"
	@echo "  make start               # Start all services"
	@echo "  make test                # Run tests"
	@echo "  make demo                # Interactive demo"
	@echo "  make stop                # Stop everything"
	@echo ""
	@echo "Individual Components:"
	@echo "  make start-infrastructure # Only NATS + Redis"
	@echo "  make services            # Only mock APIs"
	@echo "  make actors              # Only actor processes"
	@echo ""
	@echo "Demo Scenarios:"
	@echo "  make demo                # Interactive demo"
	@echo "  make demo-angry          # Angry customer scenario"
	@echo "  make demo-inquiry        # Polite inquiry scenario"
	@echo "  make demo-return         # Return request scenario"
	@echo "  make demo-phase4-5       # Phase 4 & 5 components demo"
	@echo "  make demo-all            # All scenarios"
	@echo ""
	@echo "Monitoring:"
	@echo "  make status              # Check service status"
	@echo "  make health              # Health checks"
	@echo "  make monitor             # Open dashboards"
	@echo "  make logs                # View logs"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean               # Clean everything"
	@echo "  make reset               # Clean + reinstall"
	@echo "  make restart             # Restart all services"
	@echo ""
	@echo "🌐 Phase 6 - Web Interface:"
	@echo "  make web-widget          # Open web chat widget"
	@echo "  make demo-web            # Phase 6 web demo"
	@echo "  make test-phase6         # Test web interface"

# Phase 6: Web Interface Commands
web-widget: start-gateway ## Open web chat widget in browser
	@echo "🌐 Opening web chat widget..."
	@sleep 2
	@echo "Main widget: http://localhost:8000/widget"
	@echo "Enhanced widget: http://localhost:8000/static/chat.html"
	@echo "API docs: http://localhost:8000/docs"
	@if command -v python3 >/dev/null 2>&1; then \
		python3 -c "import webbrowser; webbrowser.open('http://localhost:8000/widget')"; \
	fi

demo-web: start-infrastructure start-gateway ## Run web interface demonstration
	@echo "🌐 Running Web Interface Demo..."
	@echo "This demonstrates real-time web chat widget and WebSocket functionality"
	@if [ ! -f venv/bin/activate ]; then $(MAKE) install; fi
	@. venv/bin/activate && python demo.py --mode=web

test-phase6: start-infrastructure start-gateway ## Test web interface functionality
	@echo "🧪 Testing Web Interface..."
	@if [ ! -f venv/bin/activate ]; then $(MAKE) install; fi
	@. venv/bin/activate && python -m pytest tests/test_phase6_web.py -v --tb=short

test-web: test-phase6 ## Alias for web interface tests

# Default make target
.DEFAULT_GOAL := help
