from __future__ import annotations

import json
from pathlib import Path
import sys
import textwrap

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import list_user_agent_bindings, save_agent, save_user_agent_bindings
from backend.knowledge_assets import (
    list_knowledge_libraries,
    save_knowledge_structure,
    set_knowledge_file_meta,
)
from backend.rag import RAGEngine
from backend.retrieval_config import load_retrieval_config
from backend.tenant_config import get_tenant_knowledge_dir, save_tenant_app_config
from backend.workflow_config import load_workflow_config, save_workflow_config

TENANT_ID = "huadong_hospital"
TENANT_NAME = "华东协同医院"
DEMO_PHONE = "13800001234"

AGENT_ID = "agent_health_check_assistant"
WORKFLOW_ID = "wf_health_check_assistant"
LIBRARY_ID = "kb_health_check_assistant"
CATEGORY_ID = "cat_health_check_reference"

KNOWLEDGE_DIR = ROOT / "knowledge" / TENANT_ID / "permanent"
DOC_1 = "health_check_reference_ranges.md"
DOC_2 = "health_check_followup_guidance.md"

SCRIPT_NODE_CODE = r'''
import json
import re

text = str(((ctx.get("input") or {}).get("text")) or "").strip()

def pick_first(patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = str(match.group(1) or "").strip()
            if value:
                return value
    return ""

def pick_number(patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        raw = str(match.group(1) or "").strip().replace("，", ".").replace(",", ".")
        try:
            return float(raw)
        except Exception:
            continue
    return None

name = pick_first([
    r"(?:姓名|名字)[:：\s]*([\u4e00-\u9fa5A-Za-z·]{2,20})",
    r"患者([\u4e00-\u9fa5A-Za-z·]{2,20})",
])
gender = pick_first([r"(?:性别)[:：\s]*(男|女)"])
if not gender:
    if "男" in text and "女" not in text:
        gender = "男"
    elif "女" in text and "男" not in text:
        gender = "女"

age = pick_number([r"(?:年龄|age)[:：\s]*([0-9]{1,3})", r"([0-9]{1,3})\s*岁"])
sbp = pick_number([r"(?:收缩压|高压)[:：\s]*([0-9]{2,3}(?:\.[0-9]+)?)"])
dbp = pick_number([r"(?:舒张压|低压)[:：\s]*([0-9]{2,3}(?:\.[0-9]+)?)"])
if sbp is None or dbp is None:
    bp_match = re.search(r"血压[:：\s]*([0-9]{2,3}(?:\.[0-9]+)?)\s*[\/／]\s*([0-9]{2,3}(?:\.[0-9]+)?)", text, re.IGNORECASE)
    if bp_match:
        try:
            sbp = float(bp_match.group(1))
            dbp = float(bp_match.group(2))
        except Exception:
            pass

metrics = [
    {"key": "fasting_glucose", "label": "空腹血糖", "unit": "mmol/L", "value": pick_number([r"(?:空腹血糖|血糖|GLU)[:：\s]*([0-9]+(?:\.[0-9]+)?)"]), "low": 3.9, "high": 6.1, "critical_high": 7.0},
    {"key": "tc", "label": "总胆固醇", "unit": "mmol/L", "value": pick_number([r"(?:总胆固醇|胆固醇|TC)[:：\s]*([0-9]+(?:\.[0-9]+)?)"]), "low": 0.0, "high": 5.2, "critical_high": 6.2},
    {"key": "tg", "label": "甘油三酯", "unit": "mmol/L", "value": pick_number([r"(?:甘油三酯|TG)[:：\s]*([0-9]+(?:\.[0-9]+)?)"]), "low": 0.0, "high": 1.7, "critical_high": 2.3},
    {"key": "hdl", "label": "高密度脂蛋白", "unit": "mmol/L", "value": pick_number([r"(?:高密度脂蛋白|HDL)[:：\s]*([0-9]+(?:\.[0-9]+)?)"]), "low": 1.0, "high": 9.9, "critical_low": 0.9},
    {"key": "ldl", "label": "低密度脂蛋白", "unit": "mmol/L", "value": pick_number([r"(?:低密度脂蛋白|LDL)[:：\s]*([0-9]+(?:\.[0-9]+)?)"]), "low": 0.0, "high": 3.4, "critical_high": 4.1},
    {"key": "bmi", "label": "BMI", "unit": "", "value": pick_number([r"(?:BMI|体重指数)[:：\s]*([0-9]+(?:\.[0-9]+)?)"]), "low": 18.5, "high": 24.0, "critical_high": 28.0},
    {"key": "uric_acid", "label": "尿酸", "unit": "umol/L", "value": pick_number([r"(?:尿酸|UA)[:：\s]*([0-9]+(?:\.[0-9]+)?)"]), "low": 0.0, "high": 420.0, "critical_high": 480.0},
]

if sbp is not None:
    metrics.append({"key": "sbp", "label": "收缩压", "unit": "mmHg", "value": sbp, "low": 90.0, "high": 140.0, "critical_high": 160.0})
if dbp is not None:
    metrics.append({"key": "dbp", "label": "舒张压", "unit": "mmHg", "value": dbp, "low": 60.0, "high": 90.0, "critical_high": 100.0})

abnormal_items = []
normal_count = 0
high_count = 0
low_count = 0
risk_score = 0
measured_count = 0

for item in metrics:
    value = item.get("value")
    if value is None:
        continue
    measured_count += 1
    status = "正常"
    reason = ""
    if item["key"] == "hdl":
        if value < item.get("critical_low", item["low"]):
            status = "偏低"
            low_count += 1
            risk_score += 2
            reason = "保护性脂蛋白偏低"
        elif value < item["low"]:
            status = "偏低"
            low_count += 1
            risk_score += 1
            reason = "保护性脂蛋白略低"
        else:
            normal_count += 1
    else:
        if value > item.get("critical_high", item["high"]):
            status = "偏高"
            high_count += 1
            risk_score += 2
            reason = "明显高于参考范围"
        elif value > item["high"]:
            status = "偏高"
            high_count += 1
            risk_score += 1
            reason = "高于参考范围"
        elif item["low"] and value < item["low"]:
            status = "偏低"
            low_count += 1
            risk_score += 1
            reason = "低于参考范围"
        else:
            normal_count += 1
    item["status"] = status
    item["reason"] = reason
    item["reference"] = f'{item["low"]}-{item["high"]}' if item["high"] else f'>={item["low"]}'
    if status != "正常":
        abnormal_items.append(item)

if any(item["key"] == "fasting_glucose" and item["value"] and item["value"] >= 7.0 for item in metrics):
    risk_score += 1
if any(item["key"] == "ldl" and item["value"] and item["value"] >= 4.1 for item in metrics):
    risk_score += 1
if sbp is not None and dbp is not None and (sbp >= 160 or dbp >= 100):
    risk_score += 2

if risk_score >= 6:
    risk_level = "高风险"
elif risk_score >= 3:
    risk_level = "中风险"
else:
    risk_level = "低风险"

missing_fields = []
if not name:
    missing_fields.append("姓名")
if not gender:
    missing_fields.append("性别")
if age is None:
    missing_fields.append("年龄")
if measured_count < 2:
    missing_fields.append("至少 2 项核心体检指标（如空腹血糖、甘油三酯、LDL、血压、BMI）")

analysis_query_terms = [item["label"] for item in abnormal_items[:6]]
if not analysis_query_terms:
    analysis_query_terms = ["体检报告", "血糖", "血脂", "血压", "BMI"]

profile = {
    "name": name or "未提供",
    "gender": gender or "未提供",
    "age": int(age) if age is not None else "未提供",
}

metrics_rows = []
for item in metrics:
    value = item.get("value")
    if value is None:
        continue
    metrics_rows.append(
        {
            "label": item["label"],
            "value": value,
            "unit": item["unit"],
            "status": item["status"],
            "reference": item["reference"],
            "reason": item["reason"],
        }
    )

summary = {
    "risk_level": risk_level,
    "measured_count": measured_count,
    "abnormal_count": len(abnormal_items),
    "normal_count": normal_count,
    "high_count": high_count,
    "low_count": low_count,
    "key_findings": [item["label"] + item["status"] for item in abnormal_items[:5]],
}

chart_spec = {
    "version": "v1",
    "cards": [
        {"label": "风险等级", "value": risk_level},
        {"label": "异常项", "value": len(abnormal_items)},
        {"label": "已识别指标", "value": measured_count},
    ],
    "charts": [
        {
            "type": "donut",
            "title": "指标状态分布",
            "data": [
                {"name": "正常", "value": normal_count},
                {"name": "偏高", "value": high_count},
                {"name": "偏低", "value": low_count},
            ],
        }
    ],
}

markdown_lines = ["| 指标 | 数值 | 状态 | 参考范围 |", "| --- | --- | --- | --- |"]
for row in metrics_rows:
    value_text = f'{row["value"]}{row["unit"]}' if row["unit"] else str(row["value"])
    markdown_lines.append(f'| {row["label"]} | {value_text} | {row["status"]} | {row["reference"]} |')

health_focus_items = []
if any(item["key"] == "fasting_glucose" and item["status"] != "正常" for item in abnormal_items):
    health_focus_items.append({
        "title": "血糖管理关注",
        "content": "本次结果提示血糖指标存在异常，建议结合饮食结构、体重变化和既往血糖情况综合评估，并按时复查空腹血糖或糖化血红蛋白。"
    })
if any(item["key"] in {"tc", "tg", "ldl", "hdl"} and item["status"] != "正常" for item in abnormal_items):
    health_focus_items.append({
        "title": "血脂代谢关注",
        "content": "本次结果提示血脂代谢存在关注点，建议控制油脂和精制糖摄入，结合运动与体重管理观察变化。"
    })
if any(item["key"] in {"sbp", "dbp"} and item["status"] != "正常" for item in abnormal_items):
    health_focus_items.append({
        "title": "血压监测关注",
        "content": "如近期有波动或既往存在血压偏高情况，建议结合家庭血压监测结果和线下复评综合判断。"
    })
if any(item["key"] == "bmi" and item["status"] != "正常" for item in abnormal_items):
    health_focus_items.append({
        "title": "体重管理关注",
        "content": "体重相关指标提示代谢管理压力，建议同步关注腰围、饮食结构、运动频率和睡眠作息。"
    })
if not health_focus_items:
    health_focus_items.append({
        "title": "健康管理建议",
        "content": "本次已识别指标整体较平稳，建议保持规律作息、合理饮食和年度健康体检习惯。"
    })

followup_rows = []
for item in abnormal_items[:5]:
    clinic = "健康管理门诊"
    if item["key"] in {"fasting_glucose"}:
        clinic = "内分泌科 / 健康管理门诊"
    elif item["key"] in {"tc", "tg", "ldl", "hdl"}:
        clinic = "心内科 / 健康管理门诊"
    elif item["key"] in {"sbp", "dbp"}:
        clinic = "心内科 / 高血压门诊"
    elif item["key"] == "uric_acid":
        clinic = "风湿免疫科 / 肾内科"
    followup_rows.append({
        "item": item["label"],
        "action": "建议结合近期情况复查并持续观察",
        "timing": "建议 1-3 个月内复评",
        "clinic": clinic,
    })

report_note_lines = [
    f"本次共识别 {measured_count} 项指标，其中 {len(abnormal_items)} 项提示需重点关注。",
    "本页展示结果主要用于健康管理参考和体检结果解读，不替代门诊病历、检验正式报告或临床诊断意见。",
    "如存在持续不适、指标明显升高或既往慢病史，建议尽快到相应专科进一步评估。"
]

render_payload = {
    "type": "structured_report",
    "title": "体检报告摘要",
    "subtitle": "基于已录入体检指标完成风险分层、指标汇总、重点关注项提炼和复查建议整理。",
    "profile_items": [
        {"label": "姓名", "value": profile["name"]},
        {"label": "性别", "value": profile["gender"]},
        {"label": "年龄", "value": profile["age"]},
    ],
    "cards": [
        {"label": "风险等级", "value": risk_level},
        {"label": "异常项数量", "value": len(abnormal_items)},
        {"label": "已识别指标", "value": measured_count},
        {"label": "正常项数量", "value": normal_count},
        {"label": "偏高项数量", "value": high_count},
        {"label": "偏低项数量", "value": low_count},
    ],
    "tables": [
        {
            "title": "指标明细",
            "columns": [
                {"key": "label", "label": "指标"},
                {"key": "display_value", "label": "数值"},
                {"key": "status", "label": "状态", "kind": "status"},
                {"key": "reference", "label": "参考范围"},
                {"key": "reason", "label": "提示"},
            ],
            "rows": [
                {
                    "label": item["label"],
                    "display_value": f'{item["value"]}{item["unit"]}' if item["unit"] else str(item["value"]),
                    "status": item["status"],
                    "reference": item["reference"],
                    "reason": item["reason"] or "处于参考范围内",
                }
                for item in metrics_rows
            ],
        },
        {
            "title": "复查与就诊建议",
            "columns": [
                {"key": "item", "label": "关注指标"},
                {"key": "action", "label": "建议"},
                {"key": "timing", "label": "建议时点"},
                {"key": "clinic", "label": "建议门诊"},
            ],
            "rows": followup_rows or [{
                "item": "当前未识别明显异常项",
                "action": "建议保持年度体检和规律健康管理",
                "timing": "建议按年度复查",
                "clinic": "健康管理门诊",
            }],
        },
    ],
    "charts": chart_spec["charts"],
    "sections": [
        {
            "title": "重点关注项",
            "items": [
                {
                    "title": f'{item["label"]} {item["status"]}',
                    "content": f'当前结果 {item["value"]}{item["unit"]}，参考范围 {item["reference"]}。{item["reason"] or "建议结合线下复查继续判断。"}'
                }
                for item in abnormal_items[:4]
            ],
        }
    ] if abnormal_items else [],
    "sections_extra": [
        {
            "title": "健康管理提示",
            "items": health_focus_items,
        },
        {
            "title": "报告说明",
            "items": [{"content": line} for line in report_note_lines],
        },
    ],
}

result = {
    "profile": profile,
    "summary": summary,
    "metrics": metrics_rows,
    "abnormal_items": abnormal_items,
    "missing_fields": missing_fields,
    "missing_required": measured_count < 2,
    "analysis_query": "体检报告 解读 " + " ".join(analysis_query_terms),
    "chart_spec": chart_spec,
    "profile_json": json.dumps(profile, ensure_ascii=False),
    "summary_json": json.dumps(summary, ensure_ascii=False),
    "metrics_json": json.dumps(metrics_rows, ensure_ascii=False),
    "chart_json": json.dumps(chart_spec, ensure_ascii=False),
    "metrics_markdown": "\n".join(markdown_lines),
    "render_payload": render_payload,
}
'''


