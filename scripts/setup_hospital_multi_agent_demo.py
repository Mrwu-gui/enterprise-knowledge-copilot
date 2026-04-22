from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.database import (
    create_tenant,
    get_conn,
    init_db,
    save_agent,
    save_tenant_phone_account,
    save_user_agent_bindings,
    update_tenant,
)
from backend.knowledge_assets import save_knowledge_structure, save_knowledge_tag_groups, set_knowledge_file_meta
from backend.rag import RAGEngine
from backend.retrieval_config import load_retrieval_config, save_retrieval_config
from backend.tenant_config import (
    ensure_tenant_storage,
    get_tenant_knowledge_dir,
    get_tenant_paths,
    save_tenant_app_config,
    save_tenant_system_prompt,
)
from backend.tool_config import load_tool_config, save_tool_config
from backend.workflow_config import save_workflow_config

TENANT_ID = "huadong_hospital"
TENANT_NAME = "华东协同医院"
ADMIN_USERNAME = "tenant_huadong_hospital"
ADMIN_PASSWORD = "Hospital2026!"
DEMO_PHONE = "13800001234"
DEMO_PHONE_PASSWORD = "HospitalChat2026!"
DEMO_PHONE_NAME = "华东协同医院演示账号"
MOCK_MCP_URL = "http://127.0.0.1:8000/api/mock/hospital-mcp"


