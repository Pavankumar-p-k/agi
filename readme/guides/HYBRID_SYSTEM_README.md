# JARVIS Hybrid Automation System - Research-Grade Implementation

## Overview

This is a **research-grade hybrid automation system** that combines multiple AI paradigms into a unified, production-ready platform. Based on the provided taxonomy of modern AI automation systems, it implements:

- **Claude-based Planning** (Strategic reasoning and decomposition)
- **AutoGPT-style Autonomous Execution** (Recursive task breakdown and iteration)
- **OpenClaw Execution Engine** (Real-world system access with safety controls)
- **Perplexity-style Multi-Model Routing** (Automatic fallback between Ollama, Claude, Copilot, and Codex CLI)

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    HYBRID ORCHESTRATOR                      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                CLAUDE PLANNER                       │    │
│  │  • Strategic goal decomposition                     │    │
│  │  • Risk assessment & mitigation                     │    │
│  │  • Multi-step planning                              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │             AUTOGPT AUTONOMOUS ENGINE               │    │
│  │  • Recursive task breakdown                         │    │
│  │  • Self-iteration & refinement                      │    │
│  │  • Goal-directed execution                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              OPENCLAW EXECUTOR                      │    │
│  │  • Real system access (files, commands, browser)   │    │
│  │  • Safety controls & audit logging                 │    │
│  │  • Cross-platform execution                         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 MODEL FALLBACK SYSTEM                       │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐   │
│  │  OLLAMA     │   CODEX     │   CLAUDE    │  COPILOT    │   │
│  │  (Local)    │    CLI      │    (API)    │   (API)     │   │
│  └─────────────┴─────────────┴─────────────┴─────────────┘   │
│  Automatic routing based on: task type, availability, cost  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 MOBILE INTEGRATION                          │
│  • Flutter app with EventChannels                          │
│  • Real-time automation triggers                           │
│  • Cross-device context synchronization                     │
└─────────────────────────────────────────────────────────────┘
```

### Model Routing Strategy

| Task Type | Primary Model | Fallback Chain |
|-----------|---------------|----------------|
| Planning | Claude-3 | Ollama → Codex → Copilot |
| Reasoning | DeepSeek-R1 | Ollama → Claude → Copilot |
| Execution | Qwen3 | Ollama → Codex → Claude |
| Coding | Qwen2.5-Coder | Ollama → Copilot → Claude |
| Analysis | Qwen2.5 | Ollama → Claude → Copilot |
| Vision | Moondream | Ollama → Claude |
| Creative | Mistral | Ollama → Claude → Copilot |

## Installation & Setup

### 1. Environment Configuration

Copy the environment template and configure your API keys:

```bash
cp .env.template backend/.env
```

Edit `backend/.env` with your credentials:

```env
# Claude API (Required for planning)
CLAUDE_API_KEY=your_claude_api_key_here

# GitHub Copilot (Optional, for advanced coding)
COPILOT_API_KEY=your_copilot_api_key_here
GITHUB_TOKEN=your_github_personal_access_token

# Codex CLI (Optional, local executable)
CODEX_CLI_PATH=/path/to/codex-cli

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
```

### 2. Ollama Setup

Install and start multiple Ollama instances for different models:

```bash
# Terminal 1 - Primary chat model
OLLAMA_HOST=127.0.0.1:11434 ollama serve

# Terminal 2 - Analysis model
OLLAMA_HOST=127.0.0.1:11435 ollama serve

# Terminal 3 - Coding model
OLLAMA_HOST=127.0.0.1:11436 ollama serve

# And so on for other models...
```

Pull the required models:

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
ollama pull qwen2.5-coder:3b
ollama pull qwen3:4b
ollama pull deepseek-r1:1.5b
ollama pull mistral:7b
ollama pull moondream
ollama pull phi3:mini
ollama pull tinyllama
```

### 3. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Mobile App Setup

```bash
cd jarvis_final
flutter pub get
flutter build apk --debug
```

## Usage

### Starting the System

```bash
# Start the backend server
python jarvis_main.py

# Or use the launcher
./jarvis.bat
```

### API Endpoints

#### Hybrid Goal Execution
```bash
curl -X POST http://localhost:8000/api/hybrid/execute \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Set up a Python development environment and create a hello world script",
    "user_id": "developer",
    "platform": "desktop",
    "max_depth": 5,
    "timeout_minutes": 10
  }'
```

#### Enhanced Chat with Automation
```bash
curl -X POST http://localhost:8000/api/hybrid/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Automate opening Chrome and navigating to Google",
    "user_id": "user123",
    "context": {"location": "home", "device": "desktop"}
  }'
```

#### Mobile Automation
```bash
curl -X POST http://localhost:8000/api/mobile/automation \
  -H "Content-Type: application/json" \
  -d '{
    "command": "send whatsapp message to John: Hello from JARVIS!",
    "device_id": "android_device_123",
    "platform": "android",
    "context": {"location": "mobile", "network": "wifi"}
  }'
```

#### System Status
```bash
curl http://localhost:8000/api/hybrid/status
```

### Mobile App Integration

