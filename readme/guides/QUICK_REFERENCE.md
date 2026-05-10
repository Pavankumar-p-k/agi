# JARVIS Quick Reference Card

## 🚀 START JARVIS

```bash
cd c:\Users\peter\Desktop\jarvis
python jarvis_main.py
```

Logs will show:
```
[AUTONOMY] Initializing 4-layer autonomous stack...
[AUTONOMY] ✓ L1 Brain Layer online
[AUTONOMY] ✓ L2 Assistant Layer online
[AUTONOMY] ✓ L3 Executor Layer online
[AUTONOMY] ✓ L4 Controller Layer online
[AUTONOMY] All layers ONLINE ✓
```

---

## 🤖 API ENDPOINTS

### L1 Brain — Reasoning
```bash
curl -X POST http://localhost:8000/autonomy/think \
  -H "Content-Type: application/json" \
  -d '{"text":"your question here"}'
```

### L2 Assistant — Code Help
```bash
curl -X POST http://localhost:8000/autonomy/assist \
  -H "Content-Type: application/json" \
  -d '{
    "action":"explain",
    "code":"def fn(): pass",
    "language":"python"
  }'
```

### L3 Executor — Task Automation
```bash
curl -X POST http://localhost:8000/autonomy/execute \
  -H "Content-Type: application/json" \
  -d '{
    "goal":"create a backup script",
    "intent":"task"
  }'
```

### L4 Controller — System Control
```bash
curl -X POST http://localhost:8000/autonomy/system/action \
  -H "Content-Type: application/json" \
  -d '{
    "action":"terminal",
    "params":{"cmd":"git status"}
  }'
```

### Check Status
```bash
curl http://localhost:8000/autonomy/layers/status
```

---

## 🧠 START STUDENT AGI (Optional)

**In a SEPARATE terminal:**

```bash
cd backend/learning/student_agi
python student_agi_main.py
```

Service runs on port 11436.

### Teach the Student
```bash
curl -X POST http://localhost:8000/student-agi/teach \
  -H "Content-Type: application/json" \
  -d '{
    "topic":"Python recursion",
    "difficulty":"beginner"
  }'
```

### Ask the Student
```bash
curl -X POST http://localhost:8000/student-agi/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What is recursion?"}'
```

### Check Knowledge
```bash
curl http://localhost:8000/student-agi/status
```

### Run Daily Lesson
```bash
curl -X POST http://localhost:8000/student-agi/daily
```

---

## 📁 Key Project Folders

```
c:\Users\peter\Desktop\jarvis\
├── backend/
│   ├── autonomy/          ← 4-layer system (L1-L4)
│   ├── learning/student_agi/ ← Autonomous learning
│   └── core/main.py       ← FastAPI app
├── apps/jarvis_app/       ← Flutter app
├── jarvis_main.py         ← Start here
├── INTEGRATION_GUIDE.md   ← Full user guide
└── INTEGRATION_SUMMARY.md ← What was changed
```

---

## 🔧 Install Dependencies

```bash
pip install -r backend/requirements.txt

# Optional: Better code embeddings
pip install sentence-transformers
```

---

## 📊 Testing All 4 Layers

Test each layer:

```bash
# L1 Brain
curl -X POST http://localhost:8000/autonomy/think \
  -H "Content-Type: application/json" \
  -d '{"text":"hello jarvis"}'

# L2 Assistant
curl -X POST http://localhost:8000/autonomy/assist \
  -H "Content-Type: application/json" \
  -d '{"action":"explain","code":"print(42)","language":"python"}'

# L3 Executor
curl -X POST http://localhost:8000/autonomy/execute \
  -H "Content-Type: application/json" \
  -d '{"goal":"create hello.py","intent":"task"}'

# L4 Controller
curl -X POST http://localhost:8000/autonomy/system/action \
  -H "Content-Type: application/json" \
  -d '{"action":"terminal","params":{"cmd":"echo test"}}'

# All 4 Status
curl http://localhost:8000/autonomy/layers/status
```

---

## ⚠️ Troubleshooting

**Autonomy routes not loading?**
```bash
pip install -r backend/requirements.txt
```

**Student AGI routes return 503?**
```bash
# Start the student AGI service in another terminal:
python backend/learning/student_agi/student_agi_main.py
```

**L2 Assistant slow on first run?**
- It's scanning your project. Give it 30 seconds. Uses background scan.

**Check logs for errors:**
```bash
python jarvis_main.py 2>&1 | findstr AUTONOMY
```

---

## 📚 Full Docs

- **User Guide:** `INTEGRATION_GUIDE.md`
- **Technical Docs:** `backend/autonomy/ARCHITECTURE.md`
- **What Changed:** `INTEGRATION_SUMMARY.md`

---

## 🎯 The 4 Layers Explained (30 sec version)

| Layer | Does | Like |
|-------|------|------|
| L1 Brain | Routes, reasons, plans | ChatGPT |
| L2 Assistant | Code analysis, suggestions | Copilot |
| L3 Executor | Task decomposition, sandbox run | Codex |
| L4 Controller | System control, terminal, ADB | OpenClaw |

**Bonus:** Student AGI learns and teaches itself (like a student whose teacher is JARVIS).

---

## 💡 Pro Tips

1. **Test with Postman** — Easier than curl
2. **Use the Flutter app** — "AI LAYERS" tab shows everything live
3. **Monitor background tasks** — `/autonomy/executions/recent`
4. **Check safety blocks** — `/autonomy/safety/blocks`
5. **Teach the Student daily** — It improves automatically!

---

**Ready? → `python jarvis_main.py` ✅**