AGENT_SPECS = [
    {
        "key": "report_interpreter",
        "name": "报告解读助手",
        "department": "医学检验与影像中心",
        "library_name": "报告解读知识库",
        "library_desc": "面向检验单、影像结论和复查建议的解释型知识库。",
        "tags": {"报告类型": ["血常规", "生化", "CT", "MRI"], "适用场景": ["门诊复查", "住院随访", "体检报告"]},
        "recommended": ["这份血常规里白细胞偏高是什么意思？", "CT 报告里的磨玻璃结节怎么理解？", "肝功能轻度异常需要多久复查？"],
        "welcome": "你好，我是报告解读助手。你可以输入检验指标、影像结论或复查问题，我会先按医院知识口径做解释。",
        "description": "负责检验单、影像检查和复查建议的患者友好型解释，不替代临床诊断。",
        "input_placeholder": "输入检验指标、报告结论或你想了解的复查建议...",
        "prompt": "你是华东协同医院的报告解读助手。先解释检查结果含义，再说明常见原因、复查建议和何时需要尽快复诊。不得替代医生诊断，不得编造治疗方案。",
        "service_scope": ["血液、尿液、生化类检验解释", "影像报告常见术语解释", "复查频率与复诊提醒"],
        "boundaries": ["不做最终诊断", "出现急危重症信号时提示尽快线下就医", "不替代医生看片结论"],
        "seasonal_focus": "本月体检高峰期，重点增加体检异常指标与复查时点说明。",
        "hotfix_notice": "体检中心本周六加开上午号源；肺结节复查建议统一按影像门诊最新口径执行。",
    },
    {
        "key": "diagnosis_assistant",
        "name": "辅助诊断助手",
        "department": "全科与专科分诊中心",
        "library_name": "辅助诊断知识库",
        "library_desc": "面向症状分层、就诊科室建议和临床路径提醒的分诊知识库。",
        "tags": {"重点科室": ["全科", "心内科", "呼吸内科", "急诊"], "场景": ["首诊分流", "红旗症状识别", "慢病复诊"]},
        "recommended": ["胸闷心慌伴头晕应该挂什么科？", "反复咳嗽三周需要先看全科还是呼吸科？", "高血压老人突然头痛需要急诊吗？"],
        "welcome": "你好，我是辅助诊断助手。你可以描述主诉、症状持续时间和既往病史，我会给出就诊分层建议。",
        "description": "负责主诉分诊、危险信号识别和推荐科室建议，结合临床路径和知识库输出。",
        "input_placeholder": "输入症状、持续时间、既往病史或检查结果片段...",
        "prompt": "你是华东协同医院的辅助诊断助手。任务是做症状分层和就医建议，而不是替代医生确诊。结合知识库和临床路径规则，输出风险等级、建议科室和就医时效。",
        "service_scope": ["主诉归类与风险分层", "推荐首诊科室", "红旗症状提醒"],
        "boundaries": ["不输出明确疾病诊断", "涉及急危重症时优先建议急诊", "药物与治疗方案仅提示咨询医生"],
        "seasonal_focus": "呼吸道感染与心脑血管高峰时段，重点强化发热、胸痛、呼吸困难的急诊识别。",
        "hotfix_notice": "夜间急诊分诊台已更新胸痛绿色通道标准；卒中可疑病例统一先走急诊卒中筛查。",
        "mcp": {"server_id": "clinical-pathway-center", "tool_name": "query_clinical_pathway"},
    },
    {
        "key": "appointment_assistant",
        "name": "智能预约助手",
        "department": "门诊预约与医保服务中心",
        "library_name": "智能预约知识库",
        "library_desc": "面向门诊、检查、复诊与医保预约规则的导诊知识库。",
        "tags": {"预约类型": ["初诊", "复诊", "检查预约", "跨科转诊"], "渠道": ["公众号", "自助机", "人工窗口"]},
        "recommended": ["第一次看内分泌门诊怎么预约？", "已经做完 CT 想约复诊，医保能直接挂号吗？", "异地医保来院复诊需要准备什么？"],
        "welcome": "你好，我是智能预约助手。你可以咨询挂号、复诊、检查预约和医保资料准备。",
        "description": "负责门诊挂号、复诊预约、检查排期和医保准备材料说明。",
        "input_placeholder": "输入科室、检查项目、医保问题或预约时间需求...",
        "prompt": "你是华东协同医院的智能预约助手。请结合院内预约规则和医保校验结果，输出预约路径、所需材料和注意事项。",
        "service_scope": ["门诊/检查预约说明", "复诊与跨科转诊流程", "医保挂号材料提醒"],
        "boundaries": ["不承诺具体号源余量", "医保结果以窗口最终审核为准", "涉及住院预授权时转人工"],
        "seasonal_focus": "春季体检与复诊号源紧张，需优先提醒患者提前预约检查和复诊。",
        "hotfix_notice": "本周五起核磁共振检查需提前 2 个工作日预约；异地医保患者新增电子备案核验。",
        "mcp": {"server_id": "insurance-rule-center", "tool_name": "check_insurance_coverage"},
    },
    {
        "key": "infection_control",
        "name": "传染病防控助手",
        "department": "感染管理科",
        "library_name": "传染病防控知识库",
        "library_desc": "面向院感上报、隔离要求和发热病例处置的防控知识库。",
        "tags": {"防控场景": ["发热门诊", "院感上报", "隔离观察"], "优先级": ["普通", "重点监测", "紧急上报"]},
        "recommended": ["发热伴皮疹患者入院时先走什么流程？", "疑似流感聚集病例需要怎么上报？", "病区出现腹泻聚集情况先做什么？"],
        "welcome": "你好，我是传染病防控助手。你可以咨询发热病例处置、院感上报和隔离要求。",
        "description": "负责发热门诊分流、院感上报、隔离观察和重点监测提醒。",
        "input_placeholder": "输入病例症状、病区场景或上报问题...",
        "prompt": "你是华东协同医院的传染病防控助手。优先回答隔离、上报、转运和个人防护要求，必要时强调立即联系感染管理科。",
        "service_scope": ["发热/腹泻/皮疹病例处置", "院感监测与报告", "隔离级别说明"],
        "boundaries": ["不替代感染管理科最终判定", "聚集性事件必须提醒立即上报", "涉及儿童/重症/孕产妇需额外提醒"],
        "seasonal_focus": "重点关注流感、诺如和手足口病高发季节的分诊与病区防控。",
        "hotfix_notice": "感染管理科本周更新发热门诊转运路线，发热伴呼吸困难患者统一走急诊隔离通道。",
    },
    {
        "key": "vaccine_assistant",
        "name": "疫苗接种助手",
        "department": "预防接种门诊",
        "library_name": "疫苗接种知识库",
        "library_desc": "面向儿童、成人和重点人群接种前咨询的接种知识库。",
        "tags": {"接种对象": ["儿童", "成人", "老年人", "慢病患者"], "疫苗类型": ["流感", "肺炎", "乙肝", "HPV"]},
        "recommended": ["孩子发烧刚好还能打疫苗吗？", "老年人打流感和肺炎疫苗要间隔多久？", "HPV 接种前要准备什么？"],
        "welcome": "你好，我是疫苗接种助手。你可以咨询接种前准备、常见禁忌和接种后观察事项。",
        "description": "负责接种前咨询、禁忌提醒、资料准备和留观说明。",
        "input_placeholder": "输入年龄、既往病史、近期发热情况或想咨询的疫苗...",
        "prompt": "你是华东协同医院的疫苗接种助手。请结合接种门诊规则和接种适宜性结果，说明能否建议接种、需要准备什么以及何时转人工评估。",
        "service_scope": ["接种前准备说明", "常见禁忌与暂缓情况", "接种后留观提醒"],
        "boundaries": ["严重过敏史和特殊基础病需医生评估", "不替代接种医生面诊", "不保证当日具体库存"],
        "seasonal_focus": "秋冬重点提醒流感、肺炎疫苗接种窗口与留观要求。",
        "hotfix_notice": "预防接种门诊本周增开周六下午场；儿童首针接种需携带监护人身份证件。",
        "mcp": {"server_id": "vaccine-rule-center", "tool_name": "evaluate_vaccine_eligibility"},
    },
    {
        "key": "elderly_care",
        "name": "老年健康助手",
        "department": "老年医学科",
        "library_name": "老年健康知识库",
        "library_desc": "面向老年慢病管理、跌倒风险和复诊提醒的慢病知识库。",
        "tags": {"人群": ["高龄老人", "慢病老人", "术后老人"], "主题": ["高血压", "糖尿病", "跌倒预防", "营养"]},
        "recommended": ["老人血压控制不稳应该多久复诊？", "最近总头晕走路不稳要先看什么？", "老年糖尿病患者饮食上要注意什么？"],
        "welcome": "你好，我是老年健康助手。你可以咨询慢病复诊、跌倒预防和日常健康管理。",
        "description": "负责老年慢病管理提醒、复诊时点、生活方式和跌倒风险提示。",
        "input_placeholder": "输入老人年龄、慢病情况、症状变化或复诊疑问...",
        "prompt": "你是华东协同医院的老年健康助手。请优先回答慢病随访、跌倒风险、营养和复诊提醒，必要时建议尽快线下就诊。",
        "service_scope": ["老年慢病复诊提醒", "跌倒和营养风险提示", "家庭照护建议"],
        "boundaries": ["不替代医生调整药物", "出现急性意识改变/胸痛/跌倒外伤时先建议急诊", "居家监测数据异常要提醒线下复核"],
        "seasonal_focus": "冬春季重点提醒心脑血管事件、呼吸道感染和跌倒风险。",
        "hotfix_notice": "老年医学门诊近期增加周三下午综合评估号源；75 岁以上首次就诊建议家属陪同。",
    },
    {
        "key": "oral_health",
        "name": "口腔健康助手",
        "department": "口腔科",
        "library_name": "口腔健康知识库",
        "library_desc": "面向牙痛、洁牙、种植修复和术后注意事项的口腔知识库。",
        "tags": {"口腔场景": ["牙痛", "洁牙", "拔牙", "种植"], "流程": ["初诊", "术后", "复查"]},
        "recommended": ["拔智齿后一直肿多久需要复诊？", "洗牙前要不要停药？", "牙龈出血应该挂哪个门诊？"],
        "welcome": "你好，我是口腔健康助手。你可以咨询牙痛分诊、洁牙准备和口腔术后护理。",
        "description": "负责口腔常见症状分诊、术后护理和复诊提醒。",
        "input_placeholder": "输入牙痛、牙龈问题、术后情况或就诊疑问...",
        "prompt": "你是华东协同医院的口腔健康助手。请根据口腔知识库给出分诊建议、术后注意事项和复诊提醒。",
        "service_scope": ["常见牙痛与牙龈问题分诊", "口腔术后护理", "口腔门诊就诊准备"],
        "boundaries": ["急性肿胀伴发热需提醒尽快线下就诊", "不远程判断是否必须拔牙", "用药与止痛方案以医生处方为准"],
        "seasonal_focus": "暑期儿童口腔检查增多，重点提醒乳牙龋齿筛查与复诊。",
        "hotfix_notice": "口腔种植门诊本周五停诊半天；洁牙预约需提前在线签署知情同意。",
    },
    {
        "key": "ophthalmology",
        "name": "眼科健康助手",
        "department": "眼科",
        "library_name": "眼科健康知识库",
        "library_desc": "面向视力异常、红眼、干眼与术后复查的眼科知识库。",
        "tags": {"眼科场景": ["视力下降", "红眼", "干眼", "术后复查"], "检查": ["验光", "眼压", "OCT", "眼底照相"]},
        "recommended": ["突然眼前发黑要挂急诊吗？", "白内障术后多久复查一次？", "孩子近视加深需要做什么检查？"],
        "welcome": "你好，我是眼科健康助手。你可以咨询视力异常、红眼、干眼和术后复查问题。",
        "description": "负责眼科常见症状分诊、检查准备和术后复查提醒。",
        "input_placeholder": "输入眼部症状、术后天数、检查问题或复查需求...",
        "prompt": "你是华东协同医院的眼科健康助手。请先识别急症信号，再给出就诊科室、检查准备和术后复查建议。",
        "service_scope": ["眼科急症识别", "常规检查准备", "术后复查提醒"],
        "boundaries": ["视物遮挡、眼痛剧烈、外伤先建议急诊", "不替代医生判断手术指征", "用药仍以医生处方为准"],
        "seasonal_focus": "开学季重点提醒儿童近视筛查与干眼门诊复查。",
        "hotfix_notice": "本周六眼底照相检查设备维护，需改约到工作日完成检查。",
    },
    {
        "key": "sleep_health",
        "name": "睡眠健康助手",
        "department": "睡眠医学门诊",
        "library_name": "睡眠健康知识库",
        "library_desc": "面向失眠、睡眠呼吸暂停和睡眠监测准备的睡眠医学知识库。",
        "tags": {"睡眠问题": ["失眠", "打鼾", "呼吸暂停", "日间困倦"], "检查": ["睡眠监测", "量表评估", "复诊"]},
        "recommended": ["总是凌晨醒来睡不着应该挂什么科？", "打鼾很重需要做睡眠监测吗？", "做睡眠监测前一晚要注意什么？"],
        "welcome": "你好，我是睡眠健康助手。你可以咨询失眠、鼾症、睡眠监测准备和复诊问题。",
        "description": "负责睡眠问题初筛、检查准备和生活方式提醒。",
        "input_placeholder": "输入失眠表现、打鼾情况、白天困倦或监测问题...",
        "prompt": "你是华东协同医院的睡眠健康助手。请输出睡眠问题初筛建议、可能需要的检查以及生活方式提醒。",
        "service_scope": ["失眠和鼾症初筛", "睡眠监测准备说明", "复诊与生活方式建议"],
        "boundaries": ["严重呼吸暂停、胸痛或精神症状先建议线下评估", "不提供处方药建议", "需强调作息和专科评估"],
        "seasonal_focus": "轮班人群和学生开学季睡眠问题增多，重点强化睡眠卫生建议。",
        "hotfix_notice": "本周睡眠监测床位较紧张，需至少提前 3 天预约并完成问卷。",
    },
    {
        "key": "rehab_training",
        "name": "康复训练助手",
        "department": "康复医学科",
        "library_name": "康复训练知识库",
        "library_desc": "面向术后康复、骨关节训练和居家锻炼提醒的康复知识库。",
        "tags": {"康复主题": ["术后康复", "腰背痛", "膝关节", "卒中后训练"], "阶段": ["初期", "巩固期", "居家期"]},
        "recommended": ["膝关节术后多久可以做屈伸训练？", "腰痛居家训练要注意什么？", "卒中后康复复诊一般多久一次？"],
        "welcome": "你好，我是康复训练助手。你可以咨询术后康复、居家训练和复诊安排。",
        "description": "负责康复训练建议、训练禁忌和复诊提醒。",
        "input_placeholder": "输入手术类型、受伤部位、康复阶段或训练疑问...",
        "prompt": "你是华东协同医院的康复训练助手。请结合康复阶段说明训练目标、禁忌动作和何时需要复诊。",
        "service_scope": ["术后康复阶段提醒", "常见康复动作注意事项", "复诊安排与居家训练建议"],
        "boundaries": ["疼痛明显加重、伤口异常、跌倒后需先建议线下复诊", "不替代康复治疗师面评", "动作强度仅作一般提醒"],
        "seasonal_focus": "骨科术后和运动损伤患者增多，重点提醒膝肩关节康复节奏。",
        "hotfix_notice": "康复医学科本周新增周六上午训练评估门诊，首次来诊请携带出院小结。",
    },
    {
        "key": "tcm_wellness",
        "name": "中医养生助手",
        "department": "中医科",
        "library_name": "中医养生知识库",
        "library_desc": "面向四时调养、体质辨识和中医门诊准备的中医知识库。",
        "tags": {"主题": ["体质调养", "饮食起居", "针灸推拿", "门诊准备"], "季节": ["春", "夏", "秋", "冬"]},
        "recommended": ["春天容易上火怎么调养？", "总觉得乏力、手脚凉适合看中医吗？", "第一次去中医门诊要准备什么？"],
        "welcome": "你好，我是中医养生助手。你可以咨询体质调养、四时养生和中医门诊准备。",
        "description": "负责体质调养、饮食起居和中医门诊就诊准备说明。",
        "input_placeholder": "输入体质困扰、季节症状、饮食作息问题或中医门诊疑问...",
        "prompt": "你是华东协同医院的中医养生助手。请用谨慎、通俗的方式说明养生建议和就诊准备，不夸大疗效，不替代医生辨证。",
        "service_scope": ["四时调养建议", "饮食起居提醒", "中医门诊准备"],
        "boundaries": ["不替代中医师辨证处方", "严重症状和长期病情需线下就诊", "中成药用法不做个体化推荐"],
        "seasonal_focus": "春季重点围绕情志调养、睡眠和饮食起居做提醒。",
        "hotfix_notice": "中医科本周新增周四晚间门诊；针灸首诊需提前完成过敏史问卷。",
    },
    {
        "key": "insurance_rules",
        "name": "医保规则助手",
        "department": "医保办",
        "library_name": "医保规则知识库",
        "library_desc": "面向医保材料、备案、门诊结算与人工复核口径的医保知识库。",
        "tags": {"医保场景": ["门诊结算", "异地备案", "转诊", "人工复核"], "对象": ["职工医保", "居民医保", "异地医保"]},
        "recommended": ["异地医保来看门诊需要先做什么？", "门慢病能不能直接在医院窗口备案？", "哪些情况需要去医保窗口人工审核？"],
        "welcome": "你好，我是医保规则助手。你可以咨询门诊医保结算、异地备案和人工复核口径。",
        "description": "负责医保材料准备、备案规则、门诊结算和人工复核提醒。",
        "input_placeholder": "输入医保类型、结算问题、异地备案或材料疑问...",
        "prompt": "你是华东协同医院的医保规则助手。请结合本院医保知识库和医保规则校验结果，输出能否办理、需准备什么以及是否转人工窗口。",
        "service_scope": ["门诊医保规则说明", "异地备案和转诊材料", "窗口人工复核提醒"],
        "boundaries": ["不承诺最终报销金额", "政策冲突时以医保办窗口为准", "复杂结算场景需转人工"],
        "seasonal_focus": "年中门慢病和异地就医咨询增多，重点提醒备案和人工复核材料。",
        "hotfix_notice": "医保办本周更新异地就医电子备案核验口径；住院预授权仍需线下人工办理。",
        "mcp": {"server_id": "insurance-rule-center", "tool_name": "check_insurance_coverage"},
    },
]


