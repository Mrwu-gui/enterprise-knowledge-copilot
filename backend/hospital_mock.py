"""医院演示场景的本地 MCP mock。"""
from __future__ import annotations

import json


MOCK_HOSPITAL_MCP_URLS = {
    "http://127.0.0.1:8000/api/mock/hospital-mcp",
    "http://localhost:8000/api/mock/hospital-mcp",
}


def is_mock_hospital_mcp_url(url: str) -> bool:
    return str(url or "").strip().rstrip("/") in {
        item.rstrip("/") for item in MOCK_HOSPITAL_MCP_URLS
    }


def mock_hospital_mcp_result(tool_name: str, payload: object) -> dict:
    payload_text = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
    normalized = str(tool_name or "").strip().lower()
    if normalized == "check_insurance_coverage":
        return {
            "rule_code": "INS-OP-2026-01",
            "summary": "门诊复诊与检查预约可按本院医保规则结算，跨院初诊与特殊检查需先核验转诊或备案信息。",
            "coverage_scope": [
                "门诊复诊预约支持医保统筹结算",
                "影像检查与常规检验按目录内项目执行",
                "异地医保需先完成备案后再走统筹报销",
            ],
            "required_materials": ["医保电子凭证或社保卡", "身份证", "必要时补充转诊单或异地备案凭证"],
            "manual_review": "若涉及门慢、住院预授权、异地未备案或商业保险混合支付，请转人工医保窗口复核。",
            "input_snapshot": payload_text[:240],
        }
    if normalized == "query_clinical_pathway":
        return {
            "pathway_code": "CP-INT-HTN-2026",
            "triage_advice": "先按主诉与危险信号分层。出现持续胸痛、呼吸困难、意识改变、血氧下降等情况，建议优先急诊。",
            "recommended_departments": ["全科门诊", "心内科", "呼吸内科", "急诊医学科"],
            "decision_points": [
                "先识别红旗症状与生命体征异常",
                "无急症征象时再结合既往病史、用药史和近期检查结果给出科室建议",
                "对诊断结论只提供就医建议，不替代医生确诊",
            ],
            "input_snapshot": payload_text[:240],
        }
    if normalized == "evaluate_vaccine_eligibility":
        return {
            "rule_code": "VAC-IMM-2026-03",
            "eligibility": "默认建议先完成接种禁忌核验：近期发热、严重过敏史、急性疾病发作期需由接种门诊医生评估。",
            "contraindications": [
                "发热或急性感染期暂缓接种",
                "既往对疫苗成分严重过敏者不建议直接接种",
                "特殊基础疾病、妊娠或免疫抑制状态需专科评估",
            ],
            "required_materials": ["身份证件", "接种本/电子接种档案", "儿童监护人信息（如适用）"],
            "input_snapshot": payload_text[:240],
        }
    if normalized == "query_drug_catalog":
        return {
            "catalog_version": "DRUG-2026-Q2",
            "summary": "已按本院药事目录返回用药提醒与目录状态，具体处方仍以临床医生审核为准。",
            "highlights": [
                "目录内常用慢病药可走门诊长期处方流程",
                "抗菌药和特殊管理药需按权限与处方级别审核",
                "肝肾功能异常、儿童或高龄患者需再次核对剂量",
            ],
            "input_snapshot": payload_text[:240],
        }
    return {
        "summary": "已收到医院 MCP 模拟请求，但当前工具未配置专属规则。",
        "tool": tool_name,
        "input_snapshot": payload_text[:240],
    }
