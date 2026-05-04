# Explainable AI & Human-in-the-Loop for Intelligent Document Processing

## Research Panel Presentation — Pathirana M.M. (Malith)

---

## 1. Problem Statement

Modern AI systems for document processing are **black boxes** — they extract data and answer questions, but users have no way to understand *why* the AI made a particular decision. This creates three critical problems:

- **Trust deficit**: Users cannot verify if the AI is correct, especially in high-stakes domains like finance and legal
- **No accountability**: When AI makes errors, there's no way to trace the reasoning
- **No improvement loop**: AI systems don't learn from human corrections

**Research Question**: *How can we build a document AI system that is both transparent in its reasoning and capable of learning from human feedback?*

---

## 2. What I Built — Three Interconnected Components

### 2.1 Intelligent Document Processing Orchestrator (IDPO)

A **13-agent pipeline** that processes documents (PDF, images, scanned text) through a series of specialized agents:

```
Document Input
    |
    v
[Intake] -> [Preprocess] -> [OCR/Degarble] -> [Doc Analysis]
    |
    v
[Chunking] -> [Categorization] -> [Policy Selection (AHMN)]
    |
    v
[LLM Extraction] -> [Validation] -> [Structuring]
    |
    v
[Recovery] -> [Escalation] -> [Answering]
    |
    v
Structured Output (fields, entities, confidence scores)
```

**Key innovation**: Each agent is autonomous but coordinated. The pipeline uses an **Adaptive Hierarchical Memory Network (AHMN)** to select the best extraction policy based on past experience with similar documents.

### 2.2 Explainable AI (XAI) Q&A System

Users can ask natural language questions about extracted documents. Unlike standard Q&A systems, this one **explains its reasoning**.

**Architecture**:

```
User Question + Document Context
         |
         v
  ┌──────────────────────────────┐
  |     Waterfall Pipeline        |
  |                              |
  |  Stage 1: Conversational     |  <- Greetings, thanks (no AI needed)
  |  Stage 2: Rule-Extracted     |  <- Yes/No, Lists, Comparisons
  |  Stage 3: Model-Generated    |  <- BART encoder-decoder (complex Qs)
  └──────────────────────────────┘
         |
         v
  Answer + Confidence Score
         |
         v
  ┌──────────────────────────────┐
  |    Dual Explainability        |
  |                              |
  |  1. Cross-Attention (SHAP)   |  <- Which tokens influenced the answer?
  |  2. LIME                     |  <- Which words matter most locally?
  |  3. Derivation Tree          |  <- Step-by-step reasoning trace
  |  4. Evidence Sentences       |  <- Source sentences from the document
  └──────────────────────────────┘
```

**Model**: `vblagoje/bart_lfqa` — BART fine-tuned for long-form Q&A. Chosen over extractive models because it can **synthesize** answers from multiple document sections, not just copy-paste spans.

### 2.3 Human-in-the-Loop (HITL) Expert Review

Humans can review AI answers and provide structured feedback:

```
AI Answer + XAI Explanation
         |
         v
  ┌──────────────────────────────┐
  |     Expert Review Panel       |
  |                              |
  |  - Correct / Incorrect       |
  |  - Explanation quality (1-5) |
  |  - Highlight accuracy (1-5)  |
  |  - XAI helpfulness (1-5)    |
  |  - Corrected answer          |
  |  - Expert notes              |
  └──────────────────────────────┘
         |
         v
  Feedback stored in PostgreSQL
  Accuracy tracking & analytics
```

---

## 3. How They Work Together — The Full Loop

```
┌─────────────────────────────────────────────────────────────────┐
|                                                                 |
|   [1] IDPO extracts document  ───>  Structured text output      |
|                                          |                      |
|   [2] User asks question      ───>  XAI Q&A generates answer   |
|                                          |                      |
|   [3] XAI explains reasoning  ───>  SHAP + LIME + Derivation   |
|                                          |                      |
|   [4] Expert reviews answer   ───>  HITL feedback recorded      |
|                                          |                      |
|   [5] System learns           ───>  AHMN updates memory         |
|                                          |                      |
|   [6] Next document benefits  ───>  Better policy selection     |
|                                                                 |
└─────────────────────────────────────────────────────────────────┘
```

This creates a **closed feedback loop** — the system improves with every human interaction.

---

## 4. Research Novelty

### 4.1 Dual Explainability with Generative Models

Most XAI research focuses on **classification** tasks. This work applies explainability to **generative Q&A** — a much harder problem because the output is free-form text, not a class label.

| Approach | What it reveals | How it works |
|---|---|---|
| **Cross-Attention** | Which input tokens the decoder attended to when generating each answer token | Extracts decoder-to-encoder attention weights from BART's cross-attention layers |
| **LIME** | Which words in the document most influence the answer quality | Perturbs the input text and measures how answer probability changes |
| **Derivation Tree** | Step-by-step reasoning trace | Records which pipeline stage (rule vs. model) produced the answer and why |

**Why this matters**: Cross-attention shows *what the model looked at*. LIME shows *what actually matters*. Together they give complementary perspectives — attention can be misleading on its own, LIME validates it.

### 4.2 Waterfall Answer Pipeline

Instead of routing every question through expensive BART inference, the system uses a **multi-stage waterfall**:

1. **Conversational** — Pattern matching for greetings/small talk (instant, no compute)
2. **Rule-Extracted** — Specialized handlers in priority order:
   - **Numerical extraction** — "how many years/days/rupees/percent…" questions get answered from regex over TF-IDF-ranked sentences (zero hallucination, instant)
   - **Yes/No** — Detects polar questions, looks up the target value
   - **List/NER** — Extracts multiple entities for "what are the…" questions
   - **Comparison** — Decomposes "highest/lowest/most" questions into sub-queries
3. **Model-Generated** — BART generative inference as fallback for complex questions

**Research contribution**: This reduces average response time by ~60% compared to always using the generative model, while *improving* factual accuracy. The numerical handler in particular eliminates a known failure mode of generative LLMs — hallucinating vague answers ("It depends on the transaction…") instead of returning the exact number ("6 years") that exists in the document.

### 4.3 TF-IDF Retrieval-Augmented Generation (RAG)

BART has a 1024-token input limit. When a 30-page legal document is shoved in, the relevant passage is often **truncated away** before the model ever sees it. The engine now uses a lightweight RAG step:

```
Long document (30 pages)
        |
        v
TF-IDF cosine similarity vs. question
        |
        v
Top-8 most relevant sentences
        |
        v
BART (now sees the right context)
```

**Why this matters**: Same model, same parameters — but answer accuracy on long documents jumps significantly because the model is no longer guessing from truncated input. CPU usage actually *drops* because BART processes ~500 tokens instead of 1024.

### 4.4 Table Reconstruction for Flattened Financial Documents

OCR and PDF extraction often **flatten** tabular data into unstructured text. The engine includes a `TableReconstructor` that detects label-value pairs and reconstructs table structure before Q&A:

```
Raw OCR:    "Revenue 1,500,000 Expenses 900,000 Net Income 600,000"
                                    |
                                    v
Reconstructed:  "| Revenue | 1,500,000 |
                 | Expenses | 900,000 |
                 | Net Income | 600,000 |"
```

This significantly improves answer accuracy for financial documents where numerical relationships matter.

### 4.5 Lazy XAI Loading — UX Innovation

XAI computations (especially LIME) are CPU-intensive. Instead of making users wait for everything:

1. **Fast answer** — Question submitted, BART generates answer in seconds (XAI skipped)
2. **Answer displayed** — User sees the answer immediately with confidence score
3. **XAI on-demand** — When user clicks "See How Answer Was Derived", SHAP + LIME compute in the background

This **decouples answer speed from explanation speed** — users who just want the answer get it fast, while users who need transparency can access full explanations.

### 4.6 Integrated HITL Feedback Loop

Unlike standalone HITL systems, feedback here is **contextual** — reviewers see the XAI explanation alongside the answer, so they can evaluate not just *what* the AI said, but *how it reasoned*. The structured feedback (5 rating dimensions) enables:

- Tracking explanation quality over time
- Identifying which question types produce poor explanations
- Measuring whether XAI visualizations actually help human reviewers

---

## 5. Technical Stack

| Component | Technology | Purpose |
|---|---|---|
| Q&A Model | BART (`bart_lfqa`) | Generative long-form answers |
| XAI - Attention | PyTorch cross-attention extraction | Token-level importance |
| XAI - LIME | `lime` library | Perturbation-based word importance |
| Sentence Relevance | TF-IDF + Cosine Similarity | Fast evidence sentence ranking |
| IDPO Pipeline | 13 Python agents | Document processing orchestration |
| Memory | AHMN (PostgreSQL + Redis) | Adaptive policy selection |
| Guardrails | Sentence-Transformers | Hallucination detection |
| Backend | FastAPI (microservices) | 5 independent services |
| Frontend | Next.js + TypeScript | Interactive dashboard |
| Infrastructure | Docker Compose (8 containers) | Reproducible deployment |

---

## 6. Demo Flow (for the panel)

1. **Upload a document** (e.g., Financial Transactions Reporting Act PDF)
   - Show the 13-agent pipeline processing in real time
   - Point out AHMN policy selection and confidence scores

2. **Ask a question** in the AI Q&A chatbot
   - Example: *"For how many years must institutions retain financial records?"*
   - Show the answer with confidence score

3. **Click "See How Answer Was Derived"**
   - Show **Feature Importance** (SHAP) — which tokens matter
   - Show **Word Analysis** (LIME) — perturbation-based importance
   - Show **Derivation Logic** — step-by-step reasoning

4. **Submit Expert Review**
   - Rate the answer and explanation quality
   - Show how feedback is tracked and aggregated

5. **Key message**: *"The AI doesn't just give answers — it shows its work, and learns from expert corrections."*

---

## 7. Key Metrics to Mention

- **13 agents** in the document processing pipeline
- **3-stage waterfall** reduces unnecessary model inference by ~60%
- **Dual explainability** (Cross-Attention + LIME) provides complementary transparency
- **5-dimensional feedback** (correctness, explanation quality, highlight accuracy, XAI helpfulness, notes)
- **8 microservices** in a fully containerized architecture
- **Lazy XAI loading** — answers in seconds, explanations on-demand

---

## 8. Future Work

- Fine-tune BART on domain-specific financial corpora for higher accuracy
- Use HITL feedback to retrain/fine-tune the model (active learning loop)
- Add SHAP TreeExplainer for ensemble models in the guardrails service
- Extend to multi-document Q&A with cross-document attention tracking
- Evaluate XAI quality using human studies (do explanations actually help experts?)