def slug_to_id(prefix: str, key: str) -> str:
    return f"{prefix}_{key}"


def make_doc_content(spec: dict, tier: str) -> str:
    title_map = {
        "permanent": "核心服务规范",
        "seasonal": "当前重点场景",
        "hotfix": "本周公告",
    }
    heading = title_map[tier]
    if tier == "permanent":
        return "\n".join(
            [
                f"# {spec['name']}{heading}",
                "",
                f"来源可信度：A",
                "是否需人工复核：否",
                "",
                "## 适用范围",
                f"- 负责部门：{spec['department']}",
                *[f"- {item}" for item in spec["service_scope"]],
                "",
                "## 回答边界",
                *[f"- {item}" for item in spec["boundaries"]],
                "",
                "## 标准答复要求",
                f"- 统一以“{spec['department']}”最新服务口径为准。",
                "- 先解释当前问题归属场景，再给出建议步骤。",
                "- 对需要人工复核的内容要明确说出转人工原因。",
                "",
            ]
        )
    if tier == "seasonal":
        return "\n".join(
            [
                f"# {spec['name']}{heading}",
                "",
                "来源可信度：B",
                "是否需人工复核：否",
                "",
                "## 当前重点",
                spec["seasonal_focus"],
                "",
                "## 推荐问法示例",
                *[f"- {item}" for item in spec["recommended"]],
                "",
                "## 输出提醒",
                "- 优先回答本月高频业务问题。",
                "- 若用户信息不足，先补问关键字段再给建议。",
                "",
            ]
        )
    return "\n".join(
        [
            f"# {spec['name']}{heading}",
            "",
            "来源可信度：A",
            "是否需人工复核：是",
            "",
            "## 当前公告",
            spec["hotfix_notice"],
            "",
            "## 当班提醒",
            "- 涉及停诊、改约、人工复核或紧急就医建议时，要把公告信息放到回答前半段。",
            "- 如公告与基础规则冲突，以本周公告为准。",
            "",
        ]
    )


