# Testing Conversation Context Fixes - Quick Guide

## 🚀 Quick Start

### 1. Start the System

```bash
cd actor-mesh-demo
make start-all
```

Wait for all services to start (NATS, Redis, Actors, API Gateway).

### 2. Open Chat Interface

Navigate to: http://localhost:8000/chat.html

---

## ✅ Manual Test Scenarios

### Test 1: Basic Session Persistence (CRITICAL)

**Steps:**
1. Send message: `"Hello, I have an issue with my order"`
2. Wait for agent response
3. Send message: `"My order number is ord-12345"`
4. Wait for agent response
5. **Refresh the page (F5 or Cmd+R)**
6. Send message: `"What's the status of my order?"`

**Expected Result:**
- ✅ Agent references "ord-12345" without asking for order number
- ✅ Agent remembers you have an issue
- ✅ Same session_id shown in UI (bottom of chat)

**Failure Indicators:**
- ❌ Agent asks "Could you provide your order number?"
- ❌ Agent doesn't know about the issue
- ❌ Session ID changed after refresh

---

### Test 2: Entity Tracking

**Steps:**
1. Send: `"I need help with order #12345"`
2. Send: `"The package arrived damaged"`
3. Send: `"When will the replacement arrive?"`

**Expected Result:**
- ✅ Agent references order #12345 in every response
- ✅ Agent knows about damaged package
- ✅ Agent understands "replacement" context

**Failure Indicators:**
- ❌ Agent asks which order
- ❌ Agent doesn't mention damaged package
- ❌ Agent doesn't understand replacement context

---

### Test 3: Multi-Turn Conversation

**Steps:**
1. Send: `"I ordered a laptop last week"`
2. Send: `"It was supposed to arrive yesterday"`
3. Send: `"But I haven't received it yet"`
4. Send: `"Can you help me track it?"`
5. Send: `"The order number is ORD-67890"`
6. Send: `"Any updates?"`

**Expected Result:**
- ✅ Agent builds on each message
- ✅ Agent doesn't ask to repeat information
- ✅ Agent references previous statements
- ✅ Agent uses order number in final response

---

### Test 4: Contact Information (Bug Check)

**Steps:**
1. Have any conversation with the agent
2. Check ALL agent responses carefully

**Expected Result:**
- ✅ Agent provides: support@techmart.com or 1-800-TECHMART
- ✅ Agent says "contact us at..." or "reach out to support@..."
- ✅ NEVER includes YOUR email (test@example.com) as contact

**Failure Indicators:**
- ❌ Agent says "reach out to me at test@example.com"
- ❌ Your email appears anywhere in agent responses

---

### Test 5: New Conversation

**Steps:**
1. Have a conversation about order #12345
2. Click "🔄 New Chat" button
3. Confirm the dialog
4. Send: `"Hello, I have a billing question"`

**Expected Result:**
- ✅ Chat messages cleared
- ✅ New session_id shown
- ✅ Agent doesn't reference order #12345
- ✅ Fresh conversation started

---

## 🤖 Automated Testing

### Run Full Test Suite

```bash
source venv/bin/activate
python scripts/test_conversation_context.py
```

**Expected Output:**
```
✅ PASS: Session Persistence
✅ PASS: Entity Tracking
✅ PASS: Context Maintenance
✅ PASS: Contact Information
✅ PASS: Database Consistency

✅ ALL TESTS PASSED (5/5)
```

---

## 🔍 Database Inspection

### Check Recent Conversations

```bash
source venv/bin/activate
python scripts/check_conversation_history.py --recent
```

**Expected Output:**
```
Found 1-5 conversation sessions

Session: ws_session_1701234567890_abc123...
Customer: test@example.com
Messages: 6-10
  1. 👤 Hello, I have an issue with my order
  2. 🤖 I'm sorry to hear that...
  3. 👤 My order number is ord-12345
  4. 🤖 Thank you for providing order #12345...
  5. 👤 What's the status?
  6. 🤖 For your order #12345...
```

### Check Session Fragmentation

```bash
python scripts/check_conversation_history.py --consistency
```

**Expected Output:**
```
✅ No session fragmentation detected - all customers have single sessions
```

**Bad Output (indicates problem):**
```
⚠️  Found 1 customer with multiple sessions:
📧 test@example.com
   Sessions: 3 (should be 1 if session persistence working)
```

---

## 🐛 Troubleshooting

### Problem: Agent keeps asking for order number

**Diagnosis:**
```bash
python scripts/check_conversation_history.py --recent
```

Look for:
- Multiple sessions for same customer
- Session ID changing between messages

**Likely Cause:** Frontend session persistence not working

**Fix:**
- Clear browser cache
- Check browser console for JavaScript errors
- Verify localStorage is enabled

---

### Problem: Agent loses context after few messages

**Diagnosis:**
Check if conversation history is in prompt:

```bash
tail -f actors.log | grep "conversation"
```

**Likely Cause:** Context retriever not fetching history

**Fix:**
- Check SQLite database has messages
- Verify session_id is being passed correctly
- Check context_retriever logs for errors

---

### Problem: Still seeing customer email as contact

**Diagnosis:**
Check agent responses in database:

```bash
python scripts/check_conversation_history.py --customer test@example.com
```

Look for customer email in agent messages.

**Likely Cause:** LLM not following prompt instructions

**Fix:**
- Temperature might be too high (should be 0.3)
- Prompt might need even stronger constraints
- LLM model might need changing

---

## 📊 Success Metrics

After fixes, you should see:

| Metric | Before | After |
|--------|--------|-------|
| Avg messages per session | 2-3 | 6-12 |
| Session fragmentation | High | Near 0% |
| Context maintenance | Poor | Excellent |
| Re-asks for info | Often | Never |
| Contact info errors | Frequent | None |

---

## 🎯 Quick Validation Checklist

Run through this checklist for quick validation:

- [ ] Chat opens successfully
- [ ] Can send messages
- [ ] Agent responds reasonably
- [ ] **Refresh page - session_id stays same**
- [ ] **Agent remembers order number after refresh**
- [ ] "New Chat" button works
- [ ] Contact info is support@techmart.com
- [ ] No customer email in responses
- [ ] Multi-turn conversation makes sense
- [ ] Database shows messages in same session
- [ ] Diagnostic script shows no fragmentation

---

## 🚨 Critical Test: The Example from User

Reproduce the exact scenario that was failing:

```
Step 1: "Hello, I have an issue with my order"
Step 2: "My order number is ord-12345"  
Step 3: "Any success with my order?"
```

**Expected (PASS):**
- Agent references ord-12345 in step 3
- Agent provides update about the order
- Agent doesn't ask for order number again

**Failure (BAD):**
- Agent asks "Could you please provide your order number?"
- Agent says "reach out to me at test@example.com"

---

## 📞 Support

If tests fail:

1. Check logs: `tail -f actors.log gateway.log`
2. Verify services running: `docker ps`
3. Check database: `python scripts/check_conversation_history.py --all`
4. Review implementation docs: `docs/CONVERSATION_FIXES_IMPLEMENTED.md`
5. Report issue with test output and logs

---

**Happy Testing! 🎉**