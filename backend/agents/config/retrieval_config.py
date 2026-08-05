import os

# LexiGraph Hierarchical Retrieval Pipeline Configurable Parameters

PINECONE_TOP_K = int(os.getenv("PINECONE_TOP_K", "25"))
FILTER_TOP_K = int(os.getenv("FILTER_TOP_K", "15"))
GRAPH_TOP_K = int(os.getenv("GRAPH_TOP_K", "15"))
COMMUNITY_TOP_K = int(os.getenv("COMMUNITY_TOP_K", "15"))
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "5"))
FINAL_OUTPUT_TOP_K = int(os.getenv("FINAL_OUTPUT_TOP_K", "5"))
