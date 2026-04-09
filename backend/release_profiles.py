"""版本配置与导出打包。"""
from __future__ import annotations

import copy
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output" / "releases"
SAFE_QDRANT_PLACEHOLDER = {
    "enabled": True,
    "mode": "local",
    "url": "",
    "api_key": "",
    "path": "data/qdrant_store_template",
}
SAFE_WORKFLOW_TEMPLATE = {
    "default_workflow_id": "main",
    "items": [
        {
            "workflow_id": "main",
            "name": "默认工作流",
            "description": "当前租户主流程。",
            "enabled": True,
            "sort_order": 100,
            "version": "V1.0",
            "status": "draft",
            "updated_at": "",
            "nodes": [],
            "connections": [],
            "app_overrides": {
                "chat_title": "",
                "chat_tagline": "",
                "welcome_message": "",
                "agent_description": "",
                "recommended_questions": [],
                "input_placeholder": "",
                "send_button_text": "",
            },
            "system_prompt": "你是企业知识库的租户专属智能助理。\n\n请优先根据下方知识库内容回答；如果知识库没有明确答案，先说明知识不足，再给出谨慎建议。\n\n【知识库内容开始】\n{knowledge_context}\n【知识库内容结束】\n",
        }
    ],
}
SAFE_APP_CONFIG_TEMPLATE_FIELDS = {
    "app_name": "",
    "app_subtitle": "",
    "chat_title": "",
    "chat_tagline": "",
    "welcome_message": "",
    "agent_description": "",
    "recommended_questions": [],
    "login_hint": "",
    "input_placeholder": "",
    "send_button_text": "",
}


RELEASE_PROFILES = {
    "enterprise": {
        "key": "enterprise",
        "label": "企业版",
        "deployment_mode": "single_backend",
        "summary": "单后台版本，适合个人、小团队、单企业私有部署。",
        "menus": [
            "账户管理",
            "企业定制化",
            "工作流配置",
            "知识库设置",
            "Python脚本设置",
            "模型配置",
            "日志查看",
            "问答测试",
        ],
        "entries": {
            "backend": "/tenant",
            "login": "/login",
            "chat": "/chat",
        },
        "docs": [
            "docs/项目总说明.md",
            "docs/租户手册.md",
        ],
    },
    "service_provider": {
        "key": "service_provider",
        "label": "服务商版",
        "deployment_mode": "double_backend",
        "summary": "双后台版本，适合服务商、多客户托管和 SaaS 运营。",
        "menus": {
            "platform": [
                "企业账户管理",
                "平台总日志",
            ],
            "tenant": [
                "账户管理",
                "企业定制化",
                "工作流配置",
                "知识库设置",
                "Python脚本设置",
                "模型配置",
                "日志查看",
                "问答测试",
            ],
        },
        "entries": {
            "platform": "/admin",
            "tenant": "/tenant",
            "login": "/login",
            "chat": "/chat",
        },
        "docs": [
            "docs/项目总说明.md",
            "docs/租户手册.md",
        ],
    },
}


def list_release_profiles() -> list[dict]:
    """返回可销售版本清单。"""
    return [copy.deepcopy(item) for item in RELEASE_PROFILES.values()]


def get_release_profile(profile_key: str) -> dict:
    """读取版本配置。"""
    key = str(profile_key or "").strip()
    if key not in RELEASE_PROFILES:
        raise ValueError(f"未知版本：{profile_key}")
    return copy.deepcopy(RELEASE_PROFILES[key])


def _format_menu_lines(profile: dict) -> str:
    menus = profile.get("menus") or {}
    if isinstance(menus, list):
        return "\n".join(f"- {item}" for item in menus)
    if isinstance(menus, dict):
        parts: list[str] = []
        for role, items in menus.items():
            role_label = "平台后台" if role == "platform" else "租户后台"
            parts.append(f"### {role_label}")
            parts.extend(f"- {item}" for item in items)
            parts.append("")
        return "\n".join(parts).strip()
    return "- 暂无"