def build_tenant_system_prompt() -> str:
    return (
        "你是华东协同医院面向患者咨询场景的多智能体平台底座。\n"
        "你的回答必须遵守以下医院级规则：\n"
        "1. 优先依据当前智能体所属知识库、工作流节点结果和规则系统结果作答，严禁脱离依据自由发挥。\n"
        "2. 不得进行医生诊断、处方开具、手术指征判断、报销金额承诺、库存承诺和号源承诺。\n"
        "3. 遇到急危重症信号、儿童/孕产妇/高龄特殊风险、院感聚集、复杂医保结算、药物调整等情况，必须明确提示转线下医生、护士站、急诊或人工窗口。\n"
        "4. 如果用户提供的信息不足以判断，不要直接给结论，先补问关键字段。\n"
        "5. 输出要口语化、可执行、面向患者理解，避免空泛术语堆砌。\n"
        "6. 如知识库或规则结果之间有冲突，以本周公告和规则系统返回结果优先，同时提醒“请以窗口/门诊现场最终执行口径为准”。\n\n"
        "【知识库内容开始】\n{knowledge_context}\n【知识库内容结束】\n"
    )


def _agent_specific_blueprint(spec: dict) -> dict:
    mapping = {
        "report_interpreter": {
            "clarify": ["检查项目名称", "异常指标或报告结论", "是否有症状/既往病史", "检查时间"],
            "structure": ["检查结果怎么理解", "常见原因或背景解释", "建议多久复查/挂什么门诊", "哪些信号需要尽快线下复诊"],
            "style": "解释型、安抚型、去术语化，适合患者阅读",
        },
        "diagnosis_assistant": {
            "clarify": ["主要症状", "持续时间", "年龄/特殊人群", "是否有胸痛、呼吸困难、意识改变等红旗症状"],
            "structure": ["风险分层结论", "建议先去哪个科/是否急诊", "到院前要准备什么", "哪些情况立刻就医"],
            "style": "分诊型、风险优先、不要像确诊报告",
        },
        "appointment_assistant": {
            "clarify": ["想看的科室或检查项目", "初诊/复诊", "期望时间", "医保类型/是否异地医保"],
            "structure": ["是否可这样预约", "推荐预约路径", "需要准备的证件/材料", "哪些情况需转人工窗口"],
            "style": "流程型、办事指南型，步骤要清楚",
        },
        "infection_control": {
            "clarify": ["症状表现", "发生地点/病区", "是否聚集", "是否已有发热、腹泻、皮疹、呼吸困难等重点风险"],
            "structure": ["当前场景判定", "先做什么隔离/防护", "是否需要上报及上报对象", "哪些情况立即升级处理"],
            "style": "防控型、动作导向、风险压前",
        },
        "vaccine_assistant": {
            "clarify": ["接种对象年龄", "近期是否发热/感染", "既往严重过敏史", "想接种的疫苗名称"],
            "structure": ["当前是否建议直接接种", "需要暂缓还是可预约", "接种前准备事项", "什么情况要医生面评"],
            "style": "门诊咨询型、审慎型",
        },
        "elderly_care": {
            "clarify": ["老人年龄", "基础疾病", "最近症状变化", "是否跌倒/胸痛/意识改变"],
            "structure": ["当前最需要关注的问题", "建议复诊时点/科室", "居家管理重点", "哪些情况应尽快就医"],
            "style": "慢病管理型、家属友好型",
        },
        "oral_health": {
            "clarify": ["症状部位", "疼痛/肿胀持续时间", "是否发热", "是否术后/是否正在服药"],
            "structure": ["建议先挂什么门诊", "近期在家注意事项", "到院前准备", "哪些情况别等直接复诊"],
            "style": "分诊+术后宣教型",
        },
        "ophthalmology": {
            "clarify": ["症状发生时间", "单眼还是双眼", "是否疼痛/外伤/遮挡感", "是否术后"],
            "structure": ["是否存在急症信号", "推荐门诊或急诊路径", "检查前准备", "复查提醒"],
            "style": "急症筛查优先、简洁明确",
        },
        "sleep_health": {
            "clarify": ["主要睡眠问题", "持续时长", "是否打鼾/憋醒", "是否影响白天工作学习"],
            "structure": ["初步判断属于哪类睡眠困扰", "是否建议监测/量表", "生活方式建议", "哪些情况需要尽快专科评估"],
            "style": "睡眠门诊咨询型、生活方式友好型",
        },
        "rehab_training": {
            "clarify": ["手术/损伤类型", "康复阶段", "当前疼痛和活动度", "是否有伤口异常/跌倒"],
            "structure": ["目前阶段目标", "可做与禁忌动作", "居家训练注意点", "何时回院复评"],
            "style": "康复宣教型、动作边界清楚",
        },
        "tcm_wellness": {
            "clarify": ["主要困扰", "持续时间", "季节/作息饮食情况", "是否已有明确疾病诊断"],
            "structure": ["适合怎样调养", "饮食起居建议", "是否建议看中医门诊", "哪些情况不要只靠养生建议"],
            "style": "温和、审慎、避免神化疗效",
        },
        "insurance_rules": {
            "clarify": ["医保类型", "门诊/检查/住院哪类场景", "是否异地就医", "是否涉及转诊/备案/门慢病"],
            "structure": ["这件事能否这样办", "需要哪些材料", "办理顺序", "哪些情况必须人工窗口复核"],
            "style": "办事规则型、口径明确、不要空话",
        },
    }
    return mapping.get(spec["key"], {
        "clarify": ["用户当前诉求", "相关症状或业务场景", "时间信息", "是否已有院内检查或就诊记录"],
        "structure": ["结论", "建议步骤", "线下处理提示", "风险提醒"],
        "style": "专业、谨慎、面向患者",
    })


