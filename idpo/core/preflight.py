"""Pre-flight checks for system dependencies and environment readiness."""

from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from idpo.core.config import PipelineConfig


def run_preflight(config: PipelineConfig, strict: bool = False) -> list[str]:
    issues: list[str] = []

    issues.extend(_check_python_deps())
    if str(config.preprocessing.ocr_engine).lower() in {"paddle", "paddleocr"}:
        issues.extend(_check_paddleocr())
    issues.extend(_check_tesseract())
    issues.extend(_check_pdf_rasterizer())

    if config.llm.use_extraction:
        if config.llm.default_mode == "local" and config.llm.provider.lower() == "ollama":
            issues.extend(_check_ollama(config.llm.base_url, config.llm.local_model))
        if config.llm.default_mode == "cloud" or config.llm.allow_cloud_fallback:
            issues.extend(_check_cloud_provider(config.llm.cloud_provider, config))

    if issues:
        message = "Preflight warnings:\n- " + "\n- ".join(issues)
        if strict:
            raise SystemExit(message.replace("warnings", "failed"))
        print(message, file=sys.stderr)
    return issues

def _check_python_deps() -> list[str]:
    missing = []
    try:
        import PIL  # noqa: F401
    except Exception:
        missing.append("Python package pillow is missing (install with pip install -e .[ocr])")
    try:
        import pytesseract  # noqa: F401
    except Exception:
        missing.append("Python package pytesseract is missing (install with pip install -e .[ocr])")
    return missing

def _check_paddleocr() -> list[str]:
    try:
        import paddleocr  # noqa: F401
    except Exception:
        return ["Python package paddleocr is missing (install with pip install paddleocr)"]
    return []

_WINDOWS_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def find_tesseract_cmd() -> str | None:
    """Locate tesseract: TESSERACT_CMD, then PATH, then the default Windows install folders."""
    configured = os.environ.get("TESSERACT_CMD", "").strip()
    if configured and os.path.exists(configured):
        return configured
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    candidates = list(_WINDOWS_TESSERACT_PATHS)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(os.path.join(local_appdata, "Programs", "Tesseract-OCR", "tesseract.exe"))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _check_tesseract() -> list[str]:
    if find_tesseract_cmd():
        return []
    return ["Tesseract OCR not found (install it, add it to PATH, or set TESSERACT_CMD)"]


def find_poppler_path() -> str | None:
    """Return a Poppler binary directory accepted by pdf2image, if available."""
    configured = os.environ.get("POPPLER_PATH", "").strip()
    if configured and shutil.which("pdftoppm", path=configured):
        return configured
    on_path = shutil.which("pdftoppm")
    if on_path:
        return str(Path(on_path).parent)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        if base.exists():
            for package in base.glob("*Poppler*"):
                for binary_dir in (package / "Library" / "bin", package / "bin"):
                    if (binary_dir / "pdftoppm.exe").is_file():
                        return str(binary_dir)
    return None


def _check_pdf_rasterizer() -> list[str]:
    try:
        import pypdfium2  # noqa: F401
        return []
    except Exception:
        pass
    try:
        import pdf2image  # noqa: F401
    except Exception:
        return ["No PDF rasterizer for scanned PDFs (install pypdfium2, or pdf2image with Poppler)"]
    if find_poppler_path():
        return []
    return ["No PDF rasterizer for scanned PDFs (install pypdfium2, or install Poppler and set POPPLER_PATH)"]

def _check_ollama(base_url: str, model: str) -> list[str]:
    url = base_url.rstrip("/") + "/api/tags"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        return [
            "Ollama server is not reachable (run 'ollama serve' and ensure it is installed)",
        ]
    except Exception:
        return ["Ollama server response is invalid (check ollama serve)"]

    if not model:
        return []
    models = payload.get("models", [])
    names = {item.get("name") for item in models if isinstance(item, dict)}
    if model not in names:
        return [f"Ollama model '{model}' not found (run 'ollama pull {model}')"]
    return []

def _check_cloud_provider(provider: str, config: PipelineConfig) -> list[str]:
    provider_name = (provider or "").lower()
    if provider_name == "openai":
        try:
            import openai  # noqa: F401
        except Exception:
            return ["Python package openai is missing (install with pip install -e .[cloud])"]
        env_key = os.getenv("OPENAI_API_KEY")
        cfg_key = config.llm.openai_api_key
        key = (env_key or cfg_key or "").strip()
        if not key:
            return ["OPENAI_API_KEY is not set (or provide llm.openai_api_key in config)"]
        if key == "sk-PLACEHOLDER":
            return ["OpenAI API key is set to placeholder value"]
        if key.startswith("${"):
            return ["OpenAI API key contains unresolved variable reference (check config and .env)"]
        return []
    if provider_name == "anthropic":
        try:
            import anthropic  # noqa: F401
        except Exception:
            return ["Python package anthropic is missing (install with pip install -e .[cloud])"]
        env_key = os.getenv("ANTHROPIC_API_KEY")
        if not env_key:
            return ["ANTHROPIC_API_KEY is not set"]
        return []
    if provider_name:
        return [f"Unknown cloud provider '{provider_name}' (use 'openai' or 'anthropic')"]
    return []
