# S1 synthetic JSON-schema probe

The research-only [`s1_grammar_probe.py`](../../product_eval/s1_grammar_probe.py)
prepares one local NuExtract3 call with a **synthetic** candidate. It hashes the
pinned model, vision projector and llama.cpp executable, checks the loopback
server's build, model path, context, slot count and health, and writes the raw
reply and receipt outside Git. Its request asks for a deliberately invalid
candidate ID and schema version while supplying the candidate-bound JSON
schema. The independent [`parse_reply`](../../product_eval/s1_schema_reply.py)
must accept the returned envelope, or the probe fails. A passing call would
show this server/model combination can return a source-free reply compatible
with the S1 shape; it would not prove the grammar caused the correction or
that a field name is meaningful.

This commit contains the harness and **three passing source-free tests**. No
server was launched, no model call or document inference occurred, and no
production extraction changed. The v1 S1 CORD row-witness gate must be
assessed separately before any receipt-model calls.