def build_agent_prompt(spec: dict) -> str:
    blueprint = _agent_specific_blueprint(spec)
    clarify_block = "\n".join([f"- {item}" for item in blueprint["clarify"]])
    structure_block = "\n".join([f"- {item}" for item in blueprint["structure"]])
    service_scope = "\n".join([f"- {item}" for item in spec["service_scope"]])
    boundaries = "\n".join([f"- {item}" for item in spec["boundaries"]])
    examples = "\n".join([f"- {item}" for item in spec["recommended"]])
    return (
        f"你是华东协同医院{spec['department']}的“{spec['name']}”。\n"
        f"你的职责：{spec['description']}\n"
        f"你的回答风格：{blueprint['style']}。\n\n"
        "【你负责处理的范围】\n"
        f"{service_scope}\n\n"
        "【你绝对不能做的事】\n"
        f"{boundaries}\n\n"
        "【用户信息不足时，优先补问这些关键字段】\n"
        f"{clarify_block}\n\n"
        "【回答结构要求】\n"
        "每次都尽量按下面顺序输出，除非用户只要一个简答：\n"
        f"{structure_block}\n\n"
        "【表达规则】\n"
        "1. 先说结论，再说原因或步骤，不要一上来长篇铺垫。\n"
        "2. 如果能做，请直接告诉用户“下一步怎么做、去哪里做、带什么材料”。\n"
        "3. 如果不能直接判断，要明确说“还缺什么信息”，再提出最多 2 到 4 个关键追问。\n"
        "4. 涉及急诊、复诊、人工窗口、接种医生面评、感染上报、医保复核时，要用明确动作词，不要模糊。\n"
        "5. 不得编造号源、库存、报销比例、检查结果、医生意见或治疗方案。\n"
        "6. 如知识库没有明确依据，要坦诚说明，并引导到对应门诊/窗口，不要硬答。\n\n"
        "【遇到这些情况必须升级提醒】\n"
        "- 用户出现急危重症信号时，优先建议急诊或立即线下就医。\n"
        "- 需要医生诊断、用药调整、手术判断、最终报销审核时，必须提示以线下医生/医保窗口为准。\n"
        "- 如果本周公告或规则系统有新口径，优先采用新口径。\n\n"
        "【典型用户问法示例】\n"
        f"{examples}"
    )


