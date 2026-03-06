# Hallucination Guardrails – Financial Document AI 

**Project Component:** Hallucination Detection & Guardrails  
**Focus:** Strictly financial documents (Invoice, Receipt, Purchase Order, Bank Statement, Insurance Claim)  
**Key Upgrades (Feb 2026):**
- Fully dynamic input (extra fields allowed & processed)
- Relevance-first filtering with expectedness penalty
- SL-VAT differentiated policies (18% standard, 0% zero-rated/exempt with context boost)
- Hybrid hallucination detection (semantic + numerical + entity)
- Per-doc-type PII allowances
- Risk levels (LOW/MEDIUM/HIGH) + rich XAI metrics
- Guardrails vs Hallucination separated

## Features
- 6-layer ensemble (5 guardrails + 1 hallucination)
- Policy-driven via `config.py` (VAT, thresholds, allowed entities, weights…)
- Real-world SL financial alignment (Inland Revenue VAT rules)
- Swagger UI examples at `/docs`

## Setup
```bash
python -m venv venv
source venv/bin/activate   # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn hallucination_guardrails.main:app --reload