def _build_project_overview(profile: dict) -> str:
    entries = profile.get("entries") or {}
    entry_lines = []
    for key, path in entries.items():
        label = {
            "platform": "平台后台",
            "tenant": "租户后台",
            "backend": "后台入口",
            "login": "登录入口",
            "chat": "聊天入口",
        }.get(key, key)
        entry_lines.append(f"- {label}：`{path}`")

    if profile["key"] == "enterprise":
        role_text = """本版本面向单企业或小团队私有部署场景，默认提供一个租户后台和一个前台聊天入口。

适合：

- 单企业内部知识助手
- 小团队客服问答助手
- 私有资料查询与 FAQ 场景
- 不需要平台总后台、多客户托管能力的交付形态"""
    else:
        role_text = """本版本面向服务商、多客户托管和 SaaS 运营场景，默认提供平台后台、租户后台和前台聊天入口。

适合：

- 服务商统一托管多个企业客户
- 需要平台级企业账户管理的交付形态
- 需要同时维护平台运营与租户自配置的 SaaS 场景
- 面向多客户复用的一套企业知识助手系统"""

    return f"""# 项目说明

## 1. 当前版本

- 版本名称：{profile['label']}
- 部署模式：`{profile['deployment_mode']}`
- 版本定位：{profile['summary']}

## 2. 版本介绍

{role_text}

## 3. 默认入口

{os.linesep.join(entry_lines)}

## 4. 当前版本包含的后台能力

{_format_menu_lines(profile)}

## 5. 核心能力

- 多租户知识空间管理
- 可视化工作流编排与 LangGraph 流程引擎
- 企业知识库接入与三层知识结构
- 关键词检索、向量检索、混合检索、Rerank 精排
- 模型配置、检索配置、Prompt 配置、工作流配置
- 问答测试、日志查看、检索解释
- 会话问答、缓存命中、可观测追踪
- 支持 AI 节点、知识检索、条件判断、HTTP 请求、脚本执行、通知、子流程等工作流节点
- 支持本地或云端模型、Embedding、Rerank 方案组合

## 6. 交付说明

- 本版本已按当前交付形态整理好页面入口、目录结构和启动方式
- 首次启动后，建议先完成管理员密码、模型 Key 与知识库内容配置
- 如需扩展菜单、继续二次开发或新增企业场景，可直接在此基础上调整
"""


def _build_project_tutorial(profile: dict) -> str:
    entries = profile.get("entries") or {}
    login_path = entries.get("login", "/login")
    chat_path = entries.get("chat", "/chat")
    if profile["key"] == "enterprise":
        backend_path = entries.get("backend", "/tenant")
        steps = f"""# 项目教程

## 1. 启动后先访问哪里

- 登录页：`{login_path}`
- 租户后台：`{backend_path}`
- 前台聊天：`{chat_path}`

## 2. 默认后台账号

- 租户后台账号：`tenant_default`
- 租户后台密码：`tenant2026`

首次登录后，建议你立即修改默认密码。

## 3. 推荐使用顺序

1. 先进入租户后台完成企业定制化
2. 上传或整理知识库文件
3. 配置模型、检索、Embedding、Rerank
4. 如需业务自动化，再配置工作流节点、流程发布和联动逻辑
5. 如需自动同步数据，再配置 Python 采集脚本
6. 在“问答测试”里验证检索与回答效果
7. 验证通过后，再给终端用户开放前台聊天页

## 4. 租户后台重点菜单

- 企业定制化：配置名称、欢迎语、主题色、推荐问题、提示词
- 工作流配置：可视化编排知识检索、AI 节点、条件判断、HTTP、通知等流程
- 知识库设置：上传和维护知识文件
- Python脚本设置：配置自动采集规则
- 模型配置：配置主模型、备用模型和 Key 池
- 日志查看：查看请求日志、聊天日志、护栏事件与检索解释
- 问答测试：实时验证当前知识库问答效果

## 5. 前台聊天怎么用

- 用户从登录页进入系统
- 登录成功后进入聊天页
- 支持点击推荐问题，也支持手动输入问题
- 系统会优先基于企业知识库返回答案

## 6. 首次交付建议

- 先放 10 到 30 份高频文档验证效果
- 先确定 System Prompt 与推荐问题风格
- 先在后台问答测试页跑通高频问题，再正式给用户开放
"""
    else:
        platform_path = entries.get("platform", "/admin")
        tenant_path = entries.get("tenant", "/tenant")
        steps = f"""# 项目教程

## 1. 启动后先访问哪里

- 登录页：`{login_path}`
- 平台后台：`{platform_path}`
- 租户后台：`{tenant_path}`
- 前台聊天：`{chat_path}`

## 2. 默认后台账号

- 平台后台账号：`admin`
- 平台后台密码：`rag2026`
- 默认租户后台账号：`tenant_default`
- 默认租户后台密码：`tenant2026`

首次登录后，建议你立即修改默认密码。

## 3. 服务商推荐使用顺序

1. 先登录平台后台创建企业租户
2. 给每个租户分配后台账号与基础配置
3. 进入租户后台完成品牌、Prompt、知识库和模型配置
4. 根据企业业务编排工作流并完成发布
5. 用租户后台的“问答测试”校验效果
6. 再开放给终端用户使用前台聊天页

## 4. 平台后台负责什么

- 企业账户管理
- 平台总日志查看
- 多企业统一运营与管理
- 版本导出与平台级配置能力

## 5. 租户后台负责什么

- 企业定制化配置
- 工作流配置与发布
- 知识库上传与维护
- 采集脚本配置
- 模型与检索配置
- 日志查看与问答测试

## 6. 前台聊天怎么交付给客户

- 给客户分配手机号账号或登录账号
- 客户通过登录页进入自己的企业知识助手
- 每个租户使用自己的品牌配置、知识库和模型能力

## 7. 多客户托管建议

- 平台侧只负责租户创建和全局运营
- 每个租户的知识、Prompt、模型配置应保持独立
- 正式交付前先在租户后台做检索和回答验收
"""
    return steps


