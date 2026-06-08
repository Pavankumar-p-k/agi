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