def workflow_script_code() -> str:
    return textwrap.indent(textwrap.dedent(SCRIPT_NODE_CODE).strip(), "            ")

DOC_1_CONTENT = """# 体检常见指标参考范围

以下内容用于体检结果解读与健康管理参考，不替代正式医疗诊断或医院检验标准。

## 血糖与血脂

- 空腹血糖参考范围：3.9-6.1 mmol/L
- 总胆固醇参考上限：5.2 mmol/L
- 甘油三酯参考上限：1.7 mmol/L
- LDL 参考上限：3.4 mmol/L
- HDL 参考下限：1.0 mmol/L

## 血压与体型

- 收缩压参考上限：140 mmHg
- 舒张压参考上限：90 mmHg
- BMI 参考区间：18.5-24.0

## 其他

- 尿酸参考上限：420 umol/L
- 如同时出现血糖偏高、血脂偏高、血压偏高，应优先提示代谢风险与复查建议
- 如数值明显偏离参考范围，应提示线下复诊或转人工，不输出确诊结论
"""

DOC_2_CONTENT = """# 体检报告解读规范

以下内容用于“体检报告助手”的结果解读与服务话术约束。

## 输出结构建议

1. 体检结论摘要：先说总体风险等级、异常项数量和本次最值得关注的指标
2. 主要异常指标说明：逐条解释偏高或偏低指标、与参考范围差异、提示的风险方向
3. 健康风险提示：把多项异常串联起来解读，例如代谢风险、体重管理压力、心血管风险线索
4. 健康管理与复查建议：饮食、运动、作息、体重管理、多久复查哪些项目
5. 就医提醒与报告说明：哪些情况建议尽快线下就诊，并补充“本结果用于健康管理参考”

## 风格要求

- 语言要像医院体检中心或健康管理中心交付给客户的正式报告
- 结论要稳重、完整、可信，不要像聊天回复
- 每部分都要有明确标题，最好能让客户一眼看出这是“报告”
- 不要输出“确诊”“处方”“必须服药”等结论
- 优先强调“结合既往病史、症状和临床医生意见综合判断”
- 如果用户提供信息不全，先礼貌指出缺失字段，再提示最关键的补充项

## 典型建议

- 血糖偏高：建议复查空腹血糖与糖化血红蛋白
- 血脂偏高：建议控制油脂与精制糖摄入，并结合运动管理
- BMI 偏高：提示体重管理与腰围监测
- 血压偏高：建议家庭监测血压并线下复评
- 尿酸偏高：提示饮水、饮食控制和必要时复查
"""


