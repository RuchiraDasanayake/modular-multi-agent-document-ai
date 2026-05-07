# DocAI v2 System Requirements

Status: Current as of 2026-03-15

## 1. Purpose

Define the tools, libraries, and runtime capabilities DocAI v2 needs before checking what is already installed.

The goal is to avoid blindly inheriting the legacy environment while still reusing useful installed tools and legacy implementation pieces after quarantine and review.

## 2. Backend Requirements

DocAI v2 backend should use:
- Python 3.10 or newer
- Pydantic for contracts/data models if available
- pytest for tests
- pathlib/json/logging from standard library
- FastAPI later for API layer
- Uvicorn later for local API serving

## 3. Document Processing Requirements

The system should eventually support:
- PDF/image file handling
- image preprocessing
- OCR
- document parsing
- layout/table extraction later

Potential libraries to check:
- pillow
- opencv-python
- pytesseract
- paddleocr
- pypdf or pymupdf
- numpy
- pandas

Do not install yet. Only declare as candidates.

## 4. Local Model Requirements

The system should eventually support:
- local LLM provider
- model selection dropdown in UI
- JSON output mode
- deterministic extraction settings

Initial intended local model:
- Qwen 3.5 9B through Ollama or compatible local runner

Potential tools to check:
- ollama client or HTTP access
- requests/httpx
- pydantic validation for model outputs

## 5. Frontend Requirements

Frontend draft currently exists at:
`docs/Doc-AI-V2-Front End Gemini Draft`

Future cleaned frontend should use:
- React
- Vite
- TypeScript
- existing design tokens
- shared frontend domain types
- mock fixtures first
- backend API later

## 6. Testing Requirements

Testing should include:
- unit tests for contracts
- unit tests for artifact store
- integration test for fake orchestrator
- later regression tests for extraction outputs

Preferred tool:
- pytest

## 7. Legacy Reuse Rules

Legacy code can be reused only through quarantine.

Legacy quarantine location:
`legacy_salvage/`

Rules:
- Do not import legacy modules directly into docai_core.
- Copy useful legacy pieces into legacy_salvage only after review.
- Clean and wrap reused code through adapters.
- Add tests before using any salvaged code.
- Old architecture must not be reused.

Potential legacy areas to inspect later:
- OCR/preprocessing utilities
- validation/grounding logic
- scoring/reward logic
- benchmark loaders
- TS/RABI/DAAF learning logic
- artifact/provenance ideas

## 8. Dependency Rule

DocAI v2 should depend on declared project dependencies, not random global machine state.

However, since the legacy system has run on this PC, the next step is to inspect:
- what dependencies are declared in the repo
- what useful packages are already installed locally
- what legacy code can be quarantined and reused

## 9. Next Step

After this document, run an environment and legacy capability audit.

That audit should compare:
- what DocAI v2 requires
- what is already installed
- what is declared in dependency files
- what can be reused from legacy after quarantine

Keep the document clear and practical.