def _build_code_guide(profile: dict) -> str:
    if profile["key"] == "enterprise":
        page_lines = """- `frontend/login_v2.html`：登录页
- `frontend/tenant_v2.html`：租户后台
- `frontend/index_v2.html`：前台聊天页"""
        route_lines = """- `/login`
- `/tenant`
- `/chat`
- `/api/tenant/workflows*`
- `/api/tenant/*`
- `/api/chat`"""
    else:
        page_lines = """- `frontend/login_v2.html`：登录页
- `frontend/admin_v2.html`：平台后台
- `frontend/tenant_v2.html`：租户后台
- `frontend/index_v2.html`：前台聊天页"""
        route_lines = """- `/login`
- `/admin`
- `/tenant`
- `/chat`
- `/api/tenant/workflows*`
- `/api/admin/*`
- `/api/tenant/*`
- `/api/chat`"""

    return f"""# 代码说明

## 1. 先看哪几个文件

- `backend/main.py`：项目总入口，页面路由和 API 基本都在这里
- `backend/chat_workflow.py`：问答主链，包含护栏、缓存、工具、检索、Prompt、生成、落日志
- `backend/workflow_runtime.py`：工作流运行时，负责节点调度、状态流转和工作流执行
- `backend/workflow_config.py`：工作流配置读写与模板管理
- `backend/retrieval_orchestration.py`：检索策略判断、Query Rewrite、重试和路由选择
- `backend/database.py`：数据库读写，包含账号、租户、会话、日志等
- `backend/tenant_config.py`：租户配置文件路径和读写
- `backend/model_config.py`：模型配置与 Key 池
- `backend/retrieval_config.py`：检索配置、qdrant 本地路径等

## 2. 前端主要文件

{page_lines}

## 3. 当前版本常用路由

{route_lines}

## 4. 数据和配置放哪里

- `data/app.db`：运行数据库
- `data/tenants/<tenant_id>/`：租户配置目录
- `knowledge/`：知识文件目录
- `data/model_config.json`：模型配置
- `data/retrieval_config.json`：检索配置
- `data/workflow_config.json`：平台或默认工作流模板

## 5. 如果要改功能，建议先看

- 改登录和页面入口：先看 `backend/main.py`
- 改聊天问答：先看 `backend/chat_workflow.py`
- 改工作流编排：先看 `backend/workflow_runtime.py`、`backend/workflow_config.py`
- 改检索策略：先看 `backend/retrieval_orchestration.py`
- 改模型和检索配置：先看 `backend/model_config.py`、`backend/retrieval_config.py`
- 改数据库和会话：先看 `backend/database.py`
- 改页面展示：先看对应的 `frontend/*.html`
"""