The Flutter app automatically integrates with the hybrid system:

1. **Message Reception**: Android notifications are forwarded via EventChannel
2. **AI Processing**: Messages trigger hybrid model fallback for intelligent replies
3. **Automation Triggers**: Commands like "open app X" execute via OpenClaw
4. **Context Sync**: Mobile and desktop maintain shared context

## Testing

### Industrial-Grade Test Suite

Run the comprehensive test suite:

```bash
cd backend
python -m pytest tests/test_hybrid_system.py -v
```

Test categories:
- **Model Fallback**: Ollama → Claude → Copilot chain
- **Orchestrator**: Goal decomposition and execution
- **Executor**: Safe command execution and file operations
- **Mobile Integration**: Cross-platform automation
- **Performance**: Concurrent execution and load testing

### Manual Testing

Test specific components:

```bash
# Test model fallback
curl -X POST http://localhost:8000/api/hybrid/models/test \
  -d '{"prompt": "Hello", "task_type": "chat"}'

# Test executor
curl -X POST http://localhost:8000/api/hybrid/executor/test \
  -d '{"command": "echo Hello World"}'

# Test mobile automation
curl -X POST http://localhost:8000/api/mobile/automation \
  -d '{"command": "open calculator", "device_id": "test"}'
```

## Key Features

### 1. Research-Grade Quality
- **No fakes**: All AI responses are from real models
- **100% working**: Industrial testing validates functionality
- **No hype**: Based on proven automation patterns

### 2. Multi-Model Intelligence
- **Automatic Fallbacks**: Seamless switching between models
- **Task-Specific Routing**: Best model for each task type
- **Performance Monitoring**: Tracks latency, success rates, costs

### 3. Real-World Execution
- **System Access**: Files, commands, browser automation
- **Safety Controls**: Command whitelisting, permission checks
- **Audit Logging**: Complete execution traceability

### 4. Mobile Integration
- **Cross-Platform**: Android/iOS support
- **Real-Time Sync**: Instant mobile-to-desktop automation
- **Context Awareness**: Location, network, device state

### 5. Autonomous Operation
- **Goal Decomposition**: Breaks complex tasks into steps
- **Self-Iteration**: Refines approaches based on results
- **Error Recovery**: Automatic retry with different strategies

## Architecture Comparison

| System | JARVIS Hybrid | AutoGPT | Claude | Perplexity | OpenClaw |
|--------|---------------|---------|--------|------------|----------|
| **Planning** | Claude-based | Limited | Excellent | Good | None |
| **Autonomy** | AutoGPT-style | Excellent | None | Limited | Limited |
| **Execution** | OpenClaw | Plugins | None | Sandboxed | Excellent |
| **Multi-Model** | Perplexity-style | Single | Single | Excellent | Single |
| **Safety** | Industrial | Limited | High | High | Medium |
| **Mobile** | Integrated | None | None | None | None |

## Performance Metrics

The system tracks comprehensive performance data:

- **Model Usage**: Success rates, latency, token consumption
- **Task Completion**: Success/failure rates, execution times
- **System Health**: Memory usage, CPU, error rates
- **Mobile Sync**: Cross-device operation statistics

Access metrics via:
```bash
curl http://localhost:8000/api/hybrid/status
```

## Security & Safety

### Execution Safety
- **Command Whitelisting**: Only approved commands execute
- **Permission Checks**: User/role-based access control
- **Danger Pattern Detection**: Blocks destructive operations
- **Sandboxing**: Isolated execution environments

### Data Protection
- **Encrypted Communication**: All API calls use HTTPS
- **Local Processing**: Sensitive data stays on-device
- **Audit Trails**: Complete logging of all operations
- **Access Controls**: Mobile app authentication required

## Troubleshooting

### Common Issues

1. **Model Connection Failed**
   ```bash
   # Check Ollama status
   curl http://localhost:11434/api/tags

   # Verify API keys in .env
   cat backend/.env | grep API_KEY
   ```

2. **Mobile App Crashes**
   ```bash
   # Check Android logs
   adb logcat | grep jarvis

   # Verify EventChannel setup
   flutter logs
   ```

3. **Execution Blocked**
   ```bash
   # Check safety logs
   curl http://localhost:8000/api/hybrid/status

   # Review audit logs
   tail -f backend/logs/audit.log
   ```

### Debug Mode

Enable detailed logging:
```env
LOG_LEVEL=DEBUG
HYBRID_MAX_RETRIES=5
EXECUTOR_SAFETY_ENABLED=false  # Use with caution!
```

## Contributing

This is a research-grade system designed for:

- **Academic Research**: Study hybrid AI automation patterns
- **Industrial Applications**: Production automation systems
- **Mobile AI**: Cross-device intelligent assistants

### Development Guidelines

1. **Testing First**: All changes require comprehensive tests
2. **Safety First**: Never compromise execution safety
3. **Performance Matters**: Monitor and optimize all operations
4. **Documentation**: Keep architecture and APIs documented

## License

Research and development use only. Not for production deployment without security audit.

---

**Built with research-grade quality - No fakes, no hype, 100% working automation**