def build_workflow_ai_prompt(spec: dict) -> str:
    blueprint = _agent_specific_blueprint(spec)
    structure_block = "\n".join([f"- {item}" for item in blueprint["structure"]])
    clarify_block = "\n".join([f"- {item}" for item in blueprint["clarify"]])
    prompt = (
        f"你现在扮演华东协同医院{spec['department']}的“{spec['name']}”。\n"
        "你必须严格根据用户问题、知识库命中内容"
        + ("以及规则系统返回结果" if spec.get("mcp") else "")
        + "来组织答复。\n\n"
        "【用户问题】\n{{input.text}}\n\n"
        "【知识库内容】\n{{nodes.knowledge_1.result.knowledge_text}}\n"
    )
    if spec.get("mcp"):
        prompt += "\n【规则系统结果】\n{{nodes.mcp_1.result.result}}\n"
    prompt += (
        "\n【输出要求】\n"
        "1. 第一段必须直接给结论，不要先说“根据您提供的信息”。\n"
        "2. 结论后按业务动作拆解步骤，尽量让患者一看就知道下一步怎么办。\n"
        "3. 如果信息不足，不要硬给结论；先说明缺口，再追问这些关键字段中的最必要项：\n"
        f"{clarify_block}\n"
        "4. 回答尽量覆盖以下结构：\n"
        f"{structure_block}\n"
        "5. 涉及急危重症、人工窗口复核、感染上报、接种医生面评、线下复诊时，要单独列出“请尽快处理/请转人工”。\n"
        "6. 不得输出确诊、处方、手术建议、报销承诺、号源承诺或知识库中没有的细节。\n"
        "7. 如果规则系统与知识库口径不同，以规则系统或本周公告优先，并提醒以院内现场最终执行为准。\n"
        "8. 输出语言要像医院真正面向患者的服务答复，专业但不端着，不要像 AI 模板文。\n"
    )
    return prompt


def build_workflow(spec: dict, library_id: str) -> dict:
    workflow_id = slug_to_id("wf", spec["key"])
    start_id = "start_1"
    knowledge_id = "knowledge_1"
    end_id = "end_1"
    nodes = [
        {
            "id": start_id,
            "type": "start",
            "x": 80,
            "y": 180,
            "data": {"label": "开始节点", "description": "接收用户输入", "triggerType": "API 调用"},
        },
        {
            "id": knowledge_id,
            "type": "knowledge",
            "x": 360,
            "y": 180,
            "data": {
                "label": f"{spec['name']}检索",
                "description": f"检索{spec['library_name']}相关知识",
                "query": "{{input.text}}",
                "knowledgeBase": library_id,
                "topK": 5,
                "threshold": 0.12,
            },
        },
    ]
    connections = [{"id": "c1", "from": start_id, "to": knowledge_id, "label": ""}]

    prompt = build_workflow_ai_prompt(spec)

    previous_id = knowledge_id
    if spec.get("mcp"):
        nodes.append(
            {
                "id": "mcp_1",
                "type": "mcp",
                "x": 650,
                "y": 180,
                "data": {
                    "label": f"{spec['name']}规则核验",
                    "description": "调用医院规则系统辅助判断",
                    "serverId": spec["mcp"]["server_id"],
                    "toolName": spec["mcp"]["tool_name"],
                    "payload": json.dumps({"question": "{{input.text}}", "knowledge": "{{nodes.knowledge_1.result.knowledge_text}}"}, ensure_ascii=False),
                },
            }
        )
        connections.append({"id": "c2", "from": knowledge_id, "to": "mcp_1", "label": ""})
        previous_id = "mcp_1"

    nodes.extend(
        [
            {
                "id": "ai_1",
                "type": "ai",
                "x": 940 if spec.get("mcp") else 680,
                "y": 180,
                "data": {
                    "label": f"生成{spec['name']}答复",
                    "description": f"根据{spec['library_name']}输出业务答复",
                    "prompt": prompt,
                    "model": "__default__",
                    "temperature": 0.2,
                },
            },
            {
                "id": end_id,
                "type": "end",
                "x": 1240 if spec.get("mcp") else 980,
                "y": 180,
                "data": {"label": "结束节点", "description": "返回结果", "endType": "正常结束", "endMessage": "{{last.text}}"},
            },
        ]
    )
    connections.append({"id": "c3", "from": previous_id, "to": "ai_1", "label": ""})
    connections.append({"id": "c4", "from": "ai_1", "to": end_id, "label": ""})

    return {
        "workflow_id": workflow_id,
        "name": f"{spec['name']}流程",
        "description": f"{spec['name']}专用工作流，按独立知识库和业务规则生成答复。",
        "enabled": True,
        "sort_order": 100,
        "version": "V1.0",
        "status": "published",
        "updated_at": "2026-04-10 12:00:00",
        "nodes": nodes,
        "connections": connections,
        "app_overrides": {
            "chat_title": spec["name"],
            "chat_tagline": spec["description"],
            "welcome_message": spec["welcome"],
            "agent_description": spec["description"],
            "recommended_questions": spec["recommended"],
            "input_placeholder": spec["input_placeholder"],
            "send_button_text": "开始咨询",
        },
        "system_prompt": (
            f"你是华东协同医院{spec['department']}的“{spec['name']}”。\n"
            "请优先根据知识库与流程节点结果回答，禁止脱离依据编造。\n"
            "如涉及诊断、用药、报销、急危重症、线下处置，务必给出清晰的升级提醒。\n\n"
            "【知识库内容开始】\n{knowledge_context}\n【知识库内容结束】"
        ),
    }