def _write_release_docs(dest_dir: Path, profile: dict) -> None:
    """写入交付版文档，仅保留几份面向交付的说明。"""
    (dest_dir / "项目说明.md").write_text(_build_project_overview(profile), encoding="utf-8")
    (dest_dir / "项目教程.md").write_text(_build_project_tutorial(profile), encoding="utf-8")
    (dest_dir / "代码说明.md").write_text(_build_code_guide(profile), encoding="utf-8")


def _safe_json_load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_json_dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _sanitize_model_config(path: Path) -> None:
    if not path.exists():
        return
    data = _safe_json_load(path)
    if not data:
        return
    data.pop("api_keys", None)
    data["base_url"] = ""
    data["model_primary"] = ""
    data["model_fallback"] = ""
    providers = []
    for item in list(data.get("providers") or []):
        if not isinstance(item, dict):
            continue
        providers.append(
            {
                "id": str(item.get("id") or "").strip() or "provider_1",
                "label": "",
                "base_url": "",
                "model_primary": "",
                "model_fallback": "",
                "api_keys": [],
            }
        )
    data["providers"] = providers
    _safe_json_dump(path, data)


def _sanitize_retrieval_config(path: Path) -> None:
    if not path.exists():
        return
    data = _safe_json_load(path)
    if not data:
        return
    qdrant = dict(data.get("qdrant") or {})
    qdrant.update(SAFE_QDRANT_PLACEHOLDER)
    data["qdrant"] = qdrant
    embedding = dict(data.get("embedding") or {})
    embedding["api_key"] = ""
    embedding["base_url"] = str(embedding.get("base_url") or "")
    data["embedding"] = embedding
    rerank = dict(data.get("rerank") or {})
    rerank["api_key"] = ""
    rerank["base_url"] = str(rerank.get("base_url") or "")
    data["rerank"] = rerank
    _safe_json_dump(path, data)


def _sanitize_app_config(path: Path) -> None:
    if not path.exists():
        return
    data = _safe_json_load(path)
    if not data:
        return
    for key, value in SAFE_APP_CONFIG_TEMPLATE_FIELDS.items():
        data[key] = copy.deepcopy(value)
    _safe_json_dump(path, data)


def _sanitize_workflow_config(path: Path) -> None:
    if not path.exists():
        return
    _safe_json_dump(path, copy.deepcopy(SAFE_WORKFLOW_TEMPLATE))


def _sanitize_bundle_configs(bundle_dir: Path) -> None:
    """导出前对所有配置做脱敏处理。"""
    for env_path in [bundle_dir / ".env", bundle_dir / ".env.local", bundle_dir / ".env.production"]:
        if env_path.exists():
            env_path.unlink()

    sensitive_files = [
        bundle_dir / "config" / "api_keys.txt",
        bundle_dir / "data" / "app.db",
        bundle_dir / "data" / "app.db-shm",
        bundle_dir / "data" / "app.db-wal",
        bundle_dir / "output" / "授权码_100个.xlsx",
    ]
    for path in sensitive_files:
        if path.exists():
            path.unlink()

    shutil.rmtree(bundle_dir / "data" / "qdrant_store", ignore_errors=True)
    shutil.rmtree(bundle_dir / "data" / "qdrant_store_template", ignore_errors=True)

    for tenant_key_file in (bundle_dir / "data" / "tenants").glob("*/api_keys.txt"):
        tenant_key_file.unlink(missing_ok=True)

    # 清掉租户私有知识空间，只保留基础目录结构。
    knowledge_root = bundle_dir / "knowledge"
    for tenant_dir in knowledge_root.iterdir() if knowledge_root.exists() else []:
        if not tenant_dir.is_dir():
            continue
        if tenant_dir.name in {"hotfix", "seasonal", "permanent"}:
            continue
        shutil.rmtree(tenant_dir, ignore_errors=True)

    # 仅保留 default 模板租户，其余租户目录全部移除，避免把真实企业配置打包带走。
    tenants_root = bundle_dir / "data" / "tenants"
    for tenant_dir in tenants_root.iterdir() if tenants_root.exists() else []:
        if not tenant_dir.is_dir():
            continue
        if tenant_dir.name == "default":
            continue
        shutil.rmtree(tenant_dir, ignore_errors=True)

    _sanitize_app_config(bundle_dir / "data" / "app_config.json")
    _sanitize_model_config(bundle_dir / "data" / "model_config.json")
    _sanitize_retrieval_config(bundle_dir / "data" / "retrieval_config.json")
    _sanitize_workflow_config(bundle_dir / "data" / "workflow_config.json")
    _sanitize_app_config(bundle_dir / "data" / "tenants" / "default" / "app_config.json")
    _sanitize_model_config(bundle_dir / "data" / "tenants" / "default" / "model_config.json")
    _sanitize_retrieval_config(bundle_dir / "data" / "tenants" / "default" / "retrieval_config.json")
    _sanitize_workflow_config(bundle_dir / "data" / "tenants" / "default" / "workflow_config.json")


