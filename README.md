# AHMN - Adaptive Hierarchical Memory Network

A self-learning document processing system that uses multi-armed bandits to optimize policy selection over time.

---

## Quick Start

```bash
cd ahmn_core
docker-compose up -d          # Start PostgreSQL + Redis
pip install -r requirements.txt
uvicorn main:app --reload     # Start API at http://localhost:8000
```

---

## API Usage

### 1. Get Policy Advice

Send document context, receive a recommended processing policy.

**Request:** `POST /advice`
```json
{
  "doc_type": "invoice",
  "vendor": "Acme Corp",
  "extra_context": {}
}
```

**Response:**
```json
{
  "advice_id": "550e8400-e29b-41d4-a716-446655440000",
  "policy_id": "acme_invoice_v2",
  "policy_data": {
    "action": "ocr_enhanced",
    "model": "layoutlm-v3"
  },
  "retrieval_source": "LTM"
}
```

| Field | Description |
|-------|-------------|
| `advice_id` | Unique session ID (use this to log results) |
| `policy_id` | Name of the selected policy |
| `policy_data` | JSON configuration for your processing pipeline |
| `retrieval_source` | `"LTM"` (learned) or `"DEFAULT"` (fallback) |

---

### 2. Log Outcome

After processing, report back the results so the system can learn.

**Request:** `POST /log`
```json
{
  "advice_id": "550e8400-e29b-41d4-a716-446655440000",
  "policy_id_used": "acme_invoice_v2",
  "metrics": {
    "f1_score": 0.95,
    "cost": 0.02,
    "processing_time_ms": 150,
    "success": true
  }
}
```

---

### 3. Human Feedback (Optional)

If a human corrected the output, log it to penalize the policy.

**Request:** `POST /feedback`
```json
{
  "advice_id": "550e8400-e29b-41d4-a716-446655440000",
  "human_corrected": true
}
```

---

## How Policies Work

Policies are stored in the database (`ltm_validated_policies` table). The system retrieves the best match using:

1. **Embedding Search** - Finds similar contexts using vector similarity
2. **Thompson Sampling** - Picks from top-5 candidates based on past success rates

**Default Policy:**  
If no learned policy matches, returns:
```json
{
  "policy_id": "default_policy",
  "policy_data": {"action": "standard_processing"}
}
```

**Custom Policies:**  
Insert policies directly into PostgreSQL with any JSON structure:
```sql
INSERT INTO ltm_validated_policies (context_hash, policy_id, policy_data, ...)
VALUES ('invoice_acme', 'acme_invoice_v2', '{"action": "ocr_enhanced", "dpi": 300}'::jsonb, ...);
```

---

## Project Structure

```
ahmn_core/
├── main.py                 # FastAPI endpoints
├── app/
│   ├── schemas.py          # Input/Output models
│   ├── config.py           # Hyperparameters
│   └── services/
│       ├── memory.py       # Core logic (STM/MTM/LTM)
│       └── selection_strategies.py  # Bandit algorithms
├── jobs/
│   ├── promote.py          # Promote good policies to LTM
│   └── forgetting.py       # Decay inactive policies
└── demos/                  # Example scripts
```

---

## Memory Architecture

| Tier | Storage | Purpose | Retention |
|------|---------|---------|-----------|
| **STM** | Redis | Session context | 30 min |
| **MTM** | PostgreSQL | Outcome logs | 90 days |
| **LTM** | PostgreSQL + pgvector | Validated policies | Permanent |

---

## License

MIT
