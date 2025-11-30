from __future__ import annotations

from prometheus_client import Counter, Histogram

# Discord events
discord_messages_processed_total = Counter(
    "discord_messages_processed_total", "Total Discord messages processed by the bot"
)

# RAG decisions (outer gating)
rag_queries_total = Counter(
    "rag_queries_total", "Total user queries by chosen mode", labelnames=("mode",)
)

# Retrieval metrics
rag_query_duration_seconds = Histogram(
    "rag_query_duration_seconds", "Duration of RAG retrieval/query pipeline"
)
rag_best_score = Histogram(
    "rag_best_score", "Best retrieval score observed", buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
)

# Indexing
indexing_chunks_total = Counter(
    "indexing_chunks_total", "Total chunks indexed into the vector store"
)

# Jobs
jobs_enqueued_total = Counter(
    "jobs_enqueued_total", "Jobs enqueued by type", labelnames=("type",)
)
jobs_completed_total = Counter(
    "jobs_completed_total", "Jobs completed by status/type", labelnames=("status", "type")
)
job_duration_seconds = Histogram(
    "job_duration_seconds", "Job processing duration by type", labelnames=("type",)
)