def recreate_tenant_root() -> None:
    paths = get_tenant_paths(TENANT_ID)
    root = Path(paths["root"])
    knowledge_dir = Path(get_tenant_knowledge_dir(TENANT_ID))
    if root.exists():
        shutil.rmtree(root)
    if knowledge_dir.exists():
        shutil.rmtree(knowledge_dir)


def ensure_tenant_row() -> None:
    conn = get_conn()
    row = conn.execute("SELECT tenant_id FROM tenants WHERE tenant_id = ?", (TENANT_ID,)).fetchone()
    conn.close()
    if row:
        update_tenant(TENANT_ID, TENANT_NAME, ADMIN_USERNAME, True, ADMIN_PASSWORD)
    else:
        create_tenant(TENANT_ID, TENANT_NAME, ADMIN_USERNAME, ADMIN_PASSWORD)


def clear_tenant_runtime_rows() -> None:
    conn = get_conn()
    conn.execute("DELETE FROM agent_user_bindings WHERE tenant_id = ?", (TENANT_ID,))
    conn.execute("DELETE FROM agents WHERE tenant_id = ?", (TENANT_ID,))
    conn.execute("DELETE FROM phone_accounts WHERE tenant_id = ?", (TENANT_ID,))
    conn.commit()
    conn.close()


def setup_branding() -> None:
    save_tenant_app_config(
        TENANT_ID,
        TENANT_NAME,
        {
            "app_name": TENANT_NAME,
            "app_subtitle": "多专科智能体协同服务平台",
            "chat_title": "华东协同医院智能体广场",
            "chat_tagline": "为门诊导诊、检查解读、慢病随访、疫苗接种与医保咨询提供多 Agent 服务",
            "welcome_message": "你好，这里是华东协同医院智能体广场。请选择适合你的专科助手开始咨询。",
            "agent_description": "医院多智能体服务平台，支持每个专科助手绑定独立知识库、工作流、链接和业务规则。",
            "recommended_questions": [
                "我应该先用哪个助手咨询体检报告？",
                "想预约门诊并了解医保，需要找哪个助手？",
                "老人慢病复诊和用药提醒应该用哪个助手？",
            ],
            "login_hint": "医院租户演示账号登录 · 支持多个智能体独立入口与统一切换",
            "input_placeholder": "输入问题，或先切换到适合的医院助手...",
            "send_button_text": "发送咨询",
            "theme": {
                "bg": "#f4f8ff",
                "surface": "#ffffff",
                "surface_strong": "#ffffff",
                "line": "#d9e6fb",
                "text": "#183153",
                "muted": "#6981a3",
                "accent": "#2563eb",
                "accent_strong": "#194ab7",
                "accent_soft": "rgba(37, 99, 235, 0.12)",
                "danger": "#d55f61",
                "primary": "#2563eb",
                "primary_deep": "#194ab7",
                "primary_soft": "rgba(37, 99, 235, 0.12)",
            },
        },
    )
    save_tenant_system_prompt(
        TENANT_ID,
        TENANT_NAME,
        build_tenant_system_prompt(),
    )


def setup_retrieval_and_tools() -> None:
    retrieval = load_retrieval_config(tenant_id=TENANT_ID, tenant_name=TENANT_NAME)
    retrieval["backend"] = "bm25"
    retrieval.setdefault("qdrant", {})["enabled"] = False
    save_retrieval_config(retrieval, tenant_id=TENANT_ID, tenant_name=TENANT_NAME)

    tool_cfg = load_tool_config(tenant_id=TENANT_ID, tenant_name=TENANT_NAME)
    tool_cfg.setdefault("mcp", {})
    tool_cfg["mcp"]["enabled"] = True
    tool_cfg["mcp"]["request_timeout_seconds"] = 15
    tool_cfg["mcp"]["servers"] = [
        {"server_id": "insurance-rule-center", "label": "医保规则中心", "bridge_url": MOCK_MCP_URL, "auth_token": "", "enabled": True},
        {"server_id": "clinical-pathway-center", "label": "临床路径中心", "bridge_url": MOCK_MCP_URL, "auth_token": "", "enabled": True},
        {"server_id": "vaccine-rule-center", "label": "接种规则中心", "bridge_url": MOCK_MCP_URL, "auth_token": "", "enabled": True},
        {"server_id": "drug-catalog-center", "label": "药品目录中心", "bridge_url": MOCK_MCP_URL, "auth_token": "", "enabled": True},
    ]
    save_tool_config(tool_cfg, tenant_id=TENANT_ID, tenant_name=TENANT_NAME)


def setup_knowledge() -> tuple[list[dict], list[dict]]:
    libraries = []
    categories = []
    for spec in AGENT_SPECS:
        library_id = slug_to_id("kb", spec["key"])
        libraries.append({"library_id": library_id, "name": spec["library_name"], "description": spec["library_desc"]})
        for tier, category_name in [("permanent", "基础规则"), ("seasonal", "重点场景"), ("hotfix", "当前公告")]:
            categories.append(
                {
                    "category_id": slug_to_id("cat", f"{spec['key']}_{tier}"),
                    "library_id": library_id,
                    "name": category_name,
                }
            )
    save_knowledge_structure(TENANT_ID, libraries=libraries, categories=categories, tenant_name=TENANT_NAME)

    tag_groups = []
    knowledge_dir = Path(get_tenant_knowledge_dir(TENANT_ID))
    for spec in AGENT_SPECS:
        library_id = slug_to_id("kb", spec["key"])
        for group_name, values in spec["tags"].items():
            tag_groups.append(
                {
                    "tag_id": slug_to_id("tag", f"{spec['key']}_{group_name}"),
                    "library_id": library_id,
                    "name": group_name,
                    "values": [
                        {
                            "value_id": slug_to_id("tagv", f"{spec['key']}_{group_name}_{index}"),
                            "name": value,
                            "synonyms": [],
                        }
                        for index, value in enumerate(values, start=1)
                    ],
                }
            )
        for tier in ["permanent", "seasonal", "hotfix"]:
            tier_dir = knowledge_dir / tier
            tier_dir.mkdir(parents=True, exist_ok=True)
            file_name = {
                "permanent": "01_核心服务规范.md",
                "seasonal": "02_当前重点场景.md",
                "hotfix": "03_本周公告.md",
            }[tier]
            tenant_file_name = f"{spec['key']}_{file_name}"
            (tier_dir / tenant_file_name).write_text(make_doc_content(spec, tier), encoding="utf-8")
            category_id = slug_to_id("cat", f"{spec['key']}_{tier}")
            file_tags = [next(iter(spec["tags"].values()))[0], list(spec["tags"].values())[-1][0]]
            set_knowledge_file_meta(
                TENANT_ID,
                tier=tier,
                file_name=tenant_file_name,
                tags=file_tags,
                library_id=library_id,
                category_id=category_id,
                tenant_name=TENANT_NAME,
            )
    save_knowledge_tag_groups(TENANT_ID, tag_groups, tenant_name=TENANT_NAME)
    return libraries, categories


