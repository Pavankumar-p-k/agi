#!/usr/bin/env python3
"""
Industrial-Grade Environment Validation for JARVIS Hybrid Automation System
Tests: Python, dependencies, Ollama, online APIs, and fallback chains
"""

import sys
import os
import json
import subprocess
import socket
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

# Color codes for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def log_pass(msg: str):
    print(f"{Colors.GREEN}✓ PASS{Colors.RESET} {msg}")

def log_fail(msg: str):
    print(f"{Colors.RED}✗ FAIL{Colors.RESET} {msg}")

def log_warn(msg: str):
    print(f"{Colors.YELLOW}⚠ WARN{Colors.RESET} {msg}")

def log_info(msg: str):
    print(f"{Colors.BLUE}ℹ INFO{Colors.RESET} {msg}")

def log_header(msg: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print(f"{msg}")
    print(f"{'='*60}{Colors.RESET}\n")

# Test suite results
results = {
    "environment": {},
    "python_deps": {},
    "ollama": {},
    "online_apis": {},
    "system_health": {},
}

def test_python_version() -> bool:
    """Verify Python 3.11+"""
    log_header("1. Python Version Check")
    version = sys.version_info
    ver_str = f"{version.major}.{version.minor}.{version.micro}"
    
    if version.major >= 3 and version.minor >= 11:
        log_pass(f"Python {ver_str} (3.11+)")
        results["environment"]["python_version"] = {"status": "pass", "version": ver_str}
        return True
    else:
        log_fail(f"Python {ver_str} - requires Python 3.11+")
        results["environment"]["python_version"] = {"status": "fail", "version": ver_str}
        return False

def test_venv_setup() -> bool:
    """Check virtual environment"""
    log_header("2. Virtual Environment Setup")
    
    venv_paths = [
        BACKEND / ".venv311",
        BACKEND / ".venv",
        BACKEND / "venv"
    ]
    
    for venv in venv_paths:
        if venv.exists():
            log_pass(f"Found venv at {venv.name}")
            results["environment"]["venv"] = {"status": "pass", "path": str(venv)}
            return True
    
    log_fail("No virtual environment found")
    results["environment"]["venv"] = {"status": "fail", "error": "No venv found"}
    return False

def test_core_dependencies() -> Dict[str, bool]:
    """Test critical dependencies"""
    log_header("3. Core Dependencies Check")
    
    critical_packages = {
        "fastapi": "Web framework",
        "pydantic": "Data validation",
        "uvicorn": "ASGI server",
        "sqlalchemy": "Database ORM",
        "requests": "HTTP client (for Ollama)",
        "websockets": "WebSocket support",
    }
    
    status = {}
    for package, desc in critical_packages.items():
        try:
            __import__(package)
            log_pass(f"{package}: {desc}")
            status[package] = True
            results["python_deps"][package] = {"status": "pass", "description": desc}
        except ImportError:
            log_fail(f"{package}: {desc}")
            status[package] = False
            results["python_deps"][package] = {"status": "fail", "description": desc}
    
    return status

def check_port_open(host: str, port: int, timeout: int = 2) -> bool:
    """Check if a port is open"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def test_ollama_models() -> Dict[str, bool]:
    """Test Ollama installation and models"""
    log_header("4. Ollama Local Models")
    
    status = {}
    
    # Check if Ollama is running
    ollama_running = check_port_open("127.0.0.1", 11434)
    if not ollama_running:
        log_warn("Ollama not running on port 11434 - attempting to connect anyway")
        results["ollama"]["status"] = "warning"
        results["ollama"]["message"] = "Ollama service not running"
        return {"service_running": False}
    
    log_pass("Ollama service running on port 11434")
    results["ollama"]["service_running"] = True
    status["service_running"] = True
    
    # List available models
    try:
        response = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if response.returncode == 0:
            log_pass("Ollama CLI accessible")
            models = response.stdout.split('\n')[1:]  # Skip header
            available_models = [m.split()[0] for m in models if m.strip()]
            log_info(f"Available models: {', '.join(available_models)}")
            results["ollama"]["available_models"] = available_models
            status["models_accessible"] = True
        else:
            log_warn("Ollama CLI not fully accessible")
            status["models_accessible"] = False
    except Exception as e:
        log_warn(f"Could not list ollama models: {e}")
        status["models_accessible"] = False
    
    return status

def test_online_api_connectivity() -> Dict[str, bool]:
    """Test online API connectivity (Claude, OpenAI, etc.)"""
    log_header("5. Online API Connectivity")
    
    status = {}
    
    # Check internet connectivity first
    try:
        import urllib.request
        urllib.request.urlopen("https://www.google.com", timeout=5)
        log_pass("Internet connectivity OK")
        status["internet"] = True
        results["online_apis"]["internet"] = True
    except Exception as e:
        log_warn(f"Internet connectivity issue: {e}")
        status["internet"] = False
        results["online_apis"]["internet"] = False
        return status
    
    # Check API endpoints
    api_endpoints = {
        "claude": "https://api.anthropic.com/",
        "openai": "https://api.openai.com/v1/models",
        "github": "https://api.github.com/",
    }
    
    for api_name, endpoint in api_endpoints.items():
        try:
            import urllib.request
            urllib.request.urlopen(endpoint, timeout=5)
            log_pass(f"{api_name.upper()} API endpoint reachable")
            status[api_name] = True
            results["online_apis"][api_name] = True
        except Exception as e:
            log_warn(f"{api_name.upper()} API: {type(e).__name__}")
            status[api_name] = False
            results["online_apis"][api_name] = False
    
    return status

def test_system_health() -> Dict[str, bool]:
    """Test system resources"""
    log_header("6. System Health Check")
    
    status = {}
    
    # Check disk space
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024**3)
        log_pass(f"Disk space: {free_gb:.2f} GB free")
        status["disk"] = True
        results["system_health"]["disk_free_gb"] = free_gb
    except Exception as e:
        log_fail(f"Disk check failed: {e}")
        status["disk"] = False
    
    # Check memory
    try:
        import psutil
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024**3)
        log_pass(f"Memory: {available_gb:.2f} GB available ({memory.percent}% used)")
        status["memory"] = True
        results["system_health"]["memory_available_gb"] = available_gb
    except ImportError:
        log_warn("psutil not installed - skipping memory check")
        status["memory"] = False
    except Exception as e:
        log_warn(f"Memory check failed: {e}")
        status["memory"] = False
    
    return status

def test_fallback_chain() -> bool:
    """Test model fallback logic"""
    log_header("7. Fallback Chain Configuration")
    
    fallback_chain = [
        ("ollama:tinyllama", "11434"),
        ("ollama:qwen2.5-coder:3b", "11435"),
        ("claude-3-opus", "online"),
        ("gpt-4", "online"),
    ]
    
    log_info("Configured fallback chain (priority order):")
    for i, (model, location) in enumerate(fallback_chain, 1):
        print(f"  {i}. {model} ({location})")
    
    results["system_health"]["fallback_chain"] = [
        {"priority": i, "model": model, "location": location}
        for i, (model, location) in enumerate(fallback_chain, 1)
    ]
    
    return True

def generate_report() -> str:
    """Generate JSON report"""
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "test_results": results,
    }
    
    # Calculate pass/fail counts
    passed = 0
    failed = 0
    
    for section in results.values():
        for test_result in section.values():
            if isinstance(test_result, dict) and "status" in test_result:
                if test_result["status"] == "pass":
                    passed += 1
                elif test_result["status"] == "fail":
                    failed += 1
    
    report["summary"] = {
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "success_rate": f"{(passed / (passed + failed) * 100) if (passed + failed) > 0 else 0:.1f}%",
    }
    
    return json.dumps(report, indent=2)

def main():
    log_header("JARVIS HYBRID AUTOMATION SYSTEM - ENVIRONMENT VALIDATION")
    print(f"Root: {ROOT}")
    print(f"Python: {sys.executable}\n")
    
    # Run all tests
    python_ok = test_python_version()
    venv_ok = test_venv_setup()
    deps_ok = all(test_core_dependencies().values())
    ollama_ok = test_ollama_models()
    online_ok = test_online_api_connectivity()
    health_ok = test_system_health()
    fallback_ok = test_fallback_chain()
    
    # Summary
    log_header("VALIDATION SUMMARY")
    
    checks = [
        ("Python 3.11+", python_ok),
        ("Virtual Environment", venv_ok),
        ("Core Dependencies", deps_ok),
        ("Ollama Service", bool(ollama_ok.get("service_running", False))),
        ("Internet Connectivity", online_ok.get("internet", False)),
        ("System Health", all(health_ok.values())),
    ]
    
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    
    for check_name, ok in checks:
        if ok:
            log_pass(f"{check_name}")
        else:
            log_fail(f"{check_name}")
    
    print(f"\n{Colors.BOLD}Overall Status: {passed}/{total} critical checks passed{Colors.RESET}\n")
    
    # Save report
    report = generate_report()
    report_file = ROOT / "test_environment_report.json"
    with open(report_file, "w") as f:
        f.write(report)
    print(f"Report saved to: {report_file}")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
