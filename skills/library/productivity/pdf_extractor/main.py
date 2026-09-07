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

from skills.utils import success_response, error_response

def _parse_pages(spec, total):
    if spec == "all" or not spec:
        return list(range(total))
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a.strip()) - 1, int(b.strip())))
        else:
            pages.append(int(part) - 1)
    return [p for p in pages if 0 <= p < total]

async def pdf_extractor(params: dict) -> dict:
    file_path = params.get("file_path", "").strip()
    if not file_path:
        return error_response("file_path is required")
    action = params.get("action", "extract-text")
    pages_spec = params.get("pages", "all")

    try:
        import PyPDF2
        has_pypdf2 = True
    except ImportError:
        has_pypdf2 = False

    try:
        import pdfplumber
        has_pdfplumber = True
    except ImportError:
        has_pdfplumber = False

    if not has_pypdf2 and not has_pdfplumber:
        return error_response(
            "No PDF library available. Install one with: pip install PyPDF2 pdfplumber"
        )

    if action == "metadata":
        if has_pypdf2:
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                meta = {}
                if reader.metadata:
                    for k, v in reader.metadata.items():
                        meta[k.strip("/")] = str(v)
                return success_response({
                    "file": file_path,
                    "page_count": len(reader.pages),
                    "metadata": meta,
                })
        else:
            return error_response("PyPDF2 required for metadata extraction")

    if has_pdfplumber:
        with pdfplumber.open(file_path) as pdf:
            total = len(pdf.pages)
            pages = _parse_pages(pages_spec, total)

            if action == "extract-text":
                texts = []
                for i in pages:
                    page = pdf.pages[i]
                    txt = page.extract_text() or ""
                    texts.append({"page": i + 1, "text": txt.strip()})
                full_text = "\n".join(t["text"] for t in texts)
                return success_response({
                    "file": file_path,
                    "page_count": total,
                    "pages": texts,
                    "full_text": full_text,
                    "char_count": len(full_text),
                })

            elif action == "extract-tables":
                all_tables = []
                for i in pages:
                    page = pdf.pages[i]
                    tables = page.extract_tables()
                    if tables:
                        all_tables.append({
                            "page": i + 1,
                            "tables": [[list(row) for row in t] for t in tables],
                        })
                return success_response({
                    "file": file_path,
                    "page_count": total,
                    "tables": all_tables,
                })

    elif has_pypdf2:
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total = len(reader.pages)
            pages = _parse_pages(pages_spec, total)
            if action == "extract-text":
                texts = []
                for i in pages:
                    page = reader.pages[i]
                    txt = page.extract_text() or ""
                    texts.append({"page": i + 1, "text": txt.strip()})
                full_text = "\n".join(t["text"] for t in texts)
                return success_response({
                    "file": file_path,
                    "page_count": total,
                    "pages": texts,
                    "full_text": full_text,
                    "char_count": len(full_text),
                })
            return error_response(f"Action '{action}' requires pdfplumber for table extraction")

    return error_response("Unable to process PDF")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