def setup_workflows() -> list[dict]:
    workflows = []
    for index, spec in enumerate(AGENT_SPECS, start=1):
        workflow = build_workflow(spec, slug_to_id("kb", spec["key"]))
        workflow["sort_order"] = index * 100
        workflows.append(workflow)
    save_workflow_config(
        {"default_workflow_id": workflows[0]["workflow_id"], "items": workflows},
        tenant_id=TENANT_ID,
        tenant_name=TENANT_NAME,
    )
    return workflows


def setup_agents() -> list[dict]:
    agents = []
    for index, spec in enumerate(AGENT_SPECS, start=1):
        library_id = slug_to_id("kb", spec["key"])
        workflow_id = slug_to_id("wf", spec["key"])
        agent = save_agent(
            tenant_id=TENANT_ID,
            agent_id=slug_to_id("agent", spec["key"]),
            name=spec["name"],
            description=spec["description"],
            status="published",
            enabled=True,
            welcome_message=spec["welcome"],
            input_placeholder=spec["input_placeholder"],
            recommended_questions=spec["recommended"],
            prompt_override=build_agent_prompt(spec),
            workflow_id=workflow_id,
            knowledge_scope={"libraries": [library_id], "tags": [], "files": []},
            model_override={},
            tool_scope=[],
            mcp_servers=[spec["mcp"]["server_id"]] if spec.get("mcp") else [],
            streaming=True,
            fallback_enabled=True,
            fallback_message="当前知识库没有足够依据时，请转人工医生、护士站或医保窗口继续确认。",
            show_recommended=True,
            is_default=index == 1,
        )
        agents.append(agent)
    return agents


def setup_demo_account(agent_ids: list[str]) -> None:
    save_tenant_phone_account(
        tenant_id=TENANT_ID,
        phone=DEMO_PHONE,
        display_name=DEMO_PHONE_NAME,
        password=DEMO_PHONE_PASSWORD,
        enabled=True,
    )
    conn = get_conn()
    conn.execute(
        "UPDATE phone_accounts SET must_change_password = 0 WHERE tenant_id = ? AND phone = ?",
        (TENANT_ID, DEMO_PHONE),
    )
    conn.commit()
    conn.close()
    save_user_agent_bindings(tenant_id=TENANT_ID, phone=DEMO_PHONE, agent_ids=agent_ids)


def rebuild_demo_index() -> int:
    app_cfg = save_tenant_app_config(TENANT_ID, TENANT_NAME, {})
    retrieval_cfg = load_retrieval_config(tenant_id=TENANT_ID, tenant_name=TENANT_NAME)
    engine = RAGEngine(
        knowledge_dir=get_tenant_knowledge_dir(TENANT_ID),
        app_config=app_cfg,
        retrieval_config=retrieval_cfg,
        knowledge_namespace=TENANT_ID,
    )
    return engine.build_index()


def write_summary(libraries: list[dict], workflows: list[dict], agents: list[dict], indexed_chunks: int) -> Path:
    summary_path = Path(get_tenant_paths(TENANT_ID)["root"]) / "demo_setup_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "tenant_id": TENANT_ID,
                "tenant_name": TENANT_NAME,
                "admin_username": ADMIN_USERNAME,
                "admin_password": ADMIN_PASSWORD,
                "demo_phone": DEMO_PHONE,
                "demo_phone_password": DEMO_PHONE_PASSWORD,
                "agents": [{"agent_id": item["agent_id"], "name": item["name"], "workflow_id": item["workflow_id"]} for item in agents],
                "knowledge_libraries": libraries,
                "workflow_count": len(workflows),
                "indexed_chunks": indexed_chunks,
                "remaining_gaps": [
                    "正式医保、临床路径、药品目录服务目前接的是本地 mock MCP bridge；生产环境需替换成真实医院接口。",
                    "如需院内 AD/LDAP、科室级 RBAC、操作审计与实名脱敏，还需补企业级权限与合规能力。",
                    "如果要做和截图一致的“智能体广场卡片运营后台”，当前已有多 agent 切换能力，但卡片化运营装修仍可继续增强。",
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary_path


def main() -> None:
    init_db()
    ensure_tenant_row()
    clear_tenant_runtime_rows()
    recreate_tenant_root()
    ensure_tenant_storage(TENANT_ID, TENANT_NAME)
    setup_branding()
    setup_retrieval_and_tools()
    libraries, _ = setup_knowledge()
    workflows = setup_workflows()
    agents = setup_agents()
    setup_demo_account([item["agent_id"] for item in agents])
    indexed_chunks = rebuild_demo_index()
    summary_path = write_summary(libraries, workflows, agents, indexed_chunks)
    print(json.dumps({"ok": True, "tenant_id": TENANT_ID, "agents": len(agents), "workflows": len(workflows), "indexed_chunks": indexed_chunks, "summary": str(summary_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
