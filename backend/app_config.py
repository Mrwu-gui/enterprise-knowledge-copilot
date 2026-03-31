"""业务配置与品牌配置管理。"""
from __future__ import annotations

import copy
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
APP_CONFIG_PATH = BASE_DIR / "data" / "app_config.json"

DEFAULT_APP_CONFIG = {
    "edition": "service_provider",
    "deployment_mode": "double_backend",
    "app_id": "default",
    "app_name": "企业知识库 Agent",
    "app_subtitle": "企业级 RAG 与三层知识库平台",
    "chat_title": "企业知识库 Agent",
    "chat_tagline": "连接私有知识、流程文档与实时资讯",
    "welcome_message": "你好，欢迎来到你的专属知识助理。你可以直接问制度、SOP、产品资料、操作手册或最新公告。",
    "agent_description": "面向企业内部知识问答、制度检索与流程辅助的智能体。",
    "logo": "",
    "recommended_questions": [
        "报销流程怎么走？",
        "新员工入职需要完成哪些步骤？",
        "合同审批规范是什么？",
    ],
    "short_term_memory": {
        "enabled": True,
        "max_turns": 6,
        "max_chars": 2400,
    },
    "login_hint": "企业账号登录 · 首次接入后请在后台完成密码与品牌配置",
    "input_placeholder": "输入你的问题...",
    "send_button_text": "发送",
    "record_chat_logs": True,
    "factory_enabled": True,
    "knowledge_namespace": "default",
    "knowledge_tiers": {
        "hotfix": {"label": "L3 热库", "weight": 3.0, "desc": "高时效、随时变化的知识"},
        "seasonal": {"label": "L2 增量库", "weight": 2.0, "desc": "阶段性更新、偶尔变更的知识"},
        "permanent": {"label": "L1 基础库", "weight": 1.0, "desc": "长期稳定、基本不变的知识"},
    },
    "theme": {
        "bg": "#f6f1df",
        "bg_soft": "#fffaf0",
        "surface": "rgba(255, 252, 244, 0.9)",
        "surface_strong": "#fffef8",
        "line": "#eadbb8",
        "text": "#4c3e2c",
        "muted": "#866f59",
        "accent": "#13b6ad",
        "accent_strong": "#0f9692",
        "accent_soft": "rgba(19, 182, 173, 0.14)",
        "warm": "#f3c067",
        "warm_soft": "rgba(243, 192, 103, 0.2)",
        "danger": "#d06b5a",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def ensure_app_config_file() -> None:
    """首次启动时补齐默认业务配置文件。"""
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not APP_CONFIG_PATH.exists():
        APP_CONFIG_PATH.write_text(
            json.dumps(DEFAULT_APP_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_app_config() -> dict:
    """读取业务配置，并与默认值合并，保证字段齐全。"""
    ensure_app_config_file()
    try:
        raw = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return _deep_merge(DEFAULT_APP_CONFIG, raw if isinstance(raw, dict) else {})


def save_app_config(config_data: dict) -> dict:
    """保存业务配置，避免缺字段导致前后台渲染断裂。"""
    if not isinstance(config_data, dict):
        raise ValueError("配置内容必须是 JSON 对象")
    merged = _deep_merge(DEFAULT_APP_CONFIG, config_data)
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_CONFIG_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return merged


def build_public_app_config(cfg: dict) -> dict:
    """把平台或租户配置转换成前台可直接消费的公开配置。"""
    theme = cfg.get("theme") or {}
    frontend_theme = {
        "primary": theme.get("primary") or theme.get("accent", "#10b981"),
        "primary_deep": theme.get("primary_deep") or theme.get("accent_strong", "#059669"),
        "primary_soft": theme.get("primary_soft") or theme.get("accent_soft", "#ecfdf5"),
        "bg": theme.get("bg", "#f8fafc"),
        "surface": theme.get("surface", "#ffffff"),
        "surface_strong": theme.get("surface_strong", "#ffffff"),
        "line": theme.get("line", "#e2e8f0"),
        "text": theme.get("text", "#0f172a"),
        "muted": theme.get("muted", "#64748b"),
        "danger": theme.get("danger", "#ef4444")
    }
    return {
        "edition": cfg.get("edition", "service_provider"),
        "deployment_mode": cfg.get("deployment_mode", "double_backend"),
        "app_name": cfg["app_name"],
        "app_subtitle": cfg["app_subtitle"],
        "chat_title": cfg["chat_title"],
        "chat_tagline": cfg["chat_tagline"],
        "welcome_message": cfg["welcome_message"],
        "agent_description": cfg.get("agent_description", ""),
        "logo": cfg.get("logo", ""),
        "recommended_questions": cfg.get("recommended_questions", []),
        "short_term_memory": cfg.get("short_term_memory", {"enabled": True, "max_turns": 6, "max_chars": 2400}),
        "login_hint": cfg["login_hint"],
        "input_placeholder": cfg["input_placeholder"],
        "send_button_text": cfg["send_button_text"],
        "record_chat_logs": bool(cfg.get("record_chat_logs", True)),
        "theme": frontend_theme,
    }


def get_public_app_config() -> dict:
    """输出给前台使用的公开配置。"""
    return build_public_app_config(load_app_config())


def get_deployment_mode() -> str:
    """读取当前部署模式。"""
    cfg = load_app_config()
    mode = str(cfg.get("deployment_mode", "double_backend")).strip().lower()
    return mode or "double_backend"


def get_knowledge_namespace() -> str:
    cfg = load_app_config()
    namespace = str(cfg.get("knowledge_namespace", "default")).strip().lower()
    return namespace or "default"


def get_runtime_knowledge_dir() -> str:
    namespace = get_knowledge_namespace()
    return str(BASE_DIR / "knowledge" / namespace)


def get_knowledge_tiers() -> dict:
    cfg = load_app_config()
    return resolve_knowledge_tiers(cfg)


def resolve_knowledge_tiers(config_data: dict | None) -> dict:
    """从指定配置对象解析知识层级。

    这样租户后台可以传自己的配置，不再被平台全局配置绑死。
    """
    cfg = config_data or {}
    tiers = cfg.get("knowledge_tiers") or {}
    if not isinstance(tiers, dict):
        return copy.deepcopy(DEFAULT_APP_CONFIG["knowledge_tiers"])
    return _deep_merge(DEFAULT_APP_CONFIG["knowledge_tiers"], tiers)
