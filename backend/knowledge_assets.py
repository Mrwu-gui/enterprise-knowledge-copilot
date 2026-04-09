"""租户知识资产标签与智能体知识范围。"""
from __future__ import annotations

import hashlib
import json

from backend.document_processing import normalize_tier
from backend.tenant_config import ensure_tenant_storage, get_tenant_knowledge_metadata_path

PUBLIC_TIER_CODE_MAP = {
    "permanent": "L1",
    "seasonal": "L2",
    "incremental": "L2",
    "hotfix": "L3",
}


def _public_tier_code(value: str) -> str:
    canonical = normalize_tier(value)
    return PUBLIC_TIER_CODE_MAP.get(canonical, canonical)


def _metadata_key(tier: str, file_name: str) -> str:
    canonical = normalize_tier(tier)
    clean_file = str(file_name or "").strip().replace("\\", "/").lstrip("/")
    return f"{canonical}/{clean_file}"


def _stable_id(prefix: str, seed: str) -> str:
    clean = str(seed or "").strip()
    if not clean:
        clean = prefix
    return f"{prefix}_{hashlib.md5(clean.encode('utf-8')).hexdigest()[:10]}"


def _normalize_tags(tags: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in list(tags or []):
        clean = str(raw or "").strip()
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(clean)
    return result


def _normalize_tag_groups(entries: list | None) -> list[dict]:
    groups: list[dict] = []
    seen_group_ids: set[str] = set()
    for index, raw in enumerate(entries or [], start=1):
        if isinstance(raw, str):
            group_name = str(raw).strip()
            if not group_name:
                continue
            group_id = _stable_id("tag", f"{group_name}:{index}")
            groups.append(
                {
                    "tag_id": group_id,
                    "name": group_name,
                    "values": [
                        {
                            "value_id": _stable_id("tagv", f"{group_name}:{group_name}"),
                            "name": group_name,
                            "synonyms": [],
                        }
                    ],
                }
            )
            continue
        if not isinstance(raw, dict):
            continue
        group_name = str(raw.get("name") or raw.get("tag_name") or "").strip()
        if not group_name:
            continue
        group_id = str(raw.get("tag_id") or raw.get("id") or "").strip() or _stable_id("tag", f"{group_name}:{index}")
        if group_id in seen_group_ids:
            continue
        seen_group_ids.add(group_id)
        values: list[dict] = []
        seen_value_ids: set[str] = set()
        raw_values = raw.get("values") if isinstance(raw.get("values"), list) else raw.get("tag_values")
        for value_index, value_raw in enumerate(raw_values or [], start=1):
            if isinstance(value_raw, str):
                value_name = str(value_raw).strip()
                synonyms = []
                value_id = _stable_id("tagv", f"{group_id}:{value_name}:{value_index}")
            elif isinstance(value_raw, dict):
                value_name = str(value_raw.get("name") or value_raw.get("value") or "").strip()
                synonyms = _normalize_tags(value_raw.get("synonyms") if isinstance(value_raw.get("synonyms"), list) else [])
                value_id = str(value_raw.get("value_id") or value_raw.get("id") or "").strip() or _stable_id("tagv", f"{group_id}:{value_name}:{value_index}")
            else:
                continue
            if not value_name or value_id in seen_value_ids:
                continue
            seen_value_ids.add(value_id)
            values.append(
                {
                    "value_id": value_id,
                    "name": value_name,
                    "synonyms": synonyms,
                }
            )
        groups.append(
            {
                "tag_id": group_id,
                "name": group_name,
                "values": values,
            }
        )
    return groups


def _flatten_tag_group_values(groups: list[dict] | None) -> list[str]:
    values: list[str] = []
    for group in groups or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("values") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                values.append(name)
    return _normalize_tags(values)


def _normalize_library_records(entries: list[dict] | None) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(entries or [], start=1):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        library_id = str(raw.get("library_id") or raw.get("id") or "").strip() or _stable_id("kb", f"{name}:{index}")
        if library_id in seen:
            continue
        seen.add(library_id)
        result.append(
            {
                "library_id": library_id,
                "name": name,
                "description": str(raw.get("description") or "").strip(),
            }
        )
    if not result:
        result.append({"library_id": "kb_default", "name": "默认知识库", "description": "租户默认知识库"})
    return result


def _normalize_category_records(entries: list[dict] | None, libraries: list[dict]) -> list[dict]:
    valid_library_ids = {item["library_id"] for item in libraries}
    fallback_library_id = libraries[0]["library_id"]
    result: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(entries or [], start=1):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        library_id = str(raw.get("library_id") or "").strip()
        if library_id not in valid_library_ids:
            library_id = fallback_library_id
        category_id = str(raw.get("category_id") or raw.get("id") or "").strip() or _stable_id("cat", f"{library_id}:{name}:{index}")
        if category_id in seen:
            continue
        seen.add(category_id)
        result.append(
            {
                "category_id": category_id,
                "library_id": library_id,
                "name": name,
            }
        )
    return result


def load_knowledge_metadata(tenant_id: str, tenant_name: str = "") -> dict:
    ensure_tenant_storage(tenant_id, tenant_name or tenant_id)
    path = get_tenant_knowledge_metadata_path(tenant_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    catalog = data.get("catalog") if isinstance(data, dict) else []
    libraries = data.get("libraries") if isinstance(data, dict) else []
    categories = data.get("categories") if isinstance(data, dict) else []
    items = data.get("items") if isinstance(data, dict) else {}
    normalized_catalog = _normalize_tag_groups(catalog if isinstance(catalog, list) else [])
    normalized_libraries = _normalize_library_records(libraries if isinstance(libraries, list) else [])
    normalized_categories = _normalize_category_records(categories if isinstance(categories, list) else [], normalized_libraries)
    if not isinstance(items, dict):
        items = {}
    normalized: dict[str, dict] = {}
    for key, value in items.items():
        if not isinstance(value, dict):
            continue
        tier = normalize_tier(str(value.get("tier") or key.split("/", 1)[0] or "permanent"))
        file_name = str(value.get("file") or key.split("/", 1)[-1] or "").strip()
        if not file_name:
            continue
        clean_key = _metadata_key(tier, file_name)
        library_id = str(value.get("library_id") or "").strip() or normalized_libraries[0]["library_id"]
        if library_id not in {item["library_id"] for item in normalized_libraries}:
            library_id = normalized_libraries[0]["library_id"]
        category_id = str(value.get("category_id") or "").strip()
        if category_id and category_id not in {item["category_id"] for item in normalized_categories}:
            category_id = ""
        normalized[clean_key] = {
            "tier": tier,
            "tier_code": _public_tier_code(tier),
            "file": file_name,
            "tags": _normalize_tags(value.get("tags") if isinstance(value.get("tags"), list) else []),
            "library_id": library_id,
            "category_id": category_id,
        }
    return {
        "catalog": normalized_catalog,
        "libraries": normalized_libraries,
        "categories": normalized_categories,
        "items": normalized,
    }


def save_knowledge_metadata(tenant_id: str, metadata: dict, tenant_name: str = "") -> dict:
    ensure_tenant_storage(tenant_id, tenant_name or tenant_id)
    normalized = load_knowledge_metadata(tenant_id, tenant_name)
    catalog = metadata.get("catalog") if isinstance(metadata, dict) else []
    if isinstance(catalog, list):
        normalized["catalog"] = _normalize_tag_groups(catalog)
    libraries = metadata.get("libraries") if isinstance(metadata, dict) else []
    if isinstance(libraries, list):
        normalized["libraries"] = _normalize_library_records(libraries)
    categories = metadata.get("categories") if isinstance(metadata, dict) else []
    if isinstance(categories, list):
        normalized["categories"] = _normalize_category_records(categories, normalized["libraries"])
    items = metadata.get("items") if isinstance(metadata, dict) else {}
    if isinstance(items, dict):
        normalized["items"] = {}
        for key, value in items.items():
            if not isinstance(value, dict):
                continue
            tier = normalize_tier(str(value.get("tier") or key.split("/", 1)[0] or "permanent"))
            file_name = str(value.get("file") or key.split("/", 1)[-1] or "").strip()
            if not file_name:
                continue
            clean_key = _metadata_key(tier, file_name)
            library_id = str(value.get("library_id") or "").strip() or normalized["libraries"][0]["library_id"]
            if library_id not in {item["library_id"] for item in normalized["libraries"]}:
                library_id = normalized["libraries"][0]["library_id"]
            category_id = str(value.get("category_id") or "").strip()
            if category_id and category_id not in {item["category_id"] for item in normalized["categories"]}:
                category_id = ""
            normalized["items"][clean_key] = {
                "tier": tier,
                "tier_code": _public_tier_code(tier),
                "file": file_name,
                "tags": _normalize_tags(value.get("tags") if isinstance(value.get("tags"), list) else []),
                "library_id": library_id,
                "category_id": category_id,
            }
    catalog_groups = [dict(item) for item in (normalized.get("catalog") or []) if isinstance(item, dict)]
    known_values = set(_flatten_tag_group_values(catalog_groups))
    for tag in [
        tag
        for item in normalized["items"].values()
        for tag in (item.get("tags") or [])
    ]:
        clean = str(tag or "").strip()
        if clean and clean not in known_values:
            catalog_groups.append(
                {
                    "tag_id": _stable_id("tag", clean),
                    "name": clean,
                    "values": [
                        {
                            "value_id": _stable_id("tagv", clean),
                            "name": clean,
                            "synonyms": [],
                        }
                    ],
                }
            )
            known_values.add(clean)
    normalized["catalog"] = _normalize_tag_groups(catalog_groups)
    path = get_tenant_knowledge_metadata_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def get_knowledge_file_meta(tenant_id: str, tier: str, file_name: str, tenant_name: str = "") -> dict:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    key = _metadata_key(tier, file_name)
    item = metadata["items"].get(key)
    if item:
        return dict(item)
    canonical = normalize_tier(tier)
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    default_library_id = metadata["libraries"][0]["library_id"]
    return {
        "tier": canonical,
        "tier_code": _public_tier_code(canonical),
        "file": file_name,
        "tags": [],
        "library_id": default_library_id,
        "category_id": "",
    }


def set_knowledge_file_meta(
    tenant_id: str,
    *,
    tier: str,
    file_name: str,
    tags: list[str] | tuple[str, ...] | set[str] | None = None,
    library_id: str = "",
    category_id: str = "",
    tenant_name: str = "",
) -> dict:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    canonical = normalize_tier(tier)
    key = _metadata_key(canonical, file_name)
    existing = metadata["items"].get(key, {})
    library_id = str(library_id or existing.get("library_id") or metadata["libraries"][0]["library_id"]).strip()
    if library_id not in {item["library_id"] for item in metadata["libraries"]}:
        library_id = metadata["libraries"][0]["library_id"]
    category_id = str(category_id or existing.get("category_id") or "").strip()
    valid_categories = {item["category_id"] for item in metadata["categories"] if item["library_id"] == library_id}
    if category_id and category_id not in valid_categories:
        category_id = ""
    metadata["items"][key] = {
        "tier": canonical,
        "tier_code": _public_tier_code(canonical),
        "file": file_name,
        "tags": _normalize_tags(tags if tags is not None else existing.get("tags")),
        "library_id": library_id,
        "category_id": category_id,
    }
    catalog_groups = [dict(item) for item in (metadata.get("catalog") or []) if isinstance(item, dict)]
    known_values = set(_flatten_tag_group_values(catalog_groups))
    for tag in metadata["items"][key]["tags"]:
        clean = str(tag or "").strip()
        if not clean or clean in known_values:
            continue
        catalog_groups.append(
            {
                "tag_id": _stable_id("tag", clean),
                "name": clean,
                "values": [
                    {
                        "value_id": _stable_id("tagv", clean),
                        "name": clean,
                        "synonyms": [],
                    }
                ],
            }
        )
        known_values.add(clean)
    metadata["catalog"] = _normalize_tag_groups(catalog_groups)
    save_knowledge_metadata(tenant_id, metadata, tenant_name)
    return dict(metadata["items"][key])


def set_knowledge_file_tags(
    tenant_id: str,
    tier: str,
    file_name: str,
    tags: list[str] | tuple[str, ...] | set[str] | None,
    tenant_name: str = "",
) -> dict:
    return set_knowledge_file_meta(
        tenant_id,
        tier=tier,
        file_name=file_name,
        tags=tags,
        tenant_name=tenant_name,
    )


def delete_knowledge_file_meta(tenant_id: str, tier: str, file_name: str, tenant_name: str = "") -> None:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    metadata["items"].pop(_metadata_key(tier, file_name), None)
    save_knowledge_metadata(tenant_id, metadata, tenant_name)


def list_knowledge_tags(tenant_id: str, tenant_name: str = "") -> list[str]:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    return _normalize_tags(_flatten_tag_group_values(metadata.get("catalog") or []) + [
        tag
        for item in metadata["items"].values()
        for tag in (item.get("tags") or [])
    ])


def list_knowledge_tag_groups(tenant_id: str, tenant_name: str = "") -> list[dict]:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    return [dict(item) for item in (metadata.get("catalog") or []) if isinstance(item, dict)]


def list_knowledge_libraries(tenant_id: str, tenant_name: str = "") -> list[dict]:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    return [dict(item) for item in metadata.get("libraries") or []]


def list_knowledge_categories(tenant_id: str, tenant_name: str = "", library_id: str = "") -> list[dict]:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    categories = [dict(item) for item in metadata.get("categories") or []]
    if library_id:
        return [item for item in categories if str(item.get("library_id") or "") == str(library_id)]
    return categories


def save_knowledge_structure(
    tenant_id: str,
    *,
    libraries: list[dict] | None = None,
    categories: list[dict] | None = None,
    tenant_name: str = "",
) -> dict:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    if libraries is not None:
        metadata["libraries"] = _normalize_library_records(libraries)
    if categories is not None:
        metadata["categories"] = _normalize_category_records(categories, metadata["libraries"])
    save_knowledge_metadata(tenant_id, metadata, tenant_name)
    return metadata


def save_knowledge_tag_catalog(tenant_id: str, tags: list[str], tenant_name: str = "") -> list[str]:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    metadata["catalog"] = _normalize_tag_groups(tags)
    save_knowledge_metadata(tenant_id, metadata, tenant_name)
    return list_knowledge_tags(tenant_id, tenant_name)


def save_knowledge_tag_groups(tenant_id: str, groups: list[dict], tenant_name: str = "") -> list[dict]:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    metadata["catalog"] = _normalize_tag_groups(groups)
    save_knowledge_metadata(tenant_id, metadata, tenant_name)
    return list(metadata["catalog"])


def annotate_retrieval_results_with_scope(
    *,
    tenant_id: str,
    tenant_name: str = "",
    results: list[dict] | None,
    knowledge_scope: dict | None,
) -> list[dict]:
    metadata = load_knowledge_metadata(tenant_id, tenant_name)
    library_map = {str(item.get("library_id") or ""): dict(item) for item in metadata.get("libraries") or []}
    category_map = {str(item.get("category_id") or ""): dict(item) for item in metadata.get("categories") or []}
    scope = knowledge_scope if isinstance(knowledge_scope, dict) else {}
    allowed_tiers = {
        _public_tier_code(str(item))
        for item in (scope.get("tiers") or [])
        if str(item).strip()
    }
    allowed_tags = {
        str(item).strip().lower()
        for item in (scope.get("tags") or [])
        if str(item).strip()
    }
    allowed_files = {
        str(item).strip()
        for item in (scope.get("files") or [])
        if str(item).strip()
    }
    allowed_libraries = {
        str(item).strip()
        for item in (scope.get("libraries") or [])
        if str(item).strip()
    }
    allowed_categories = {
        str(item).strip()
        for item in (scope.get("categories") or [])
        if str(item).strip()
    }
    filtered: list[dict] = []
    for item in list(results or []):
        source = str(item.get("source") or "").strip()
        tier = str(item.get("tier") or "").strip() or "permanent"
        source_name = source.split("/", 1)[-1]
        meta = metadata["items"].get(_metadata_key(tier, source.split("/", 1)[-1]))
        if meta is None:
            meta = metadata["items"].get(_metadata_key(tier, source))
        tags = list((meta or {}).get("tags") or [])
        library_id = str((meta or {}).get("library_id") or "").strip()
        category_id = str((meta or {}).get("category_id") or "").strip()
        public_tier = _public_tier_code(tier)
        if allowed_tiers and public_tier not in allowed_tiers:
            continue
        if allowed_libraries and library_id not in allowed_libraries:
            continue
        if allowed_categories and category_id not in allowed_categories:
            continue
        if allowed_tags:
            tag_set = {str(tag).strip().lower() for tag in tags if str(tag).strip()}
            if not (tag_set & allowed_tags):
                continue
        if allowed_files:
            file_candidates = {
                source,
                source_name,
                f"{public_tier}/{source_name}",
                f"{tier}/{source_name}",
            }
            if not (file_candidates & allowed_files):
                continue
        enriched = dict(item)
        enriched["tags"] = tags
        enriched["tier_code"] = public_tier
        enriched["file_key"] = f"{public_tier}/{source_name}"
        enriched["library_id"] = library_id
        enriched["category_id"] = category_id
        enriched["library_name"] = str((library_map.get(library_id) or {}).get("name") or "")
        enriched["category_name"] = str((category_map.get(category_id) or {}).get("name") or "")
        filtered.append(enriched)
    return filtered
