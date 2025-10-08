# Multi-stage Dockerfile for E-commerce Support Agent Actor Mesh Demo
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set work directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml README.md ./

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Development stage
FROM base as development
RUN pip install --no-cache-dir -e ".[dev,test]"
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "-m", "api.gateway"]

# Production stage
FROM base as production

# Copy application code
COPY actors/ ./actors/
COPY api/ ./api/
COPY models/ ./models/
COPY mock_services/ ./mock_services/
COPY storage/ ./storage/
COPY web/ ./web/
COPY __init__.py ./

# Create necessary directories
RUN mkdir -p data logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Default command (can be overridden)
EXPOSE 8000
CMD ["python", "-m", "api.gateway"]

# Gateway stage - API Gateway service
FROM production as gateway
EXPOSE 8000
CMD ["python", "-m", "api.gateway"]

# Actor stage - Individual actor services
FROM production as actor
CMD ["python", "-c", "import sys; print('Specify actor module as CMD argument'); sys.exit(1)"]

# Mock services stage
FROM production as mock-services
EXPOSE 8001 8002 8003
CMD ["python", "-c", "import asyncio; from mock_services import run_all_services; asyncio.run(run_all_services())"]

# All-in-one stage for development/testing
FROM production as allinone
EXPOSE 8000 8001 8002 8003
COPY docker/start-all.sh /app/start-all.sh
RUN chmod +x /app/start-all.sh
CMD ["/app/start-all.sh"]
