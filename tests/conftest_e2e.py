"""
E2E test configuration with Docker Compose infrastructure setup.

This module provides fixtures and utilities for running end-to-end tests
with real infrastructure services (NATS, Redis, Mock APIs) via Docker Compose.
"""

import asyncio
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Any
import pytest
import pytest_asyncio
from unittest.mock import patch

# Test environment configuration
TEST_ENV_CONFIG = {
    "NATS_URL": "nats://localhost:14222",
    "REDIS_URL": "redis://localhost:16379",
    "CUSTOMER_API_URL": "http://localhost:18001",
    "ORDERS_API_URL": "http://localhost:18002",
    "TRACKING_API_URL": "http://localhost:18003",
    "LOG_LEVEL": "INFO",
    "LITELLM_MODEL": "gpt-3.5-turbo",
    "SENTIMENT_CONFIDENCE_THRESHOLD": "0.7",
    "INTENT_TIMEOUT": "30",
    "RESPONSE_TEMPERATURE": "0.3",
    "USE_LLM_VALIDATION": "true",
}


@pytest_asyncio.fixture(scope="session")
async def docker_services():
    """
    Start Docker Compose services for testing and ensure they're healthy.
    """
    project_root = Path(__file__).parent.parent
    compose_file = project_root / "docker-compose.test.yml"

    if not compose_file.exists():
        pytest.skip("docker-compose.test.yml not found")

    # Check if Docker is available
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
        subprocess.run(["docker-compose", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker or Docker Compose not available")

    print("Starting Docker Compose test services...")

    # Start services
    try:
        result = subprocess.run([
            "docker-compose", "-f", str(compose_file), "up", "-d"
        ], cwd=project_root, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            print(f"Docker Compose up failed: {result.stderr}")
            pytest.skip("Failed to start Docker Compose services")

    except subprocess.TimeoutExpired:
        pytest.skip("Docker Compose services failed to start within timeout")

    # Wait for services to be healthy
    print("Waiting for services to be healthy...")
    max_wait = 60  # seconds
    start_time = time.time()

    services_healthy = False
    while time.time() - start_time < max_wait:
        try:
            # Check service health
            health_result = subprocess.run([
                "docker-compose", "-f", str(compose_file), "ps", "--format", "json"
            ], cwd=project_root, capture_output=True, text=True)

            if health_result.returncode == 0:
                import json
                services = []
                for line in health_result.stdout.strip().split('\n'):
                    if line.strip():
                        try:
                            service_info = json.loads(line)
                            if service_info.get('Health') == 'healthy' or 'healthy' in service_info.get('Status', ''):
                                services.append(service_info['Service'])
                        except json.JSONDecodeError:
                            continue

                expected_services = {'nats-test', 'redis-test', 'mock-customer-api', 'mock-orders-api', 'mock-tracking-api'}
                if len(services) >= len(expected_services):
                    services_healthy = True
                    break

        except subprocess.CalledProcessError:
            pass

        await asyncio.sleep(2)

    if not services_healthy:
        print("Service health check failed")
        # Cleanup
        subprocess.run([
            "docker-compose", "-f", str(compose_file), "down", "-v"
        ], cwd=project_root)
        pytest.skip("Docker services failed to become healthy")

    print("All services are healthy!")

    # Yield control to tests
    try:
        yield {
            "nats_url": TEST_ENV_CONFIG["NATS_URL"],
            "redis_url": TEST_ENV_CONFIG["REDIS_URL"],
            "customer_api_url": TEST_ENV_CONFIG["CUSTOMER_API_URL"],
            "orders_api_url": TEST_ENV_CONFIG["ORDERS_API_URL"],
            "tracking_api_url": TEST_ENV_CONFIG["TRACKING_API_URL"],
        }
    finally:
        # Cleanup services
        print("Cleaning up Docker Compose test services...")
        try:
            subprocess.run([
                "docker-compose", "-f", str(compose_file), "down", "-v"
            ], cwd=project_root, timeout=30)
        except subprocess.TimeoutExpired:
            print("Timeout during cleanup, forcing removal...")
            subprocess.run([
                "docker-compose", "-f", str(compose_file), "kill"
            ], cwd=project_root)


@pytest_asyncio.fixture
async def e2e_environment(docker_services):
    """
    Set up environment variables for E2E testing with real services.
    """
    # Patch environment variables
    with patch.dict(os.environ, TEST_ENV_CONFIG):
        yield docker_services


@pytest_asyncio.fixture
async def redis_client_e2e(e2e_environment):
    """
    Create a real Redis client connected to test Redis instance.
    """
    from storage.redis_client import RedisClient

    client = RedisClient(redis_url=TEST_ENV_CONFIG["REDIS_URL"])
    await client.connect()

    try:
        yield client
    finally:
        await client.disconnect()


@pytest_asyncio.fixture
async def clean_test_data(redis_client_e2e):
    """
    Clean test data before and after each test.
    """
    # Clean before test
    try:
        await redis_client_e2e.flushdb()
    except Exception:
        pass  # Ignore if Redis is not ready

    yield

    # Clean after test
    try:
        await redis_client_e2e.flushdb()
    except Exception:
        pass


@pytest_asyncio.fixture
async def healthy_services(e2e_environment):
    """
    Ensure all external services are healthy before running tests.
    """
    import httpx

    service_urls = {
        "customer_api": e2e_environment["customer_api_url"],
        "orders_api": e2e_environment["orders_api_url"],
        "tracking_api": e2e_environment["tracking_api_url"],
    }

    # Verify services are responding
    async with httpx.AsyncClient(timeout=10.0) as client:
        for service_name, url in service_urls.items():
            try:
                health_url = f"{url}/health"
                response = await client.get(health_url)
                if response.status_code != 200:
                    pytest.skip(f"Service {service_name} is not healthy")
            except Exception as e:
                pytest.skip(f"Service {service_name} is not responding: {e}")

    yield service_urls


# Test markers for E2E tests
pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_redis,
    pytest.mark.requires_nats,
    pytest.mark.requires_services,
]
