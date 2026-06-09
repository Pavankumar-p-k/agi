# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import shutil
from skills.utils import success_response, error_response

async def system_monitor(params: dict) -> dict:
    cpu_percent = "N/A"
    ram = {}
    disk = {}
    
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        ram = {
            "total_gb": round(mem.total / (1024**3), 1),
            "available_gb": round(mem.available / (1024**3), 1),
            "percent": mem.percent,
        }
        du = shutil.disk_usage("/")
        disk = {
            "total_gb": round(du.total / (1024**3), 1),
            "free_gb": round(du.free / (1024**3), 1),
            "percent": round(du.used / du.total * 100, 1),
        }
    except ImportError:
        cpu_percent = "psutil not installed"
    except Exception as e:
        cpu_percent = str(e)

    info = {
        "platform": os.name,
        "cpu": f"{cpu_percent}%" if isinstance(cpu_percent, (int, float)) else cpu_percent,
        "ram": ram or "unavailable",
        "disk": disk or "unavailable",
        "python": __import__('sys').version,
        "hostname": os.environ.get('COMPUTERNAME', 'unknown'),
    }
    return success_response(info, "System status retrieved")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        pass
