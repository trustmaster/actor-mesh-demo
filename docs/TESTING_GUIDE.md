# Testing Guide - Actor Mesh E-commerce Support Agent

This guide provides comprehensive information about testing the Actor Mesh E-commerce Support Agent system, including unit tests, integration tests, and system validation.

## Overview

The testing framework includes:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions and message flow
- **End-to-End Tests**: Test complete system workflows
- **Performance Tests**: Test system performance and scalability
- **Mock Infrastructure**: Comprehensive mocking of external dependencies

## Quick Start

```bash
# Validate test environment
python test_setup_validation.py

# Run all tests
make test

# Run specific test categories
make test-unit              # Unit tests only
make test-integration       # Integration tests with mocked infrastructure
make test-coverage          # Tests with coverage report
```

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Shared pytest fixtures and configuration
├── test_runner.py           # Comprehensive test runner script
├── fixtures/                # Test data and utilities
├── unit/                    # Unit tests
│   ├── test_message_models.py
│   ├── test_base_actor.py
│   ├── test_sentiment_analyzer.py
│   ├── test_storage.py
│   └── test_mock_services.py
└── integration/             # Integration tests
    ├── test_actor_flow.py
    └── test_system_e2e.py
```

## Test Categories

### Unit Tests (`tests/unit/`)

Test individual components in isolation with comprehensive mocking.

#### Message Models (`test_message_models.py`)
- MessagePayload creation and serialization
- Route navigation and advancement
- Message factory functions
- StandardRoutes validation
- Error handling and edge cases

```bash
# Run message model tests
make test-models
pytest tests/unit/test_message_models.py -v
```

#### Base Actor Framework (`test_base_actor.py`)
- BaseActor initialization and lifecycle
- NATS connection and message handling
- Error handling and retry logic
- ProcessorActor and RouterActor inheritance
- Actor utility functions

```bash
# Run actor framework tests
make test-actors-unit
pytest tests/unit/test_base_actor.py -v
```

#### Sentiment Analyzer (`test_sentiment_analyzer.py`)
- Rule-based sentiment analysis
- Urgency detection algorithms
- Complaint classification
- Keyword extraction and matching
- Performance and edge cases

```bash
# Run sentiment analyzer tests
pytest tests/unit/test_sentiment_analyzer.py -v
```

#### Storage Clients (`test_storage.py`)
- Redis client operations (sessions, context, counters)
- SQLite client functionality
- Connection management and health checks
- Error handling and recovery
- Data consistency validation

```bash
# Run storage tests
make test-storage
pytest tests/unit/test_storage.py -v
```

#### Mock Services (`test_mock_services.py`)
- Customer API functionality
- Orders API operations
- Tracking API responses
- HTTP endpoint testing
- Data structure validation

```bash
# Run mock services tests
make test-services
pytest tests/unit/test_mock_services.py -v
```

### Integration Tests (`tests/integration/`)

Test component interactions and system workflows with mocked infrastructure.

#### Actor Message Flow (`test_actor_flow.py`)
- Actor-to-actor communication via NATS
- Message routing and enrichment
- Error handling in distributed flow
- Concurrent message processing
- Performance under load

#### System End-to-End (`test_system_e2e.py`)
- Complete customer support workflows
- Multi-actor message processing
- Error recovery and resilience
- Data persistence and session management
- System health and monitoring

```bash
# Run integration tests
make test-integration-full
pytest tests/integration/ -v
```

## Test Runner

The comprehensive test runner (`tests/test_runner.py`) provides advanced testing capabilities:

### Features

- **Dependency Checking**: Validates required packages and tools
- **Project Structure Validation**: Ensures correct file organization
- **Test Execution**: Runs tests with detailed reporting
- **Coverage Analysis**: Generates coverage reports
- **Performance Tests**: Load testing and benchmarking
- **Code Quality**: Integration with linting and formatting tools

### Usage

```bash
# Run comprehensive test suite
python tests/test_runner.py --verbose --coverage

# Run specific test categories
python tests/test_runner.py --unit-only
python tests/test_runner.py --integration-only

# Save detailed results
python tests/test_runner.py --coverage --output test-results.json

# Skip code quality checks
python tests/test_runner.py --skip-quality
```

### Output

The test runner provides detailed reporting:

```
============================================================
Actor Mesh E-commerce Support Agent - Test Suite
============================================================

📦 Checking Dependencies
✓ pytest is available
✓ pytest-asyncio is available
✓ All dependencies are available

📁 Checking Project Structure
✓ models/
✓ actors/
✓ storage/
✓ tests/
✓ Project structure is correct