def ensure_demo_docs() -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_DIR / DOC_1).write_text(DOC_1_CONTENT, encoding="utf-8")
    (KNOWLEDGE_DIR / DOC_2).write_text(DOC_2_CONTENT, encoding="utf-8")


def ensure_knowledge_structure() -> None:
    libraries = save_knowledge_structure(
        TENANT_ID,
        tenant_name=TENANT_NAME,
        libraries=[
            {"library_id": item["library_id"], "name": item["name"], "description": item.get("description", "")}
            for item in list_knowledge_libraries(TENANT_ID, TENANT_NAME)
            if str(item.get("library_id") or "").strip() != LIBRARY_ID
        ] + [
            {
                "library_id": LIBRARY_ID,
                "name": "体检报告知识库",
                "description": "用于体检报告助手，沉淀参考范围、话术模板和复查建议。",
            }
        ],
        categories=[
            {"category_id": CATEGORY_ID, "library_id": LIBRARY_ID, "name": "参考范围与解读模板"}
        ],
    )
    _ = libraries
    set_knowledge_file_meta(
        TENANT_ID,
        tier="permanent",
        file_name=DOC_1,
        tags=["体检报告", "参考范围", "血糖", "血脂", "血压"],
        library_id=LIBRARY_ID,
        category_id=CATEGORY_ID,
        tenant_name=TENANT_NAME,
    )
    set_knowledge_file_meta(
        TENANT_ID,
        tier="permanent",
        file_name=DOC_2,
        tags=["体检报告", "复查建议", "健康管理", "话术规范"],
        library_id=LIBRARY_ID,
        category_id=CATEGORY_ID,
        tenant_name=TENANT_NAME,
    )


