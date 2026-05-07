from docai_core.persistence.artifact_indexer import ArtifactIndexer
from docai_core.persistence.sqlite_store import SQLiteStore, ensure_database_schema

initialize_database = ensure_database_schema

__all__ = ["ArtifactIndexer", "SQLiteStore", "ensure_database_schema", "initialize_database"]
