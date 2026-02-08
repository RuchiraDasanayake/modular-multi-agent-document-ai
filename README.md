# modular-multi-agent-document-ai
A modular, multi-agent framework for intelligent document understanding and analysis. This project integrates specialized agents for parsing, reasoning, summarization, and retrieval, enabling adaptive collaboration through a scalable architecture designed for complex document AI workflows.
# Finance Q&A Bot with Explainable AI (XAI)

A domain-specific Q&A system for finance that provides **Explainable AI** answers with **SHAP/LIME analysis**, **Text Span Highlighting**, and **Human-in-the-Loop (HITL) feedback**.

## Features

### Core Capabilities

- **Transformer-based Q&A** - Uses DistilBERT (distilbert-base-cased-distilled-squad) for accurate question answering
- **Domain Focus** - Optimized for finance-related content and terminology

### XAI (Explainable AI)

1. **SHAP Analysis** - Feature importance visualization showing which words contributed most to the answer
2. **LIME Explanations** - Local interpretable model-agnostic explanations with word-level importance
3. **Text Span Highlighting** - Visual highlighting of evidence in the source text
4. **Confidence Scoring** - Reliability metrics for answer quality

### Human-in-the-Loop (HITL)

- **Feedback Dashboard** - Rate answer quality, relevance, and completeness
- **Correction Interface** - Submit improved answers for model refinement
- **Quality Tracking** - Monitor answer performance over time

### User Interface

- **Document Upload** - Simulated document ingestion flow
- **WhatsApp-style Chat** - Modern conversational interface
- **XAI Visualization Page** - Detailed explanation breakdowns with charts

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/finance_qa_xai.git
cd finance_qa_xai
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Application

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`

## Project Structure

```
finance_qa_xai/
├── app.py              # Main Streamlit application (UI pages)
├── xai_engine.py       # XAI engine with SHAP/LIME integration
├── hitl_dashboard.py   # Human-in-the-Loop feedback system
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── .gitignore          # Git ignore patterns
```

## Application Flow

1. **Upload Page** - Drag and drop document upload (simulated for demo)
2. **Processing Page** - Document processing animation
3. **Success Page** - Confirmation with "Ask Q&A" button
4. **Q&A Chat** - Ask questions about the finance content
5. **XAI Page** - View SHAP/LIME explanations and highlighted text
6. **HITL Dashboard** - Provide feedback on answer quality

## Dependencies

| Package | Purpose |
|---------|---------|
| `streamlit` | Web UI framework |
| `transformers` | Hugging Face transformer models |
| `torch` | PyTorch for model inference |
| `shap` | SHAP explanations |
| `lime` | LIME explanations |
| `scikit-learn` | ML utilities for LIME |
| `plotly` | Interactive visualizations |
| `scipy` | Scientific computing |
| `numpy` | Numerical operations |

## Sample Questions

- "What is the core function of finance?"
- "How does the time value of money work?"
- "What instruments mediate capital exchange?"
- "What is the relationship between risk and return?"

## Requirements

- Python 3.8+
- 4GB+ RAM (for transformer model)
- Internet connection (first run downloads model)

## License

MIT License