def build_workflow() -> dict:
    return {
        "workflow_id": WORKFLOW_ID,
        "name": "体检报告助手流程",
        "description": "用于体检报告结构化解析、风险分层、追问补充和报告生成。",
        "enabled": True,
        "sort_order": 150,
        "version": "V1.0",
        "status": "published",
        "nodes": [
            {"id": "start_1", "type": "start", "x": 80, "y": 180, "data": {"label": "开始节点", "triggerType": "API 调用"}},
            {
                "id": "script_1",
                "type": "script",
                "x": 330,
                "y": 180,
                "data": {
                    "label": "结构化解析",
                    "description": "从自然语言中提取体检指标并计算风险分层、图表数据。",
                    "scriptType": "Python",
                    "timeout": 20,
                    "code": workflow_script_code(),
                },
            },
            {
                "id": "condition_1",
                "type": "condition",
                "x": 590,
                "y": 180,
                "data": {
                    "label": "信息是否足够",
                    "description": "判断是否已提供至少两项核心体检指标。",
                    "condition": "nodes.script_1.result.result.missing_required == True",
                },
            },
            {
                "id": "ai_followup",
                "type": "ai",
                "x": 860,
                "y": 70,
                "data": {
                    "label": "生成补充追问",
                    "description": "缺信息时先追问，不直接输出完整报告。",
                    "prompt": "你是华东协同医院体检中心的“体检报告助手”，现在处于信息补全阶段。\n\n【用户原始输入】\n{{input.text}}\n\n【已提取画像】\n{{nodes.script_1.result.result.profile_json}}\n\n【缺失字段】\n{{nodes.script_1.result.result.missing_fields}}\n\n【你的任务】\n请像体检中心导检人员或健康管理师一样，先说明“当前信息已经足够做初步判断”，再告诉用户为了把报告写成一份更完整、更正规的体检解读，还需要补充哪些关键数据。\n\n【输出要求】\n1. 第一段先概括目前已掌握的信息，例如已提供了年龄、性别或部分异常指标。\n2. 第二段再说明还缺哪些关键字段，以及这些字段会影响哪部分解读，例如风险分层、复查建议、综合判断。\n3. 只追问最必要的 2 到 4 项，不要像问卷，不要一次把所有项目都抛给用户。\n4. 如果姓名/性别/年龄缺失，可以简短提醒；如果只是缺指标，优先追问空腹血糖、血脂、血压、BMI、尿酸这类核心项。\n5. 语气自然、专业、像医院健康管理中心服务人员，不要出现“作为AI”“信息不足无法判断”等生硬模板话。\n6. 最后一行单独给一个可直接照抄的补充示例，方便用户继续输入。\n7. 整体控制在 6 到 8 行，简洁但不能敷衍。",
                    "model": "__default__",
                    "temperature": 0.2,
                },
            },
            {
                "id": "knowledge_1",
                "type": "knowledge",
                "x": 860,
                "y": 290,
                "data": {
                    "label": "体检知识检索",
                    "description": "检索体检参考范围、复查建议和解读话术。",
                    "query": "{{nodes.script_1.result.result.analysis_query}}",
                    "knowledgeBase": LIBRARY_ID,
                    "topK": 4,
                    "threshold": 0.05,
                },
            },
            {
                "id": "ai_report",
                "type": "ai",
                "x": 1160,
                "y": 290,
                "data": {
                    "label": "生成体检报告",
                    "description": "根据结构化指标和知识库结果输出正式体检解读报告。",
                    "prompt": "你是华东协同医院体检中心的“体检报告助手”。你的职责不是替代医生做诊断，而是把体检数据整理成一份像大型医院体检中心或健康管理中心会正式展示给客户的体检解读报告：版式清晰、结论稳重、解释具体、建议明确、具备服务感。\n\n【用户原始输入】\n{{input.text}}\n\n【用户画像】\n{{nodes.script_1.result.result.profile_json}}\n\n【风险摘要】\n{{nodes.script_1.result.result.summary_json}}\n\n【结构化指标】\n{{nodes.script_1.result.result.metrics_json}}\n\n【表格版指标】\n{{nodes.script_1.result.result.metrics_markdown}}\n\n【基础图表规格】\n{{nodes.script_1.result.result.chart_json}}\n\n【知识库依据】\n{{nodes.knowledge_1.result.knowledge_text}}\n\n【任务目标】\n请输出一份正式、详细、适合客户展示的体检解读 HTML 报告。\n\n【输出协议】\n1. 只返回 HTML 片段，不要返回 JSON，不要返回 Markdown，不要加代码块，不要解释格式。\n2. 可以使用这些标签：div、section、h2、h3、p、ul、li、table、thead、tbody、tr、th、td、strong、span。\n3. 不要写 html、body、style、script 标签；只输出内容片段。\n4. 表格必须用标准 HTML table 输出，不要再用 Markdown 表格。\n5. 如果本次已有结构化图表或摘要卡片在前台显示，不要在正文里重复写“结构化结果”“前台统一渲染”等系统说明。\n\n【版式结构】\n请严格按下面顺序输出：\n1. `<section>` 体检结论摘要\n2. `<section>` 主要异常指标说明\n3. `<section>` 健康风险提示\n4. `<section>` 健康管理与复查建议\n5. `<section>` 就医提醒与报告说明\n\n【写作要求】\n1. 语言要像医院体检中心或健康管理中心的正式服务报告，详细、稳重、可信；不要口语化，不要像聊天。\n2. “主要异常指标说明”要逐条展开，每一项都要说明当前数值、参考范围差异、提示的风险方向和关注原因。\n3. “健康管理与复查建议”必须具体，至少覆盖饮食、运动、体重、作息、复查项目、复查时点和建议门诊。\n4. 至少输出 2 张 HTML 表格：\n   - 指标明细表\n   - 复查与就诊建议表\n5. 禁止输出：确诊、处方、手术方案、药品剂量、治疗承诺。\n6. 结尾必须补一句正式边界提醒：本结果仅用于健康管理建议，正式诊断请以临床医生意见为准。\n7. 直接输出 HTML 内容，不要出现 `answer_text`、`render_payload`、`structured_report` 这些系统字段名。",
                    "model": "__default__",
                    "temperature": 0.25,
                },
            },
            {"id": "end_1", "type": "end", "x": 1450, "y": 180, "data": {"label": "结束节点", "endType": "正常结束", "endMessage": "{{last.text}}"}},
        ],
        "connections": [
            {"id": "c1", "from": "start_1", "to": "script_1", "label": ""},
            {"id": "c2", "from": "script_1", "to": "condition_1", "label": ""},
            {"id": "c3", "from": "condition_1", "to": "ai_followup", "label": "信息不足"},
            {"id": "c4", "from": "condition_1", "to": "knowledge_1", "label": "信息充分"},
            {"id": "c5", "from": "knowledge_1", "to": "ai_report", "label": ""},
            {"id": "c6", "from": "ai_followup", "to": "end_1", "label": ""},
            {"id": "c7", "from": "ai_report", "to": "end_1", "label": ""},
        ],
        "app_overrides": {
            "chat_title": "体检报告助手",
            "chat_tagline": "支持自然语言录入体检指标，自动完成结构化解析、风险分层、图表汇总，并生成更接近大型医院体检中心风格的正式解读报告。",
            "welcome_message": "你好，我是华东协同医院体检中心的体检报告助手。你可以直接输入姓名、年龄、性别，以及空腹血糖、血脂、血压、BMI、尿酸等体检指标。我会先把数据整理为结构化结果，再输出一份包含体检结论摘要、异常指标说明、风险提示、复查建议和健康管理建议的正式报告。",
            "agent_description": "面向体检中心和健康管理场景，支持灵活输入体检数据，自动生成结构化报告卡片、异常项分析、图表汇总、复查建议和更接近大型医院体检中心风格的正式解读。",
            "recommended_questions": [
                "姓名张三，男，45岁，空腹血糖6.8，甘油三酯2.4，LDL 4.1，帮我出一份体检解读",
                "王女士 52 岁，总胆固醇 6.5、HDL 0.9、BMI 29，这份体检报告风险大吗？请给我一份详细一点的报告",
                "李先生 39 岁，血压 148/96、空腹血糖 7.2、尿酸 480，帮我生成一份包含复查建议和生活方式建议的体检解读",
            ],
            "input_placeholder": "输入姓名、年龄、性别和体检指标，例如：男 45岁，空腹血糖6.8，TG 2.4，LDL 4.1，BMI 28.2",
            "send_button_text": "生成解读",
        },
        "system_prompt": "你是华东协同医院体检中心的“体检报告助手”。\n你的职责是把用户输入的体检数据转化成一份更像大型医院体检中心或健康管理中心正式交付给客户的解读报告，而不是普通聊天回复。\n请优先根据结构化分析结果和知识库内容输出，不得脱离依据编造。\n可以给出健康管理建议、复查建议和就诊建议，但不得输出确诊、用药、处方和治疗方案。\n输出风格应正式、完整、稳重，避免口语化、模板化、过短或明显敷衍的表述。\n\n【知识库内容开始】\n{knowledge_context}\n【知识库内容结束】",
    }