🧪 Running Unit Tests
Found 5 unit test files:
  - test_message_models.py
  - test_base_actor.py
  - test_sentiment_analyzer.py
  - test_storage.py
  - test_mock_services.py

Unit Test Results:
  Total: 125
  Passed: 123
  Failed: 0
  Skipped: 2
  Errors: 0
  Duration: 12.45s
  Status: ✓ PASSED

📊 Coverage Report
Overall Coverage: 87.3%
Lines Covered: 1,247
Lines Missing: 181
Total Lines: 1,428

Per-Module Coverage:
  message_models: 95.2%
  base_actor: 89.1%
  sentiment_analyzer: 91.7%
  redis_client: 82.4%
  customer_api: 88.9%

✅ ALL TESTS PASSED
```

## Test Configuration

### pytest.ini

```ini
[tool:pytest]
minversion = 6.0
addopts = -ra -q --strict-markers --strict-config
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
    requires_redis: Tests that require Redis
    requires_nats: Tests that require NATS
    requires_llm: Tests that require LLM API keys
asyncio_mode = auto
timeout = 30
```

### Test Markers

Use markers to run specific test subsets:

```bash
# Run only unit tests
pytest -m "unit"

# Run integration tests
pytest -m "integration"

# Skip slow tests
pytest -m "not slow"

# Run tests that require external services
pytest -m "requires_redis or requires_nats"
```

## Mock Infrastructure

### NATS Mocking

```python
@pytest.fixture
def mock_nats_environment():
    """Mock NATS connection and JetStream."""
    mock_nc = AsyncMock()
    mock_js = AsyncMock()
    mock_js.publish = AsyncMock()
    mock_js.subscribe = AsyncMock()
    
    with patch("nats.connect", return_value=mock_nc):
        yield {"nc": mock_nc, "js": mock_js}