def _remove_extra_markdown(bundle_dir: Path) -> None:
    """导出包中仅保留顶层几份交付文档，其余 markdown 全部移除。"""
    keep = {
        bundle_dir / "项目说明.md",
        bundle_dir / "项目教程.md",
        bundle_dir / "代码说明.md",
    }
    for md_path in bundle_dir.rglob("*.md"):
        if md_path in keep:
            continue
        md_path.unlink(missing_ok=True)


def export_release_bundle(*, profile_key: str, current_app_config: dict) -> dict:
    """导出指定版本的可交付包。

    这里先走轻量版本化：
    - 保留共用代码底座
    - 写入版本配置
    - 输出版本说明
    - 打成 zip 包
    """
    profile = get_release_profile(profile_key)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_name = f"lok_{profile_key}_{timestamp}"
    bundle_dir = OUTPUT_DIR / bundle_name

    ignore = shutil.ignore_patterns(
        ".git",
        ".DS_Store",
        "__pycache__",
        "venv",
        "output",
        "output/releases",
        "*.pyc",
        "*.pyo",
        "*.bak",
        "*.bak2",
        ".codex_write_test*",
        ".env",
        ".env.local",
        ".env.production",
        "api_keys.txt",
        "app.db",
        "app.db-shm",
        "app.db-wal",
        "qdrant_store",
        "qdrant_store_template",
    )
    shutil.copytree(BASE_DIR, bundle_dir, dirs_exist_ok=False, ignore=ignore)

    app_config_path = bundle_dir / "data" / "app_config.json"
    merged = copy.deepcopy(current_app_config)
    merged["edition"] = profile["key"]
    merged["deployment_mode"] = profile["deployment_mode"]
    merged["release_profile"] = {
        "label": profile["label"],
        "summary": profile["summary"],
        "entries": profile["entries"],
    }
    merged["factory_enabled"] = False
    app_config_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    cleanup_targets = [
        bundle_dir / "docs",
        bundle_dir / "frontend" / "factory_v2.html",
        bundle_dir / "newUI",
        bundle_dir / "seed_demo_agents.py",
        bundle_dir / "data" / "tenants" / "acme_acceptance",
        bundle_dir / "data" / "tenants" / "beta_acceptance",
        bundle_dir / "data" / "tenants" / "gamma_acceptance",
        bundle_dir / "data" / "tenants" / "smoke_enterprise",
        bundle_dir / "knowledge" / "acme_acceptance",
        bundle_dir / "knowledge" / "smoke_enterprise",
        bundle_dir / "frontend" / "tenant_v2.html.bak2",
    ]
    cleanup_targets.extend(bundle_dir.glob("tmp_*.py"))
    for target in cleanup_targets:
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()
    for cache_dir in bundle_dir.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
    _sanitize_bundle_configs(bundle_dir)
    (bundle_dir / "data" / "qdrant_store_template").mkdir(parents=True, exist_ok=True)
    (bundle_dir / "data" / "qdrant_store_template" / "README.txt").write_text(
        "该目录为本地向量库占位目录，正式部署后会在此生成本地检索数据，请勿提交真实索引数据。",
        encoding="utf-8",
    )

    _write_release_docs(bundle_dir, profile)
    _remove_extra_markdown(bundle_dir)

    zip_path = OUTPUT_DIR / f"{bundle_name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(bundle_dir):
            for file in files:
                abs_path = Path(root) / file
                rel_path = abs_path.relative_to(bundle_dir.parent)
                zf.write(abs_path, rel_path.as_posix())

    return {
        "profile": profile,
        "bundle_dir": str(bundle_dir),
        "zip_path": str(zip_path),
        "zip_name": zip_path.name,
    }
