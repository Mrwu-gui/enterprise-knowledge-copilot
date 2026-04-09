"""模型配置与多供应商 Key 池管理。"""
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

DEFAULT_PROVIDER = {
    "id": "provider_1",
    "label": "默认供应商",
    "base_url": LLM_BASE_URL,
    "model_primary": LLM_MODEL_PRIMARY,
    "model_fallback": LLM_MODEL_FALLBACK,
    "api_keys": list(LLM_API_KEYS),
}

DEFAULT_MODEL_CONFIG = {
    "base_url": LLM_BASE_URL,
    "model_primary": LLM_MODEL_PRIMARY,
    "model_fallback": LLM_MODEL_FALLBACK,
    "providers": [DEFAULT_PROVIDER],
}


def _resolve_model_config_path(tenant_id: str | None = None, tenant_name: str = "") -> Path:
    if tenant_id:
        ensure_tenant_storage(tenant_id, tenant_name or tenant_id)
        return get_tenant_model_config_path(tenant_id)
    return MODEL_CONFIG_PATH


def _resolve_api_keys_path(tenant_id: str | None = None, tenant_name: str = "") -> Path:
    if tenant_id:
        ensure_tenant_storage(tenant_id, tenant_name or tenant_id)
        return get_tenant_api_keys_path(tenant_id)
    return API_KEYS_PATH


def ensure_model_config_files(tenant_id: str | None = None, tenant_name: str = "") -> None:
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
    for raw in str(text or "").replace(",", "\n").splitlines():
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        keys.append(item)
    return keys


def _dedupe_keep_order(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def _normalize_provider(item: dict, index: int, fallback_keys: list[str]) -> dict:
    if not isinstance(item, dict):
        item = {}
    label = str(item.get("label") or item.get("name") or f"供应商 {index + 1}").strip() or f"供应商 {index + 1}"
    provider_id = str(item.get("id") or f"provider_{index + 1}").strip() or f"provider_{index + 1}"
    base_url = str(item.get("base_url") or item.get("url") or LLM_BASE_URL).strip()
    primary = str(item.get("model_primary") or item.get("model") or LLM_MODEL_PRIMARY).strip()
    fallback = str(item.get("model_fallback") or item.get("fallback_model") or "").strip()
    raw_keys = item.get("api_keys")
    if isinstance(raw_keys, list):
        keys = _dedupe_keep_order([str(v).strip() for v in raw_keys if str(v).strip()])
    else:
        keys = _normalize_keys(str(item.get("api_keys_text") or ""))
    if not keys:
        keys = list(fallback_keys)
    return {
        "id": provider_id,
        "label": label,
        "base_url": base_url,
        "model_primary": primary,
        "model_fallback": fallback,
        "model": primary,
        "api_keys": keys,
        "api_keys_text": "\n".join(keys),
    }


def _normalize_providers(data: dict, fallback_keys: list[str]) -> list[dict]:
    providers = data.get("providers") if isinstance(data, dict) else None
    if isinstance(providers, list) and providers:
        normalized = [_normalize_provider(item, index, fallback_keys) for index, item in enumerate(providers)]
        return [item for item in normalized if item.get("base_url") and item.get("model_primary")]

    legacy_provider = {
        "id": "provider_1",
        "label": "默认供应商",
        "base_url": str((data or {}).get("base_url") or LLM_BASE_URL).strip(),
        "model_primary": str((data or {}).get("model_primary") or LLM_MODEL_PRIMARY).strip(),
        "model_fallback": str((data or {}).get("model_fallback") or "").strip(),
        "api_keys": list(fallback_keys),
    }
    return [_normalize_provider(legacy_provider, 0, fallback_keys)]


def _build_runtime_config(providers: list[dict]) -> dict:
    active = providers[0] if providers else dict(DEFAULT_PROVIDER)
    all_keys = _dedupe_keep_order([key for provider in providers for key in provider.get("api_keys", [])])
    return {
        "base_url": active.get("base_url", ""),
        "model_primary": active.get("model_primary", ""),
        "model_fallback": active.get("model_fallback", ""),
        "model": active.get("model_primary", ""),
        "api_keys": all_keys,
        "providers": providers,
    }


def load_model_config(tenant_id: str | None = None, tenant_name: str = "") -> dict:
    ensure_model_config_files(tenant_id, tenant_name)
    model_path = _resolve_model_config_path(tenant_id, tenant_name)
    keys_path = _resolve_api_keys_path(tenant_id, tenant_name)
    try:
        data = json.loads(model_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    fallback_keys = _normalize_keys(keys_path.read_text(encoding="utf-8")) or list(LLM_API_KEYS)
    providers = _normalize_providers(data if isinstance(data, dict) else {}, fallback_keys)
    if not providers:
        providers = [_normalize_provider(DEFAULT_PROVIDER, 0, list(LLM_API_KEYS))]
    return _build_runtime_config(providers)


def save_model_config(
    config_data: dict,
    keys_text: str,
    tenant_id: str | None = None,
    tenant_name: str = "",
) -> dict:
    ensure_model_config_files(tenant_id, tenant_name)
    model_path = _resolve_model_config_path(tenant_id, tenant_name)
    keys_path = _resolve_api_keys_path(tenant_id, tenant_name)
    if not isinstance(config_data, dict):
        raise ValueError("模型配置必须是对象")

    fallback_keys = _normalize_keys(keys_text) or list(LLM_API_KEYS)
    providers = _normalize_providers(config_data, fallback_keys)
    if not providers:
        raise ValueError("至少保留一个可用模型供应商")

    for provider in providers:
        if not provider.get("base_url"):
            raise ValueError("每个模型供应商都必须填写 Base URL")
        if not provider.get("model_primary"):
            raise ValueError("每个模型供应商都必须填写模型名称")
        if not provider.get("api_keys"):
            raise ValueError("每个模型供应商至少保留一个可用 API Key")

    stored = {
        "providers": [
            {
                "id": provider["id"],
                "label": provider["label"],
                "base_url": provider["base_url"],
                "model_primary": provider["model_primary"],
                "model_fallback": provider.get("model_fallback", ""),
                "api_keys": provider["api_keys"],
            }
            for provider in providers
        ]
    }
    runtime = _build_runtime_config(providers)
    stored.update(
        {
            "base_url": runtime["base_url"],
            "model_primary": runtime["model_primary"],
            "model_fallback": runtime["model_fallback"],
        }
    )

    model_path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    keys_path.write_text("\n".join(runtime["api_keys"]), encoding="utf-8")
    return runtime
