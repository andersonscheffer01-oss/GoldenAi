"""Golden Memory Engine V2 — fundação (M1.0) + vault (M1.1) + grafo (M1.2) + obsidian bidirecional (M1.6)."""
from .engine import GoldenMemoryEngine, WorkingMemory
from .consolidation import (ConsolidationDecision, ConsolidationKind,
                            MemoryConsolidator)
from .graph import (EdgeDirection, EntityResolution, GraphEdge, GraphNeighbor,
                    GraphNode, GraphPath, GraphResult, ResolutionStatus,
                    TrustTier, inverse_label, normalize_name,
                    relation_direction, source_trust)
from .hybrid import (HybridCandidate, HybridMemoryRetriever, HybridReport,
                     build_context, clean_snippet, evaluate_queries,
                     fts_available, hybrid_mode, mrr, recall_at_k,
                     rebuild_fts, sanitize_query, top1_hit)
from .importer import ImportDecision, ImportResult, VaultImporter
from .legacy_adapter import LegacyMemoryAdapter
from .migrations import (V2_SCHEMA_VERSION, ensure_v2_schema,
                         v2_pending_embeddings, v2_schema_version)
from .reconciler import ReconciliationState, VaultReconciler
from .record import (EntityV2, MemoryCandidate, MemoryRecordV2,
                     MemorySearchResult, MemorySecurityError,
                     MemoryValidationError, RelationV2, content_hash)
from .research import (CandidateResolution, EvidenceRecord, ExpertDomain,
                       ExpertProfile, FetchedSource, KnowledgeCandidate,
                       LearningEngine, LearningState, LocalExperience,
                       BraveSearchResearchProvider, ResearchEngine,
                       ResearchProvider, ResearchProviderError, ResearchReport,
                       ResearchResult, SafeHTTPFetcher, SourceTrustEvaluator,
                       SourceTrustLevel, StaticResearchProvider,
                       AutoResearchProvider, GroqWebResearchProvider,
                       TavilyResearchProvider,
                       build_research_provider_from_env,
                       normalize_research_url, sanitize_research_query,
                       research_provider_health_from_env, validate_fetch_url)
from .store import MarkdownMemoryStore, MemoryStore, SQLiteMemoryStore
from .types import (ConfidenceBasis, EmbeddingState, EntityType, MatchSource,
                    MemoryKind, RecordStatus, RelationType, SourceType)
from .vault import SyncStatus, default_vault_root
from .watcher import SelfWriteToken, VaultFileEvent, VaultWatcher

__all__ = [
    "ConfidenceBasis", "ConsolidationDecision", "ConsolidationKind",
    "MemoryConsolidator", "EdgeDirection", "EmbeddingState", "EntityResolution",
    "EntityType", "EntityV2", "GoldenMemoryEngine", "GraphEdge",
    "GraphNeighbor", "GraphNode", "GraphPath", "GraphResult",
    "HybridCandidate", "HybridMemoryRetriever", "HybridReport",
    "CandidateResolution", "EvidenceRecord", "ExpertDomain", "ExpertProfile",
    "AutoResearchProvider", "BraveSearchResearchProvider", "FetchedSource",
    "GroqWebResearchProvider", "ImportDecision", "ImportResult",
    "KnowledgeCandidate",
    "LearningEngine", "LearningState",
    "LegacyMemoryAdapter", "LocalExperience", "MarkdownMemoryStore", "MatchSource",
    "MemoryCandidate", "MemoryKind", "MemoryRecordV2", "MemorySearchResult",
    "MemorySecurityError", "MemoryStore", "MemoryValidationError",
    "ReconciliationState", "RelationType", "RelationV2", "RecordStatus",
    "ResearchEngine",
    "ResearchProvider", "ResearchProviderError", "ResearchReport",
    "ResearchResult", "ResolutionStatus", "SafeHTTPFetcher",
    "SelfWriteToken", "SQLiteMemoryStore", "SourceType", "SyncStatus",
    "TrustTier", "VaultFileEvent", "VaultImporter", "VaultReconciler",
    "VaultWatcher",
    "SourceTrustEvaluator", "SourceTrustLevel", "StaticResearchProvider",
    "TavilyResearchProvider",
    "V2_SCHEMA_VERSION", "WorkingMemory", "build_context", "clean_snippet",
    "content_hash", "default_vault_root", "ensure_v2_schema",
    "evaluate_queries", "fts_available", "hybrid_mode", "inverse_label",
    "mrr", "normalize_name", "recall_at_k", "rebuild_fts",
    "relation_direction", "sanitize_query", "source_trust", "top1_hit",
    "build_research_provider_from_env", "normalize_research_url",
    "research_provider_health_from_env", "sanitize_research_query",
    "validate_fetch_url", "v2_pending_embeddings", "v2_schema_version",
]