def upsert_workflow() -> dict:
    cfg = load_workflow_config(tenant_id=TENANT_ID, tenant_name=TENANT_NAME)
    items = [item for item in cfg.get("items") or [] if str(item.get("workflow_id") or "").strip() != WORKFLOW_ID]
    items.append(build_workflow())
    items.sort(key=lambda item: int(item.get("sort_order") or 9999))
    saved = save_workflow_config(
        {"default_workflow_id": cfg.get("default_workflow_id") or "", "items": items},
        tenant_id=TENANT_ID,
        tenant_name=TENANT_NAME,
    )
    return next(item for item in saved["items"] if item["workflow_id"] == WORKFLOW_ID)


def upsert_agent() -> dict:
    return save_agent(
        tenant_id=TENANT_ID,
        agent_id=AGENT_ID,
        name="体检报告助手",
        description="面向体检中心和健康管理场景，支持灵活输入体检数据，自动生成结构化报告卡片、异常项分析、图表汇总、复查建议和更接近大型医院体检中心风格的正式解读。",
        status="published",
        enabled=True,
        welcome_message="你好，我是华东协同医院体检中心的体检报告助手。直接输入姓名、年龄、性别，以及血糖、血脂、血压、BMI、尿酸等体检指标，我会先进行结构化分析，再输出一份包含体检结论摘要、异常指标说明、风险提示、图表汇总、复查建议和健康管理建议的正式体检报告。",
        input_placeholder="例如：张三，男，45岁，空腹血糖6.8，甘油三酯2.4，LDL 4.1，BMI 28",
        recommended_questions=[
            "姓名张三，男，45岁，空腹血糖6.8，甘油三酯2.4，LDL 4.1，帮我出一份体检解读",
            "王女士 52 岁，总胆固醇 6.5、HDL 0.9、BMI 29，这份体检报告风险大吗？请给我一份详细一点的报告",
            "李先生 39 岁，血压 148/96、空腹血糖 7.2、尿酸 480，帮我生成一份包含复查建议和生活方式建议的体检解读",
        ],
        prompt_override="你是华东协同医院体检中心的体检报告助手。\n\n你的输出目标不是一句简单回答，而是一份明显更接近大型医院体检中心正式服务报告风格的体检解读。\n请优先根据结构化指标、流程结果和知识库口径来组织答复，体现出“数据被解析过、风险被判断过、建议有层次、结论有依据”。\n\n回答时请严格遵守以下要求：\n1. 必须按照“体检结论摘要 / 主要异常指标说明 / 健康风险提示 / 健康管理与复查建议 / 就医提醒与报告说明”这五部分来写。\n2. 体检结论摘要里要明确风险等级、异常项数量、已识别指标数量，以及本次最值得关注的 2 到 3 项指标。\n3. 主要异常指标说明里要逐条展开，写清楚当前数值、参考范围差异、提示的风险方向和关注原因。\n4. 健康风险提示里要把多项异常串联起来解释，体现综合判断能力，但不能写成确诊。\n5. 健康管理与复查建议必须具体，至少覆盖饮食、运动、体重、作息、复查项目、复查时点和建议门诊。\n6. 如果信息不足，先追问最关键字段，不要直接输出空泛报告。\n7. 语言必须正式、稳重、完整，不能口语化，不能像普通聊天，也不能显得过短或敷衍。\n8. 不得输出确诊、药物处方、治疗方案或绝对化医学结论。\n9. 结尾必须补一句正式边界提醒：本结果仅用于健康管理建议，正式诊断请以临床医生意见为准。",
        workflow_id=WORKFLOW_ID,
        knowledge_scope={"libraries": [LIBRARY_ID], "tags": [], "files": []},
        model_override={},
        tool_scope=[],
        mcp_servers=[],
        streaming=True,
        fallback_enabled=True,
        fallback_message="当前环境未能完整生成体检解读，请稍后重试，或补充更多指标后再试。",
        show_recommended=True,
        is_default=False,
    )


