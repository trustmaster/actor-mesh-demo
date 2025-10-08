# Actor Mesh Demo - Quick Start Guide

Get the E-commerce Support AI Agent running in under 5 minutes!

## 🚀 One-Line Setup

```bash
cd actor-mesh-demo && ./install.sh
```

This will automatically:
- ✅ Check Python 3.11+ installation
- ✅ Create virtual environment  
- ✅ Install all dependencies
- ✅ Start NATS and Redis servers (Docker)
- ✅ Run basic tests to verify setup

## 📋 Prerequisites

- **Python 3.11+** (`python --version`)
- **Docker** (optional, for NATS/Redis)
- **LLM API Key** (optional, for full AI features):
  - OpenAI: `export OPENAI_API_KEY="your-key"`
  - Anthropic: `export ANTHROPIC_API_KEY="your-key"` 
  - Or run Ollama locally

## ⚡ Instant Demo

After installation, run the interactive demo:

```bash
# Activate environment (if not already active)
source venv/bin/activate  # Linux/Mac
# OR: venv\Scripts\activate  # Windows

# Run complete demo with 5 scenarios
python demo.py
```

**What you'll see:**
```
🎯 SCENARIO: Angry Customer - Delivery Issue
💬 Customer Message: "I am absolutely FURIOUS! My order ORD-12345678..."

🎭 STEP 1: Sentiment Analysis
   ✅ Sentiment: negative (score: -0.8, confidence: 0.9)
   📊 Urgency: high (score: 0.9)
   🚨 Is Complaint: True

🧠 STEP 2: Intent Analysis  
   ✅ Intent: delivery_issue (confidence: 0.95)
   🏷️ Entities: order_number: "ORD-12345678"

📋 STEP 3: Context Retrieval
   👤 Customer: John Doe (Premium tier)
   📦 Recent Orders: 3
   ⚠️ Risk Factors: delivery_issues

✍️ STEP 4: Response Generation
   💬 "I sincerely apologize for the delivery delay..."
   🎬 Actions: [expedite_delivery, add_credit]

🛡️ STEP 5: Guardrail Validation
   ✅ Approved: True, Issues: 0

⚡ STEP 6: Execution Coordination  
   ✅ Delivery expedited, $20 credit added
```

## 🧪 Test Individual Components

Test actors without full pipeline:

```bash
# Test basic functionality (no external deps)
python test_basic_flow.py

# Test individual actors
python -m actors.sentiment_analyzer  # Ctrl+C to stop
python -m actors.intent_analyzer
python -m actors.response_generator
```

## 🔧 Manual Setup (Alternative)

If automated installation fails:

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies  
pip install -r requirements.txt

# 3. Start NATS (required)
docker run -d -p 4222:4222 -p 8222:8222 --name nats-demo nats:latest -js

# 4. Start Redis (optional)
docker run -d -p 6379:6379 --name redis-demo redis:alpine

# 5. Configure environment
cp .env.example .env  # Edit with your API keys

# 6. Run demo
python demo.py
```

## 🌐 Start Mock APIs (Optional)

For full context retrieval, start mock services:

```bash
# Terminal 1 - Customer API
python -m mock_services.customer_api

# Terminal 2 - Orders API  
python -m mock_services.orders_api

# Terminal 3 - Tracking API
python -m mock_services.tracking_api
```

Access APIs at:
- Customer API: http://localhost:8001/docs
- Orders API: http://localhost:8002/docs  
- Tracking API: http://localhost:8003/docs

## 📊 Monitor System

While running, monitor:
- **NATS**: http://localhost:8222 (JetStream dashboard)
- **Logs**: Watch terminal output for message flow
- **Performance**: Demo shows timing for each step

## ❓ Troubleshooting

### "Module not found" errors
```bash
# Ensure virtual environment is activated
source venv/bin/activate
# Verify installation
pip list | grep fastapi
```

### NATS connection errors  
```bash
# Check NATS is running
docker ps | grep nats
# Restart if needed
docker restart nats-demo
```

### LLM/API errors
```bash
# Set API key
export OPENAI_API_KEY="your-key-here"
# Or edit .env file
echo 'OPENAI_API_KEY=your-key' >> .env
```

### Tests fail
```bash
# Expected without LLM keys - core functionality still works
# Check specific errors in output
python test_basic_flow.py 2>&1 | grep -E "(ERROR|FAILED)"
```

## 🎯 What's Working?

Even without LLM API keys, you'll see:
- ✅ **Sentiment Analysis**: Rule-based emotion detection
- ✅ **Message Routing**: Smart flow through actors  
- ✅ **Context Retrieval**: Customer data aggregation
- ✅ **Template Responses**: Fallback response generation
- ✅ **Guardrail Validation**: Safety and policy checks
- ✅ **Action Execution**: Simulated API operations

With LLM API keys, you get:
- 🤖 **AI Intent Classification**: Advanced understanding
- 🤖 **AI Response Generation**: Natural, context-aware responses
- 🤖 **AI Guardrail Validation**: Intelligent safety checks

## 🚀 Next Steps

1. **Explore the Code**: Check `actors/` directory for implementations
2. **Modify Scenarios**: Edit `demo.py` to test your own messages  
3. **Add New Actors**: Follow the patterns in existing actors
4. **Deploy to Kubernetes**: Use `k8s/` manifests for production
5. **Integrate Real APIs**: Replace mock services with your systems

## 📚 Learn More

- **Full Documentation**: See `README.md`
- **Architecture Details**: Read `spec/article.md`  
- **Implementation Guide**: Check `spec/implementation.md`
- **Project Summary**: Review `IMPLEMENTATION_SUMMARY.md`

## 🆘 Need Help?

- **Check Logs**: Most issues show clear error messages
- **Verify Prerequisites**: Ensure Python 3.11+ and Docker installed
- **Read Documentation**: Comprehensive guides available
- **Test Components**: Use `test_basic_flow.py` to isolate issues

---

**🎉 You're ready to explore Actor Mesh Architecture!**

The demo showcases a production-ready system handling real customer support scenarios with intelligent AI assistance, comprehensive safety checks, and robust error handling.