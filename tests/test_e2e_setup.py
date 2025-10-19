#!/usr/bin/env python3
"""
Test script to verify E2E infrastructure setup with Docker Compose.

This script:
1. Starts Docker Compose test services
2. Verifies all services are healthy
3. Runs a simple connectivity test
4. Reports results
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import httpx
import redis
import nats

# Test configuration
TEST_SERVICES = {
    "nats": {"host": "localhost", "port": 14222},
    "redis": {"host": "localhost", "port": 16379},
    "customer_api": {"host": "localhost", "port": 18001, "path": "/health"},
    "orders_api": {"host": "localhost", "port": 18002, "path": "/health"},
    "tracking_api": {"host": "localhost", "port": 18003, "path": "/health"},
}


def run_command(cmd, cwd=None, timeout=30):
    """Run a shell command and return result."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"


async def test_nats_connection():
    """Test NATS connectivity."""
    try:
        nc = await nats.connect(f"nats://{TEST_SERVICES['nats']['host']}:{TEST_SERVICES['nats']['port']}")
        await nc.close()
        return True, "NATS connection successful"
    except Exception as e:
        return False, f"NATS connection failed: {e}"


async def test_redis_connection():
    """Test Redis connectivity."""
    try:
        r = redis.Redis(
            host=TEST_SERVICES['redis']['host'],
            port=TEST_SERVICES['redis']['port'],
            decode_responses=True
        )
        r.ping()
        return True, "Redis connection successful"
    except Exception as e:
        return False, f"Redis connection failed: {e}"


async def test_http_services():
    """Test HTTP service connectivity."""
    results = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        for service_name in ["customer_api", "orders_api", "tracking_api"]:
            service_config = TEST_SERVICES[service_name]
            url = f"http://{service_config['host']}:{service_config['port']}{service_config['path']}"

            try:
                response = await client.get(url)
                if response.status_code == 200:
                    results[service_name] = (True, f"HTTP service {service_name} healthy")
                else:
                    results[service_name] = (False, f"HTTP service {service_name} returned {response.status_code}")
            except Exception as e:
                results[service_name] = (False, f"HTTP service {service_name} failed: {e}")

    return results


def start_docker_services():
    """Start Docker Compose test services."""
    project_root = Path(__file__).parent.parent
    compose_file = project_root / "docker-compose.test.yml"

    if not compose_file.exists():
        return False, "docker-compose.test.yml not found"

    print("🐳 Starting Docker Compose test services...")

    # Stop any existing services
    run_command(f"docker-compose -f {compose_file} down -v", cwd=project_root)

    # Start services
    success, stdout, stderr = run_command(
        f"docker-compose -f {compose_file} up -d", cwd=project_root, timeout=120
    )

    if not success:
        return False, f"Failed to start services: {stderr}"

    # Wait for services to be ready
    print("⏳ Waiting for services to be ready...")
    max_wait = 60
    start_time = time.time()

    while time.time() - start_time < max_wait:
        success, stdout, stderr = run_command(
            f"docker-compose -f {compose_file} ps --services --filter status=running",
            cwd=project_root
        )

        if success:
            running_services = stdout.strip().split('\n') if stdout.strip() else []
            expected_services = {'nats-test', 'redis-test', 'mock-customer-api', 'mock-orders-api', 'mock-tracking-api'}

            if all(service in running_services for service in expected_services):
                print("✅ All services are running")
                return True, "Services started successfully"

        time.sleep(2)

    # Get logs for debugging
    run_command(f"docker-compose -f {compose_file} logs", cwd=project_root)
    return False, "Services failed to start within timeout"


def stop_docker_services():
    """Stop Docker Compose test services."""
    project_root = Path(__file__).parent.parent
    compose_file = project_root / "docker-compose.test.yml"

    if compose_file.exists():
        print("🧹 Cleaning up Docker services...")
        run_command(f"docker-compose -f {compose_file} down -v", cwd=project_root)


async def main():
    """Main test function."""
    print("🚀 Starting E2E Infrastructure Test")
    print("=" * 50)

    # Check Docker availability
    docker_available, _, _ = run_command("docker --version")
    compose_available, _, _ = run_command("docker-compose --version")

    if not docker_available or not compose_available:
        print("❌ Docker or Docker Compose not available")
        return False

    # Start Docker services
    success, message = start_docker_services()
    if not success:
        print(f"❌ {message}")
        return False

    try:
        # Wait a bit more for services to fully initialize
        print("⏳ Waiting for services to initialize...")
        await asyncio.sleep(10)

        # Test connections
        print("\n🔍 Testing service connectivity...")

        # Test NATS
        nats_success, nats_message = await test_nats_connection()
        print(f"{'✅' if nats_success else '❌'} NATS: {nats_message}")

        # Test Redis
        redis_success, redis_message = await test_redis_connection()
        print(f"{'✅' if redis_success else '❌'} Redis: {redis_message}")

        # Test HTTP services
        http_results = await test_http_services()
        for service_name, (success, message) in http_results.items():
            print(f"{'✅' if success else '❌'} {service_name}: {message}")

        # Overall result
        all_success = (
            nats_success and
            redis_success and
            all(success for success, _ in http_results.values())
        )

        print("\n" + "=" * 50)
        if all_success:
            print("🎉 All E2E infrastructure tests passed!")
            print("You can now run E2E tests with: pytest tests/integration/test_system_e2e.py -v")
        else:
            print("❌ Some infrastructure tests failed")
            print("Check the service logs for more details")

        return all_success

    finally:
        # Clean up
        stop_docker_services()


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        stop_docker_services()
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        stop_docker_services()
        sys.exit(1)