```

### Redis Mocking

```python
@pytest.fixture
def mock_redis_client():
    """Mock Redis client operations."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.ping = AsyncMock(return_value=True)
    return mock_redis
```

### LLM API Mocking

```python
@pytest.fixture
def mock_llm_responses():
    """Mock LLM API responses."""
    def mock_completion(*args, **kwargs):
        response_data = {"intent": {"category": "order_inquiry"}}
        return MagicMock(
            choices=[MagicMock(
                message=MagicMock(content=json.dumps(response_data))
            )]
        )
    
    with patch("litellm.acompletion", side_effect=mock_completion):
        yield
```

## Performance Testing

### Load Testing

```bash
# Run performance tests
make test-performance

# Custom load test
python -c "
import asyncio
from actors.sentiment_analyzer import SentimentAnalyzer
from models.message import MessagePayload

async def load_test():
    analyzer = SentimentAnalyzer()
    messages = [
        MessagePayload(
            customer_message=f'Load test message {i}',
            customer_email=f'test{i}@example.com'
        ) for i in range(100)
    ]
    
    import time
    start = time.time()
    tasks = [analyzer.process(msg) for msg in messages]
    await asyncio.gather(*tasks)
    duration = time.time() - start
    
    print(f'Processed {len(messages)} messages in {duration:.2f}s')
    print(f'Throughput: {len(messages)/duration:.1f} msg/s')

asyncio.run(load_test())
"
```

### Benchmarking

Test specific components for performance:

```python
@pytest.mark.performance
async def test_sentiment_analyzer_performance():
    """Test sentiment analyzer performance."""
    analyzer = SentimentAnalyzer()
    payload = MessagePayload(
        customer_message="Performance test message",
        customer_email="perf@example.com"
    )
    
    import time
    start_time = time.time()
    
    for _ in range(1000):
        await analyzer.process(payload)
    
    duration = time.time() - start_time
    assert duration < 5.0  # Should process 1000 messages in under 5 seconds
```

## Coverage Reports

### Generate Coverage

```bash
# HTML coverage report
make test-coverage
open htmlcov/index.html

# Terminal coverage report
pytest --cov=actors --cov=models --cov=storage --cov-report=term-missing

# JSON coverage for CI/CD
pytest --cov=actors --cov-report=json
```

### Coverage Targets

- **Overall Coverage**: Target 85%+
- **Critical Paths**: Target 95%+
- **New Code**: Target 90%+

## Continuous Integration

### CI/CD Pipeline

```yaml
# Example GitHub Actions workflow
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, 3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest-cov
    
    - name: Validate setup
      run: python test_setup_validation.py
    
    - name: Run tests
      run: python tests/test_runner.py --ci
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
- repo: local
  hooks:
  - id: tests
    name: run-tests
    entry: make test-unit-fast
    language: system
    pass_filenames: false
```

## Test Data and Fixtures

### Sample Test Data

Common test data is provided via fixtures in `conftest.py`:

```python
@pytest.fixture
def sample_customer_messages():
    """Sample customer messages for testing."""
    return [
        {
            "customer_email": "angry.customer@example.com",
            "message": "I'm furious about my delayed order!",
            "expected_sentiment": "negative",
            "expected_urgency": "high",
        },
        {
            "customer_email": "happy.customer@example.com", 
            "message": "Thank you for excellent service!",
            "expected_sentiment": "positive",
            "expected_urgency": "low",
        }
    ]
```

### Test Utilities

```python
def create_test_message(message="Test", email="test@example.com"):
    """Utility to create test messages."""
    return create_support_message(
        customer_message=message,
        customer_email=email,
        session_id=f"test-{uuid.uuid4()}",
        route=StandardRoutes.full_support_flow()
    )

def assert_message_enriched(message, field, expected_keys=None):
    """Utility to assert message enrichment."""
    payload_data = getattr(message.payload, field, None)
    assert payload_data is not None
    if expected_keys:
        for key in expected_keys:
            assert key in payload_data
```

## Debugging Tests

### Debug Failed Tests

```bash
# Run with debugger on failure
pytest --pdb

# Run only last failed tests
pytest --lf

# Verbose output with print statements
pytest -s -v

# Run specific test with debugging
pytest tests/unit/test_sentiment_analyzer.py::TestSentimentAnalyzer::test_process_positive_sentiment -s -v
```

### Test Logging

Enable detailed logging during tests:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or use caplog fixture
def test_with_logging(caplog):
    with caplog.at_level(logging.INFO):
        # Test code here
        pass
    
    assert "Expected log message" in caplog.text
```

## Best Practices

### Test Organization

1. **One test class per component**
2. **Descriptive test method names**
3. **Arrange-Act-Assert pattern**
4. **Use fixtures for setup**
5. **Mock external dependencies**

### Test Writing Guidelines

```python
class TestSentimentAnalyzer:
    """Test sentiment analyzer functionality."""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return SentimentAnalyzer()
    
    @pytest.mark.asyncio
    async def test_process_positive_sentiment(self, analyzer):
        """Test processing message with positive sentiment."""
        # Arrange
        payload = MessagePayload(
            customer_message="I love this service!",
            customer_email="happy@example.com"
        )
        
        # Act
        result = await analyzer.process(payload)
        
        # Assert
        assert result["sentiment"]["label"] == "positive"
        assert result["sentiment"]["score"] > 0
        assert result["is_complaint"] is False
```

### Performance Testing Guidelines

1. **Set reasonable timeouts**
2. **Test with realistic data volumes**
3. **Measure both latency and throughput**
4. **Test concurrent scenarios**
5. **Monitor resource usage**

## Troubleshooting

### Common Issues

#### Import Errors
```bash
# Check Python path
python -c "import sys; print(sys.path)"

# Verify project structure
python test_setup_validation.py
```

#### Async Test Failures
```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Check pytest.ini has asyncio_mode = auto
```

#### Mock Not Working
```python
# Ensure patch is applied correctly
with patch("module.function") as mock_func:
    mock_func.return_value = "expected"
    # Test code here
```

#### Coverage Issues
```bash
# Clean coverage data
rm -rf .coverage htmlcov/

# Run with coverage debug
pytest --cov-report=term-missing --cov-config=.coveragerc
```

### Test Cleanup

```bash
# Clean all test artifacts
make test-clean

# Remove pytest cache
rm -rf .pytest_cache

# Clean Python cache
find . -name "__pycache__" -type d -exec rm -rf {} +
```

## Contributing

When adding new tests:

1. **Write tests for new features**
2. **Update existing tests for changes**
3. **Ensure all tests pass**: `make test`
4. **Check coverage**: `make test-coverage`
5. **Run full validation**: `python tests/test_runner.py`

### Test Review Checklist

- [ ] Tests cover happy path and edge cases
- [ ] External dependencies are mocked
- [ ] Tests are independent and can run in any order
- [ ] Test names are descriptive
- [ ] Coverage meets project targets
- [ ] Tests run quickly (under 30 seconds for unit tests)

## Resources

- **pytest Documentation**: https://docs.pytest.org/
- **pytest-asyncio**: https://pytest-asyncio.readthedocs.io/
- **Coverage.py**: https://coverage.readthedocs.io/
- **unittest.mock**: https://docs.python.org/3/library/unittest.mock.html

## Support

For testing issues:

1. Run `python test_setup_validation.py` first
2. Check the troubleshooting section
3. Review test logs and error messages
4. Ask in project discussions or issues

---

*This testing guide ensures comprehensive validation of the Actor Mesh E-commerce Support Agent system through unit tests, integration tests, and end-to-end validation.*