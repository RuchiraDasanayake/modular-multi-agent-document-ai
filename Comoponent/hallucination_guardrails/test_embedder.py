# test_embedder.py
from sentence_transformers import SentenceTransformer

print("Testing embedder load...")

try:
    model = SentenceTransformer("all-mpnet-base-v2", device="cpu")
    print("SUCCESS: Model loaded!")
    emb = model.encode("This is a test sentence.")
    print(f"Embedding shape: {emb.shape}") # pyright: ignore[reportAttributeAccessIssue]
except Exception as e:
    print("FAILED to load model:")
    print(e)