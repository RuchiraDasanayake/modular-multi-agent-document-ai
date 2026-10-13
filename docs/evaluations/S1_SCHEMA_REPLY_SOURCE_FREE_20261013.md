# S1 candidate-bound schema reply contract

**Source-free, 13 October 2026.** The research-only
[`s1_schema_reply.py`](../../product_eval/s1_schema_reply.py) accepts a model
reply only when it covers every enumerated source candidate exactly once,
either with a field proposal or an explicit abstention. It rejects unknown
or duplicate candidate IDs, extra keys or generated values, duplicate field
IDs, invalid field types, nonfinite JSON and oversized replies. Column
candidates can only become repeated fields; their source row group and node
identities come from the graph, not the model. Every retained field is
`needs_review`. The generated JSON Schema is for a future local grammar
compatibility probe; independent parsing remains mandatory because grammar
support cannot establish field meaning.

This contract has **no parser or model call**, no prompt, no source admission
to inference and no benchmark score. Its catalog must be built from a
source-verified graph; it does not validate the graph or infer a schema by
itself. The native-format graph and CORD OCR line graph remain research arms,
and CORD row/column witnesses plus full parser/config locks are still needed
before S1 inference under the [frozen protocol](EVIDENCE_FIRST_AUTO_SCHEMA_DECISION_AND_PROTOCOL_20261013.md).