def bind_demo_account() -> list[str]:
    existing = list_user_agent_bindings(tenant_id=TENANT_ID, phone=DEMO_PHONE)
    merged = []
    seen = set()
    for agent_id in existing + [AGENT_ID]:
        clean = str(agent_id or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            merged.append(clean)
    save_user_agent_bindings(tenant_id=TENANT_ID, phone=DEMO_PHONE, agent_ids=merged)
    return merged


def rebuild_index() -> int:
    app_cfg = save_tenant_app_config(TENANT_ID, TENANT_NAME, {})
    retrieval_cfg = load_retrieval_config(tenant_id=TENANT_ID, tenant_name=TENANT_NAME)
    engine = RAGEngine(
        knowledge_dir=get_tenant_knowledge_dir(TENANT_ID),
        app_config=app_cfg,
        retrieval_config=retrieval_cfg,
        knowledge_namespace=TENANT_ID,
    )
    return engine.build_index()


def main() -> None:
    ensure_demo_docs()
    ensure_knowledge_structure()
    workflow = upsert_workflow()
    agent = upsert_agent()
    bindings = bind_demo_account()
    chunks = rebuild_index()
    print(
        json.dumps(
            {
                "ok": True,
                "tenant_id": TENANT_ID,
                "workflow_id": workflow["workflow_id"],
                "agent_id": agent["agent_id"],
                "bindings": bindings,
                "indexed_chunks": chunks,
                "demo_questions": agent["recommended_questions"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
