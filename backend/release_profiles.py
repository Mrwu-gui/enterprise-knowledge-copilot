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


RELEASE_PROFILES = {
    "enterprise": {
        "key": "enterprise",
        "label": "企业版",
        "deployment_mode": "single_backend",
        "summary": "单后台版本，适合个人、小团队、单企业私有部署。",
        "menus": [
            "账户管理",
            "企业定制化",
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


def _write_release_readme(dest_dir: Path, profile: dict) -> None:
    """写入版本说明，方便直接打包售卖。"""
    readme = f"""# {profile['label']}

## 版本定位

{profile['summary']}

## 默认入口

{json.dumps(profile['entries'], ensure_ascii=False, indent=2)}

## 菜单结构

{json.dumps(profile['menus'], ensure_ascii=False, indent=2)}

## 说明

- 该版本由母版项目一键导出生成。
- 保留通用代码底座，按版本配置切换页面入口与产品文案。
- 如需升级到其他版本，请在母版项目中重新导出。
"""
    (dest_dir / "RELEASE_EDITION.md").write_text(readme, encoding="utf-8")


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
        ".codex_write_test*",
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
        bundle_dir / "docs" / "内部文档索引.md",
        bundle_dir / "docs" / "版本打包说明.md",
        bundle_dir / "frontend" / "factory_v2.html",
        bundle_dir / "newUI",
        bundle_dir / "data" / "app.db",
        bundle_dir / "data" / "qdrant_store",
        bundle_dir / "data" / "tenants" / "acme_acceptance",
        bundle_dir / "data" / "tenants" / "beta_acceptance",
        bundle_dir / "data" / "tenants" / "gamma_acceptance",
        bundle_dir / "data" / "tenants" / "smoke_enterprise",
        bundle_dir / "knowledge" / "acme_acceptance",
        bundle_dir / "knowledge" / "smoke_enterprise",
    ]
    cleanup_targets.extend(bundle_dir.glob("tmp_*.py"))
    for target in cleanup_targets:
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()
    (bundle_dir / "data" / "qdrant_store").mkdir(parents=True, exist_ok=True)

    _write_release_readme(bundle_dir, profile)

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
