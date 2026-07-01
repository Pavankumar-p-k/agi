# Performance Baseline

**Date:** 2026-07-01T14:02:01  
**JARVIS version:** 3.0.0-rc3  
**Platform:** Windows-10-10.0.26200-SP0  
**Python:** 3.11.9  
**CPU:** 16× AMD64 Family 25 Model 68 Stepping 1, AuthenticAMD  
**RAM:** 15.7 GB  
**GPU:** [{'name': 'NVIDIA GeForce RTX 4050 Laptop GPU', 'memory_mb': 6141.0}]

## Results

| Metric | Value |
|--------|-------|
| Cold start | 0.328s |
| Import `jarvis` | 0.344s |
| Import `core.version` | 0.078s |
| Import `core.diagnostics` | 0.109s |
| Import `demo.quick_demo` | 0.078s |
| Import `core.main` | 12.969s |
| Provider discovery | 3.547s |
| Demo duration | 12.1s |
| Server startup | 47.7s |
| Server ready | True |
| RSS memory | 213.1 MB |
| VMS memory | 673.7 MB |
| CPU idle | 0.0% |
