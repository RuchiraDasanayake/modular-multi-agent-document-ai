"""Document chunking agent for splitting documents into processable segments."""

from __future__ import annotations

import time

from idpo.agents.base import Agent, AgentContext
from idpo.core.metrics import token_count
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Chunk, Document, Section, StageSignal

class ChunkingAgent(Agent):
    name = "chunking"
    version = "v1"
    input_contract = {"document": "Document", "sections": "list", "input_artifact_id": "str|None"}
    output_contract = {"chunks": "list", "artifact_id": "str", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        sections: list[Section] = payload.get("sections", [])
        input_artifact_id = payload.get("input_artifact_id")
        chunk_size = int(payload.get("chunk_size", ctx.config.chunking.chunk_size))
        overlap = int(payload.get("chunk_overlap", ctx.config.chunking.chunk_overlap))
        max_chunks = int(payload.get("max_chunks", ctx.config.chunking.max_chunks))
        chunks: list[Chunk] = []
        chunk_id = 0

        def _chunk_text(text: str, section_name: str | None, page_range: tuple[int, int]) -> None:
            nonlocal chunk_id
            tokens = text.split()
            idx = 0
            while idx < len(tokens) and len(chunks) < max_chunks:
                window = tokens[idx : idx + chunk_size]
                chunk_text = " ".join(window)
                chunk = Chunk(
                    chunk_id=f"{doc.doc_id}_chunk_{chunk_id}",
                    doc_id=doc.doc_id,
                    text=chunk_text,
                    tokens=token_count(chunk_text),
                    page_range=page_range,
                    section=section_name,
                    metadata={"index": chunk_id},
                )
                chunks.append(chunk)
                chunk_id += 1
                idx += max(chunk_size - overlap, 1)

        if sections:
            for section in sections:
                if not section.text:
                    continue
                start_page = section.page_start or (doc.pages[0].number if doc.pages else 1)
                end_page = section.page_end or (doc.pages[-1].number if doc.pages else 1)
                _chunk_text(section.text, section.name, (start_page, end_page))
        else:
            text = "\n".join(page.text for page in doc.pages)
            start_page = doc.pages[0].number if doc.pages else 1
            end_page = doc.pages[-1].number if doc.pages else 1
            _chunk_text(text, None, (start_page, end_page))

        input_artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_chunk_input.txt",
            "\n".join(page.text for page in doc.pages),
            kind="chunk_input",
            raw=True,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {"chunk_size": chunk_size, "overlap": overlap, "max_chunks": max_chunks},
                "source_artifacts": [input_artifact_id] if input_artifact_id else [],
            },
        )
        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_chunks.json",
            {"chunks": [chunk.__dict__ for chunk in chunks]},
            kind="chunks",
            raw=False,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {"chunk_size": chunk_size, "overlap": overlap, "max_chunks": max_chunks},
                "source_artifacts": [input_artifact.artifact_id],
            },
        )
        ctx.provenance.register_chunks(doc.doc_id, [chunk.__dict__ for chunk in chunks])
        signal = StageSignal(
            stage=self.name,
            confidence=0.7 if chunks else 0.3,
            uncertainty=0.3 if chunks else 0.7,
            metadata={"chunk_count": len(chunks)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "chunk_count": len(chunks)},
            outputs={"chunk_count": len(chunks), "artifact_id": artifact.artifact_id, "chunk_ids": [chunk.chunk_id for chunk in chunks]},
            parameters={"chunk_size": chunk_size, "overlap": overlap, "max_chunks": max_chunks},
            artifacts=[input_artifact.artifact_id, artifact.artifact_id],
            input_artifacts=[input_artifact_id] if input_artifact_id else [],
            output_artifacts=[artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"chunks": chunks, "chunks_artifact": artifact, "signal": signal})
