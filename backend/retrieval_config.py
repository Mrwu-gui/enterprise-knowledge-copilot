"""检索后端配置管理。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from backend.tenant_config import ensure_tenant_storage, get_tenant_retrieval_config_path

BASE_DIR = Path(__file__).resolve().parent.parent
RETRIEVAL_CONFIG_PATH = BASE_DIR / "data" / "retrieval_config.json"

DEFAULT_RETRIEVAL_CONFIG = {
    "backend": "hybrid",
    "qdrant": {
        "enabled": True,
        "mode": "local",
        "url": "http://127.0.0.1:6333",
        "api_key": "",
        "path": "data/qdrant_store",
        "collection": "enterprise_rag_default",
        "vector_size": 1024,
        "distance": "Cosine",
    },
    "embedding": {
        "provider": "local_hash",
        "model": "local_hash_v1",
        "base_url": "",
        "api_key": "",
    },
    "rerank": {
        "enabled": True,
        "provider": "local_overlap",
        "model": "local_overlap_v1",
        "base_url": "",
        "api_key": "",
        "candidate_limit": 12,
        "top_n": 5,
    },
    "sparse": {
        "enabled": True,
        "provider": "bm25",
        "k1": 1.5,
        "b": 0.75,
        "dense_weight": 0.6,
        "sparse_weight": 0.4,
        "fusion_alpha": 0.7,
        "rrf_k": 50,
        "query_profiles": {
            "keyword_exact": {"dense_weight": 0.35, "sparse_weight": 0.65, "fusion_alpha": 0.55},
            "identifier_lookup": {"dense_weight": 0.25, "sparse_weight": 0.75, "fusion_alpha": 0.45},
            "faq_semantic": {"dense_weight": 0.72, "sparse_weight": 0.28, "fusion_alpha": 0.82},
            "process_policy": {"dense_weight": 0.58, "sparse_weight": 0.42, "fusion_alpha": 0.7},
        },
    },
    "orchestration": {
        "rewrite": {
            "enabled": True,
            "expand_synonyms": True,
            "attempt_expansions": True,
        },
        "judge": {
            "min_results": 2,
            "min_top_score": 0.24,
            "min_avg_score": 0.16,
        },
        "routing": {
            "enabled": True,
            "profile_backends": {
                "identifier_lookup": "bm25",
                "keyword_exact": "hybrid",
                "faq_semantic": "qdrant",
                "process_policy": "hybrid",
            },
        },
        "retry": {
            "enabled": True,
            "max_attempts": 2,
            "fallback_top_k": 8,
            "stages": [
                {"backend": "hybrid", "top_k": 8, "rewrite_mode": "broad"},
                {"backend": "bm25", "top_k": 10, "rewrite_mode": "strict"},
            ],
        },
    },
}


def _resolve_retrieval_config_path(tenant_id: str | None = None, tenant_name: str = "") -> Path:
    """解析检索配置路径。"""
    if tenant_id:
        ensure_tenant_storage(tenant_id, tenant_name or tenant_id)
        return get_tenant_retrieval_config_path(tenant_id)
    return RETRIEVAL_CONFIG_PATH


def resolve_qdrant_local_path(path_value: str | None) -> Path:
    """把相对路径解析到项目根目录，避免本地嵌入式 Qdrant 写到未知位置。"""
    raw = str(path_value or "").strip()
    if not raw:
        raw = str(DEFAULT_RETRIEVAL_CONFIG["qdrant"]["path"])
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def ensure_retrieval_config_file(tenant_id: str | None = None, tenant_name: str = "") -> None:
    """首次启动时补齐检索后端配置。"""
    config_path = _resolve_retrieval_config_path(tenant_id, tenant_name)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(
            json.dumps(DEFAULT_RETRIEVAL_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_retrieval_config(tenant_id: str | None = None, tenant_name: str = "") -> dict:
    """读取检索后端配置。"""
    ensure_retrieval_config_file(tenant_id, tenant_name)
    config_path = _resolve_retrieval_config_path(tenant_id, tenant_name)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return _deep_merge(DEFAULT_RETRIEVAL_CONFIG, raw if isinstance(raw, dict) else {})


def save_retrieval_config(config_data: dict, tenant_id: str | None = None, tenant_name: str = "") -> dict:
    """保存检索后端配置。"""
    if not isinstance(config_data, dict):
        raise ValueError("检索配置必须是 JSON 对象")
    merged = _deep_merge(DEFAULT_RETRIEVAL_CONFIG, config_data)
    config_path = _resolve_retrieval_config_path(tenant_id, tenant_name)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return merged
