"""模型配置与 Key 池管理。"""
from __future__ import annotations

import json
from pathlib import Path

from backend.config import (
    BASE_DIR,
    LLM_API_KEYS,
    LLM_BASE_URL,
    LLM_MODEL_FALLBACK,
    LLM_MODEL_PRIMARY,
)
from backend.tenant_config import (
    ensure_tenant_storage,
    get_tenant_api_keys_path,
    get_tenant_model_config_path,
)


MODEL_CONFIG_PATH = BASE_DIR / "data" / "model_config.json"
API_KEYS_PATH = BASE_DIR / "config" / "api_keys.txt"

DEFAULT_MODEL_CONFIG = {
    "base_url": LLM_BASE_URL,
    "model_primary": LLM_MODEL_PRIMARY,
    "model_fallback": LLM_MODEL_FALLBACK,
}


def _resolve_model_config_path(tenant_id: str | None = None, tenant_name: str = "") -> Path:
    """解析模型配置文件路径。

    未指定租户时走平台总配置；指定租户时走租户私有配置。
    """
    if tenant_id:
        ensure_tenant_storage(tenant_id, tenant_name or tenant_id)
        return get_tenant_model_config_path(tenant_id)
    return MODEL_CONFIG_PATH


def _resolve_api_keys_path(tenant_id: str | None = None, tenant_name: str = "") -> Path:
    """解析 Key 池文件路径。"""
    if tenant_id:
        ensure_tenant_storage(tenant_id, tenant_name or tenant_id)
        return get_tenant_api_keys_path(tenant_id)
    return API_KEYS_PATH


def ensure_model_config_files(tenant_id: str | None = None, tenant_name: str = "") -> None:
    """确保模型配置和 Key 池文件存在。"""
    model_path = _resolve_model_config_path(tenant_id, tenant_name)
    keys_path = _resolve_api_keys_path(tenant_id, tenant_name)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    keys_path.parent.mkdir(parents=True, exist_ok=True)
    if not model_path.exists():
        model_path.write_text(
            json.dumps(DEFAULT_MODEL_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if not keys_path.exists():
        keys_path.write_text("\n".join(LLM_API_KEYS), encoding="utf-8")


def _normalize_keys(text: str) -> list[str]:
    keys: list[str] = []
    for raw in text.replace(",", "\n").splitlines():
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        keys.append(item)
    return keys


def load_model_config(tenant_id: str | None = None, tenant_name: str = "") -> dict:
    """读取模型配置，支持平台级和租户级。"""
    ensure_model_config_files(tenant_id, tenant_name)
    model_path = _resolve_model_config_path(tenant_id, tenant_name)
    keys_path = _resolve_api_keys_path(tenant_id, tenant_name)
    try:
        data = json.loads(model_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = dict(DEFAULT_MODEL_CONFIG)
    if isinstance(data, dict):
        merged.update({k: v for k, v in data.items() if isinstance(v, str)})
    keys = _normalize_keys(keys_path.read_text(encoding="utf-8"))
    merged["api_keys"] = keys or list(LLM_API_KEYS)
    return merged


def save_model_config(
    config_data: dict,
    keys_text: str,
    tenant_id: str | None = None,
    tenant_name: str = "",
) -> dict:
    """保存模型配置，支持平台级和租户级。"""
    ensure_model_config_files(tenant_id, tenant_name)
    model_path = _resolve_model_config_path(tenant_id, tenant_name)
    keys_path = _resolve_api_keys_path(tenant_id, tenant_name)
    if not isinstance(config_data, dict):
        raise ValueError("模型配置必须是对象")
    merged = dict(DEFAULT_MODEL_CONFIG)
    merged.update({k: str(v).strip() for k, v in config_data.items() if str(v).strip()})
    keys = _normalize_keys(keys_text)
    if not keys:
        raise ValueError("至少保留一个可用 API Key")
    model_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    keys_path.write_text("\n".join(keys), encoding="utf-8")
    merged["api_keys"] = keys
    return merged
