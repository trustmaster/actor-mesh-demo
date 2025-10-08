# Makefile Usage Guide

This guide explains how to use the comprehensive Makefile provided with the E-commerce Support Agent Actor Mesh Demo.

## Quick Reference

```bash
make help          # Show all available commands
make quick-start   # One-command setup: install + start + demo
make examples      # Show detailed usage examples
```

## Installation & Setup

### Initial Setup
```bash
make install       # Install dependencies and setup environment
make setup-env     # Configure API keys interactively
make dev-setup     # Complete development setup (install + setup-env)
```

### Environment Management
```bash
make config        # Show current configuration
make check-deps    # Verify all dependencies are installed
make clean         # Remove containers, venv, and generated files
make reset         # Complete reset (clean + reinstall)
```

## Service Management

### Starting Services
```bash
make start                 # Start everything (infrastructure + APIs + actors)
make start-infrastructure  # Start only NATS and Redis containers
make start-services        # Start only mock API services
make start-actors          # Start only actor processes
```

### Stopping Services
```bash
make stop          # Stop all services and containers
make stop-services # Stop only mock API services
make stop-actors   # Stop only actor processes
make restart       # Stop and start all services
```

### Service Status
```bash
make status        # Show process PIDs and container status
make health        # Check health of all services
make ports         # Show which ports are in use
make logs          # View service logs
```

## Demo & Testing

### Interactive Demos
```bash
make demo          # Full interactive demo with all scenarios
make demo-angry    # Quick angry customer scenario
make demo-inquiry  # Quick polite inquiry scenario  
make demo-return   # Quick return request scenario
make demo-all      # Run all quick scenarios in sequence
```

### Testing
```bash
make test              # Run basic functionality tests
make test-integration  # Run full integration tests with services
make test-actors       # Test individual actors without NATS
make load-test         # Performance/load testing
```

## Monitoring & Debugging

### Monitoring Tools
```bash
make monitor       # Open all monitoring dashboards in browser
make logs          # View recent logs from all services
make config        # Show current configuration
```

### Debugging
```bash
make status        # Check which services are running
make health        # Health check all endpoints
make ports         # Check for port conflicts
```

### Monitoring URLs
When services are running:
- **NATS Monitoring**: http://localhost:8222
- **Customer API Docs**: http://localhost:8001/docs
- **Orders API Docs**: http://localhost:8002/docs
- **Tracking API Docs**: http://localhost:8003/docs

## Development Workflow

### Typical Development Session
```bash
# 1. Initial setup (first time only)
make dev-setup

# 2. Start development environment
make start

# 3. Run tests during development
make test

# 4. Test specific scenarios
make demo-angry
make demo-inquiry

# 5. Check status and health
make status
make health

# 6. Stop when done
make stop
```

### Code Quality
```bash
make format        # Format code with black and isort
make lint          # Run linting checks with flake8 and mypy
```

## Deployment

### Docker
```bash
make docker-build  # Build Docker images
make docker-run    # Run with docker-compose
make docker-stop   # Stop docker-compose services
```

### Kubernetes
```bash
make k8s-deploy    # Deploy to Kubernetes cluster
make k8s-status    # Check Kubernetes deployment status
```

## Troubleshooting

### Common Issues

**Services won't start:**
```bash
make ports         # Check for port conflicts
make clean         # Clean old processes/containers
make install       # Reinstall if needed
```

**Docker container issues:**
```bash
docker ps          # Check running containers
docker logs nats-demo    # Check NATS logs
docker logs redis-demo   # Check Redis logs
```

**API connection errors:**
```bash
make health        # Check service health
make status        # Verify all services are running
make start-services # Restart API services if needed
```

**LLM/API key errors:**
```bash
make setup-env     # Configure environment variables
# Then edit .env file with your API keys
```

**Complete reset (nuclear option):**
```bash
make reset         # Clean everything and reinstall
```

## Service Architecture

### Infrastructure Services
- **NATS** (Port 4222): Message broker for actor communication
- **Redis** (Port 6379): Session state and caching

### Mock API Services  
- **Customer API** (Port 8001): Customer profile data
- **Orders API** (Port 8002): Order management
- **Tracking API** (Port 8003): Shipping and tracking info

### Actor Processes
- **SentimentAnalyzer**: Analyzes customer sentiment and urgency
- **IntentAnalyzer**: Classifies intent using LLM or rules
- **ContextRetriever**: Fetches customer context from APIs
- **ResponseGenerator**: Generates responses using LLM or templates
- **GuardrailValidator**: Validates responses for safety/policy
- **ExecutionCoordinator**: Executes approved actions via APIs

## Environment Variables

Key environment variables (configured in `.env`):

```bash
# NATS Configuration
NATS_URL=nats://localhost:4222

# API Endpoints  
CUSTOMER_API_URL=http://localhost:8001
ORDERS_API_URL=http://localhost:8002
TRACKING_API_URL=http://localhost:8003

# Redis (optional)
REDIS_URL=redis://localhost:6379

# LLM Configuration
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
LITELLM_MODEL=gpt-3.5-turbo

# Logging
LOG_LEVEL=INFO
```

## Advanced Usage

### Running Individual Components

Start only what you need for development:

```bash
# Just infrastructure for testing actors
make start-infrastructure

# Add mock APIs for integration testing  
make services

# Add actors for full system
make actors
```

### Performance Testing
```bash
# Start services first
make start

# Run load test
make load-test

# Monitor during test
make status
make health
```

### Custom Scenarios

You can create custom demo scenarios by editing `demo.py` or calling the actors directly:

```bash
# Activate virtual environment first
source venv/bin/activate

# Run individual actors for testing
python -m actors.sentiment_analyzer
python -m actors.intent_analyzer

# Or run custom demo scenarios
python demo.py
```

## Best Practices

### Development
1. Always use `make status` to check what's running
2. Use `make health` to verify service connectivity
3. Run `make test` before committing changes
4. Use `make clean` to resolve mysterious issues

### Debugging
1. Check logs with `make logs`
2. Verify ports with `make ports`  
3. Use `make monitor` to open all dashboards
4. Test individual components before full integration

### Production
1. Use `make docker-build` and `make docker-run` for containerized deployment
2. Use `make k8s-deploy` for Kubernetes deployment
3. Monitor with `make health` and external monitoring tools
4. Configure proper API keys and external service URLs

## Getting Help

```bash
make help          # List all available commands
make examples      # Show usage examples  
make docs          # Open documentation
```

For more detailed information, see:
- `README.md` - Complete project documentation
- `QUICKSTART.md` - Quick start guide
- `IMPLEMENTATION_SUMMARY.md` - Technical details

## Example Workflows

### Quick Demo (5 minutes)
```bash
make quick-start   # Install, start, and demo everything
```

### Development Setup (first time)
```bash
make install       # Install dependencies
make setup-env     # Configure API keys
make start         # Start all services
make test          # Verify everything works
make demo          # Try the demo
```

### Daily Development
```bash
make start         # Start services
make test          # Run tests
# ... develop and test ...
make stop          # Stop when done
```

### Troubleshooting Session
```bash
make status        # What's running?
make health        # What's broken?
make logs          # What happened?
make restart       # Try turning it off and on again
make reset         # Nuclear option
```

This Makefile provides a complete development and deployment toolkit for the Actor Mesh demo. All commands are designed to be safe, idempotent, and provide clear feedback about what's happening.