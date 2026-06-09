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
import logging

logger = logging.getLogger(__name__)


def extract_pdf_text(path: str) -> str:
    try:
        import pypdf
        with open(path, "rb") as f:
            reader = pypdf.PdfReader(f)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        pass
    try:
        from pdfminer.high_level import extract_text as pm_extract
        return pm_extract(path)
    except ImportError:
        pass
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        pass
    try:
        import subprocess
        result = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except Exception as _e:
        logger.debug("personal_docs pdftotext failed: %s", _e)
    logger.warning(f"No PDF extractor available for {path}")
    return ""


class PersonalDocsManager:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def index_personal_documents(self, directory: str) -> dict:
        logger.info(f"PersonalDocsManager.index not implemented (data_dir={self.data_dir})")
        return {"indexed": 0, "errors": 0}

    def search(self, query: str, k: int = 5) -> list[dict]:
        return []
