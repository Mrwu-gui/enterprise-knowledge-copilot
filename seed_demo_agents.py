from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from backend.database import create_tenant, get_conn, save_tenant_phone_account, update_tenant
from backend.tenant_config import (
    ensure_tenant_storage,
    get_tenant_knowledge_dir,
    save_tenant_app_config,
    save_tenant_system_prompt,
)
from backend.tool_config import load_tool_config, save_tool_config


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "app.db"

ADMIN_PASSWORD = "AgentDemo2026!"
PHONE_PASSWORD = "ChatDemo2026!"


TENANTS = [
    {
        "tenant_id": "repair_dispatch",
        "tenant_name": "速修联维（上海）科技有限公司",
        "admin_username": "repair_admin",
        "phone": "16600010001",
        "display_name": "小维调度官",
        "app_config": {
            "app_name": "速修联维",
            "app_subtitle": "设备维修调度与上门服务中台",
            "chat_title": "小维调度官",
            "chat_tagline": "报修受理、初步诊断、报价复核与工程师派单",
            "welcome_message": "你好，我是小维调度官。你可以描述故障现象、上传设备照片、咨询报价范围或安排上门维修。",
            "agent_description": "面向家电与商用设备报修场景的维修调度 Agent，负责故障分级、报价建议、人工复核与工程师派单建议。",
            "recommended_questions": [
                "空调不制冷并且外机异响，怎么判断故障？",
                "洗衣机 E03 报错上门维修大概多少钱？",
                "浦东新区今天下午能安排哪个工程师上门？",
            ],
            "login_hint": "维修调度后台登录 · 先校验报价规则与工程师排班",
            "input_placeholder": "输入设备故障、区域、时间诉求或上传照片后的描述...",
            "send_button_text": "提交报修",
            "theme": {
                "bg": "#eef6ff",
                "surface": "#ffffff",
                "surface_strong": "#ffffff",
                "line": "#d8e7fb",
                "text": "#17324d",
                "muted": "#5f7894",
                "accent": "#1f8ef1",
                "accent_strong": "#1168b9",
                "accent_soft": "rgba(31, 142, 241, 0.12)",
                "danger": "#d85f4a",
            },
        },
        "prompt": """你是“速修联维（上海）科技有限公司”的维修调度 Agent，名字叫“小维调度官”。

你的职责：
1. 先识别设备类型、故障现象、使用环境和紧急程度。
2. 根据知识库给出初步诊断、处理建议和报价区间。
3. 如果信息不足、涉及拆机高风险、报价不确定或安全风险，请明确标记“需人工审核”。
4. 如用户提供了地址或区域，需结合知识库中的工程师排班信息，给出附近工程师与预约建议。
5. 输出尽量像真实业务受理单，不要闲聊。

回答格式优先按下面结构：
- 故障判断：
- 报价建议：
- 是否需人工审核：
- 工程师匹配：
- 预约建议：
- 后续跟进：

如果知识库没有依据，不要编造工程师、报价或配件库存。

【知识库内容开始】
{knowledge_context}
【知识库内容结束】""",
        "knowledge": {
            "permanent": {
                "01_企业与服务范围.md": """# 速修联维服务台说明

## 企业定位
速修联维（上海）科技有限公司，主营家用空调、洗衣机、冰箱、热水器以及中小型商用设备的上门维修与保养服务。

## 服务区域
- 上海浦东新区
- 上海闵行区
- 上海徐汇区
- 上海静安区

## 受理规则
- 7x12 小时在线受理
- 标准上门时段：09:00-12:00、13:00-16:00、16:00-19:00
- 紧急故障仅限：漏水、跳闸、异味冒烟、设备完全停机且影响营业

## 可回答问题
- 某类设备是否在服务范围
- 某个区域是否支持上门
- 标准预约时段有哪些
""",
                "02_故障诊断与报价手册.md": """# 常见故障诊断与报价手册

## 空调类
### 不制冷
- 常见原因：缺氟、冷凝器脏堵、压缩机保护、风机故障
- 报价区间：
  - 基础检测：80-120 元
  - 清洗保养：160-260 元
  - 补氟：260-480 元
  - 压缩机相关：需人工复核

### 外机异响
- 常见原因：风叶摩擦、固定螺丝松动、轴承磨损
- 报价区间：
  - 紧固处理：120-180 元
  - 风叶更换：220-360 元
  - 电机或轴承：需人工复核

## 洗衣机类
### E03 报错
- 常见原因：排水泵堵塞、排水阀异常、线路接触不良
- 报价区间：
  - 基础检测：70-100 元
  - 排水泵清理：120-180 元
  - 排水泵更换：220-320 元

## 人工审核触发条件
- 用户提供信息不足
- 涉及主板、压缩机、燃气模块
- 用户反馈有冒烟、异味、漏电
- 设备为商用大型机型
""",
            },
            "seasonal": {
                "03_工程师排班与技能表.md": """# 工程师排班与技能表

## 当周可派单工程师
### 陈骁
- 区域：浦东、徐汇
- 擅长：空调、热水器
- 可预约：周一到周六 13:00-19:00

### 赵宁
- 区域：闵行、徐汇
- 擅长：洗衣机、冰箱
- 可预约：周一到周日 09:00-16:00

### 孙立
- 区域：静安、浦东
- 擅长：商用制冷设备、紧急故障排查
- 可预约：周二到周日 16:00-19:00

## 派单原则
- 优先同区域
- 再看设备技能匹配
- 紧急故障优先派给可处理高风险故障的工程师
""",
            },
            "hotfix": {
                "04_当前服务公告.md": """# 当前服务公告

## 本周公告
- 受台风天气影响，浦东临港片区上门时段统一调整为 10:00 之后。
- 涉及燃气热水器主板故障的订单，本周一律人工审核后报价。
- 商用制冰机项目当前仅支持静安和浦东核心商圈预约。
""",
            },
        },
    },
    {
        "tenant_id": "service_desk",
        "tenant_name": "悦程生活服务集团",
        "admin_username": "service_admin",
        "phone": "16600010002",
        "display_name": "小悦客服",
        "app_config": {
            "app_name": "悦程生活服务",
            "app_subtitle": "售后服务、退款与预约处理中心",
            "chat_title": "小悦客服",
            "chat_tagline": "意图识别、订单查询、自助退款与转人工衔接",
            "welcome_message": "你好，我是小悦客服。你可以咨询退款、改约、催单、投诉处理或售后服务规则。",
            "agent_description": "面向生活服务售后场景的客服 Agent，负责意图识别、规则解释、自助处理和人工升级。",
            "recommended_questions": [
                "订单 YC20260405017 现在是什么状态？",
                "我想把明天下午的保洁预约改到周日早上。",
                "课程卡退款规则是怎样的？",
            ],
            "login_hint": "客服中心登录 · 先查看订单规则与人工升级标准",
            "input_placeholder": "输入客户反馈、订单号、退款诉求或预约问题...",
            "send_button_text": "开始受理",
            "theme": {
                "bg": "#fff7f0",
                "surface": "#ffffff",
                "surface_strong": "#ffffff",
                "line": "#f3dcc8",
                "text": "#4a3122",
                "muted": "#8a6a57",
                "accent": "#f28b2c",
                "accent_strong": "#cb6711",
                "accent_soft": "rgba(242, 139, 44, 0.14)",
                "danger": "#d95d5d",
            },
        },
        "prompt": """你是“悦程生活服务集团”的售后客服 Agent，名字叫“小悦客服”。

你的职责：
1. 先识别客户意图：咨询、退款、改约、催单、投诉、人工协助。
2. 根据订单规则和知识库判断能否自助处理。
3. 能处理时，明确给出处理结果和下一步动作。
4. 退款争议、赔付诉求、高情绪投诉、查无订单时，必须转人工。
5. 输出要像客服工单摘要，语气专业、克制、能安抚。

回答格式优先按下面结构：
- 意图识别：
- 查询结果：
- 处理方案：
- 是否转人工：
- 给客户的话术：

不要编造订单状态和退款结果。

【知识库内容开始】
{knowledge_context}
【知识库内容结束】""",
        "knowledge": {
            "permanent": {
                "01_客服服务手册.md": """# 客服服务手册

## 业务范围
悦程生活服务集团提供家庭保洁、到家维修、家庭整理、课程卡预约与会员服务。

## 常见客服意图
- 查询订单状态
- 申请退款
- 修改预约时间
- 反馈服务质量
- 要求人工客服介入

## 客服回复原则
- 先确认客户诉求，再给规则依据
- 能自助处理的直接给结果
- 涉及赔偿争议必须人工接管
""",
                "02_退款与改约规则.md": """# 退款与改约规则

## 退款规则
- 未上门且距离预约开始时间超过 4 小时：支持全额退款
- 距离预约开始 4 小时内取消：收取 20% 服务占用费
- 服务已开始：不支持在线全额退款，需人工复核

## 改约规则
- 每笔订单最多改约 2 次
- 距离预约开始时间 2 小时以上可自助改约
- 高峰档（周末 09:00-12:00）改约需重新确认排班

## 转人工规则
- 客户要求赔付
- 客户情绪激烈投诉
- 系统查不到订单
- 订单状态与客户描述明显冲突
""",
            },
            "seasonal": {
                "03_订单与预约示例库.md": """# 订单与预约示例库

## 示例订单
### YC20260405017
- 类型：深度保洁
- 状态：已付款，待服务
- 预约时间：2026-04-06 14:00-17:00
- 地址：上海浦东新区张杨路
- 支持操作：改约、取消退款

### YC20260401008
- 类型：课程卡预约
- 状态：已核销一次
- 预约时间：2026-04-08 10:00
- 支持操作：改约，不支持全额退款
""",
            },
            "hotfix": {
                "04_当前客服公告.md": """# 当前客服公告

## 本周公告
- 清明假期期间，保洁服务热门档期改约处理时间延长至 30 分钟内。
- 涉及课程卡退款的诉求，本周统一要求人工复核后答复。
- 投诉单如包含“安全”“财产损失”等关键词，必须直接转人工。
""",
            },
        },
    },
    {
        "tenant_id": "training_coach",
        "tenant_name": "启航职业成长学院",
        "admin_username": "training_admin",
        "phone": "16600010003",
        "display_name": "启航教练",
        "app_config": {
            "app_name": "启航职业成长学院",
            "app_subtitle": "学习方案、练习反馈与进度跟踪中心",
            "chat_title": "启航教练",
            "chat_tagline": "根据基础水平与目标生成学习路径，并持续跟进调整",
            "welcome_message": "你好，我是启航教练。你可以告诉我你的基础水平、目标岗位和时间计划，我会帮你设计学习路径。",
            "agent_description": "面向职业培训与能力提升场景的学习方案 Agent，负责路径设计、练习安排、反馈与调优。",
            "recommended_questions": [
                "零基础转产品经理，三个月怎么学？",
                "英语四级水平，想备考雅思 6.5，怎么安排？",
                "我上周只完成了 60% 任务，接下来怎么调整？",
            ],
            "login_hint": "培训方案后台登录 · 建议先看能力模型和路径模板",
            "input_placeholder": "输入学习基础、目标、期限、可投入时长...",
            "send_button_text": "生成方案",
            "theme": {
                "bg": "#f4f7ff",
                "surface": "#ffffff",
                "surface_strong": "#ffffff",
                "line": "#d9e0ff",
                "text": "#27325f",
                "muted": "#6773a8",
                "accent": "#5b7cff",
                "accent_strong": "#3b5be0",
                "accent_soft": "rgba(91, 124, 255, 0.14)",
                "danger": "#d86a70",
            },
        },
        "prompt": """你是“启航职业成长学院”的学习方案 Agent，名字叫“启航教练”。

你的职责：
1. 先识别学员当前水平、目标、时间周期和每周投入时长。
2. 输出阶段化学习路径，不要只给大而空的建议。
3. 每个阶段都要给出练习、反馈方式和进度检查点。
4. 学员完成度不足时，要提供调整建议，而不是简单重复原计划。
5. 回答要像教练在制定行动计划，不要像百科介绍。

回答格式优先按下面结构：
- 当前水平判断：
- 阶段路径：
- 每周练习安排：
- 反馈机制：
- 调整建议：

【知识库内容开始】
{knowledge_context}
【知识库内容结束】""",
        "knowledge": {
            "permanent": {
                "01_学院课程体系.md": """# 学院课程体系

## 课程方向
- 产品经理
- 新媒体运营
- 数据分析
- 英语能力提升

## 学习规划原则
- 先补基础，再做项目
- 每周至少要有一次输出型练习
- 每两周安排一次阶段复盘
""",
                "02_学习路径模板.md": """# 学习路径模板

## 产品经理转岗三个月模板
### 第 1 阶段：基础认知（第 1-2 周）
- 学习产品生命周期、需求分析、竞品分析
- 输出 1 份产品拆解笔记

### 第 2 阶段：实战表达（第 3-6 周）
- 学习 PRD、流程图、用户旅程图
- 输出 1 份需求文档和 1 次项目复盘

### 第 3 阶段：项目冲刺（第 7-12 周）
- 完成 1 个完整作品集项目
- 准备面试问答与表达训练

## 调整原则
- 完成度低于 70%：缩短目标范围，保留高优先级任务
- 完成度高于 90%：可提前进入下一阶段
""",
            },
            "seasonal": {
                "03_反馈与跟踪规则.md": """# 反馈与跟踪规则

## 每周反馈模板
- 本周完成率
- 卡点总结
- 下一周重点

## 学员分层
- A 档：完成率 90% 以上，可加压
- B 档：完成率 70%-90%，按计划推进
- C 档：完成率 70% 以下，需要减负和重排
""",
            },
            "hotfix": {
                "04_当前训练营公告.md": """# 当前训练营公告

## 本期公告
- 4 月产品经理训练营新增“AI 原型工具实践”模块。
- 本周所有学员复盘统一采用“问题-原因-改进”三段式格式。
- 英语训练营本周口语作业统一延后到周日晚提交。
""",
            },
        },
    },
    {
        "tenant_id": "marketing_lab",
        "tenant_name": "星火增长实验室",
        "admin_username": "marketing_admin",
        "phone": "16600010004",
        "display_name": "火花增长官",
        "app_config": {
            "app_name": "星火增长实验室",
            "app_subtitle": "内容策划、多平台发布与增长实验工作台",
            "chat_title": "火花增长官",
            "chat_tagline": "围绕产品目标生成文案、海报结构、视频脚本与发布节奏",
            "welcome_message": "你好，我是火花增长官。告诉我你的产品、活动目标和平台，我会生成多版营销内容与发布时间建议。",
            "agent_description": "面向内容营销与增长运营场景的营销 Agent，负责文案生成、脚本生成与平台差异化改写。",
            "recommended_questions": [
                "给一款新中式茶饮写 3 版小红书开业文案。",
                "围绕五一促销活动生成抖音短视频脚本。",
                "帮我做一份本周内容发布时间表。",
            ],
            "login_hint": "营销工作台登录 · 先设置品牌语气和活动目标",
            "input_placeholder": "输入产品、活动目标、人群、平台和素材方向...",
            "send_button_text": "生成内容",
            "theme": {
                "bg": "#fffaf2",
                "surface": "#ffffff",
                "surface_strong": "#ffffff",
                "line": "#f0dec4",
                "text": "#563a22",
                "muted": "#8f6f57",
                "accent": "#ff8a3d",
                "accent_strong": "#dd6420",
                "accent_soft": "rgba(255, 138, 61, 0.14)",
                "danger": "#d55f61",
            },
        },
        "prompt": """你是“星火增长实验室”的营销 Agent，名字叫“火花增长官”。

你的职责：
1. 根据产品、活动目标、受众和平台，生成多版本营销内容。
2. 输出时要区分抖音、小红书、朋友圈、公众号等平台语气。
3. 除了文案，还要能提供海报文案结构、短视频脚本和发布时间建议。
4. 不要夸大宣传，不要虚构承诺，不要触碰平台敏感表达。
5. 回答要有执行感，像营销策划方案而不是泛泛建议。

回答格式优先按下面结构：
- 核心卖点提炼：
- 内容版本 A/B/C：
- 海报/视频脚本建议：
- 平台适配建议：
- 发布时间建议：

【知识库内容开始】
{knowledge_context}
【知识库内容结束】""",
        "knowledge": {
            "permanent": {
                "01_品牌语气与内容原则.md": """# 品牌语气与内容原则

## 品牌语气
- 真实
- 有温度
- 不端着
- 要有明确行动引导

## 内容原则
- 一条内容只讲一个核心卖点
- 前三秒/前三行必须抓注意力
- 必须带明确 CTA，例如到店、私信、预约、领券
- 禁止出现绝对化承诺，如“全网最低”“100%有效”
""",
                "02_平台内容模板.md": """# 平台内容模板

## 抖音
- 结构：钩子 + 场景 + 反转/利益点 + CTA
- 句子短，节奏快

## 小红书
- 结构：痛点共鸣 + 体验过程 + 结果呈现 + 收藏/私信引导
- 口吻更像真实分享

## 公众号
- 结构：背景 + 价值点 + 方案说明 + 行动引导
- 信息密度更高
""",
            },
            "seasonal": {
                "03_活动与发布时间建议.md": """# 活动与发布时间建议

## 常见活动目标
- 新品曝光
- 到店转化
- 私域拉新
- 老客复购

## 发布时间建议
- 抖音：工作日 12:00、18:30、21:00
- 小红书：工作日 11:30、20:00；周末 10:00、19:30
- 公众号：工作日 08:30 或 20:30
""",
            },
            "hotfix": {
                "04_当前活动公告.md": """# 当前活动公告

## 本周活动
- 五一预热内容全部围绕“到店转化”和“限时优惠”展开。
- 小红书内容统一避免使用“最低价”字样。
- 短视频脚本需增加门店真实场景与用户互动镜头。
""",
            },
        },
    },
    {
        "tenant_id": "crm_sales",
        "tenant_name": "云帆企业服务",
        "admin_username": "crm_admin",
        "phone": "16600010005",
        "display_name": "云帆销售助手",
        "app_config": {
            "app_name": "云帆企业服务",
            "app_subtitle": "客户跟进、成交预测与销售复盘中心",
            "chat_title": "云帆销售助手",
            "chat_tagline": "更新客户记录、分析成交概率并提醒关键跟进动作",
            "welcome_message": "你好，我是云帆销售助手。你可以让我更新客户记录、评估成交概率、提醒跟进或生成销售报告。",
            "agent_description": "面向 B2B 销售与 CRM 运营场景的 CRM Agent，负责客户画像更新、商机推进与销售复盘。",
            "recommended_questions": [
                "帮我更新客户海川科技的最新需求和成交概率。",
                "这周有哪些客户 3 天内需要跟进？",
                "基于本周跟进情况生成一份销售周报。",
            ],
            "login_hint": "CRM 后台登录 · 建议先检查客户阶段和跟进规则",
            "input_placeholder": "输入客户名称、需求变化、跟进记录或报表诉求...",
            "send_button_text": "更新线索",
            "theme": {
                "bg": "#f2fbf8",
                "surface": "#ffffff",
                "surface_strong": "#ffffff",
                "line": "#d4eee5",
                "text": "#18493c",
                "muted": "#5f867a",
                "accent": "#18b57f",
                "accent_strong": "#0d8a60",
                "accent_soft": "rgba(24, 181, 127, 0.14)",
                "danger": "#cf6662",
            },
        },
        "prompt": """你是“云帆企业服务”的 CRM Agent，名字叫“云帆销售助手”。

你的职责：
1. 根据客户跟进信息更新客户画像和阶段判断。
2. 对成交概率给出明确分数与依据。
3. 提醒销售下一步跟进动作，避免只做总结不提建议。
4. 可以输出客户摘要、跟进提醒和销售周报。
5. 不要虚构客户记录，也不要夸大成交把握。

回答格式优先按下面结构：
- 客户阶段判断：
- 成交概率：
- 关键信号：
- 下次跟进建议：
- 报表摘要：

【知识库内容开始】
{knowledge_context}
【知识库内容结束】""",
        "knowledge": {
            "permanent": {
                "01_CRM阶段定义.md": """# CRM 阶段定义

## 客户阶段
- MQL：有初步兴趣，信息不完整
- SQL：已明确需求并愿意沟通方案
- Proposal：已进入方案或报价阶段
- Negotiation：正在谈判预算、合同或交付细节
- Won/Lost：成交/丢单

## 成交概率参考
- MQL：20%-35%
- SQL：40%-55%
- Proposal：60%-75%
- Negotiation：75%-90%
""",
                "02_销售跟进规则.md": """# 销售跟进规则

## 跟进提醒
- 高意向客户 48 小时内必须有下一次动作
- 发出报价后 24 小时内要确认客户反馈
- 谈判期客户不得超过 3 天无更新

## 关键信号
- 正向：主动约演示、询问报价、要求合同样本、拉采购参与
- 风险：只问价格、不确认下一步、长期沉默、频繁比较竞品
""",
            },
            "seasonal": {
                "03_重点客户快照.md": """# 重点客户快照

## 海川科技
- 当前阶段：Proposal
- 当前需求：员工知识助手 + 多租户管理
- 最近动作：已看演示，等待报价优化
- 风险点：预算审批链较长

## 启新教育
- 当前阶段：Negotiation
- 当前需求：培训方案 Agent + CRM 接口
- 最近动作：法务已索要合同模板
""",
            },
            "hotfix": {
                "04_本周销售公告.md": """# 本周销售公告

## 本周提醒
- 本周报价模板统一加入“私有部署说明”段落。
- 对教育行业客户优先强调培训方案 Agent 和学习跟踪能力。
- Proposal 阶段客户本周统一要求输出一页纸价值摘要。
""",
            },
        },
    },
    {
        "tenant_id": "recruiting_hub",
        "tenant_name": "北辰人才科技",
        "admin_username": "recruit_admin",
        "phone": "16600010006",
        "display_name": "北辰招聘官",
        "app_config": {
            "app_name": "北辰人才科技",
            "app_subtitle": "简历筛选、岗位匹配与面试邀约中心",
            "chat_title": "北辰招聘官",
            "chat_tagline": "解析简历、匹配 JD、筛选候选人并安排面试",
            "welcome_message": "你好，我是北辰招聘官。你可以上传简历摘要、岗位 JD 或面试安排诉求，我会帮你做匹配与筛选建议。",
            "agent_description": "面向招聘流程场景的招聘 Agent，负责简历解析、岗位匹配、自动筛选与面试编排建议。",
            "recommended_questions": [
                "帮我把这份产品经理简历和高级产品 JD 做匹配评分。",
                "这个候选人适不适合进入一面？",
                "给候选人生成一条面试邀约短信。",
            ],
            "login_hint": "招聘中台登录 · 先确认岗位 JD 和筛选标准",
            "input_placeholder": "输入岗位 JD、候选人履历摘要或邀约安排需求...",
            "send_button_text": "开始筛选",
            "theme": {
                "bg": "#f6f5ff",
                "surface": "#ffffff",
                "surface_strong": "#ffffff",
                "line": "#dfdaf9",
                "text": "#372d64",
                "muted": "#7368a3",
                "accent": "#7a5cff",
                "accent_strong": "#5e43d4",
                "accent_soft": "rgba(122, 92, 255, 0.14)",
                "danger": "#d76372",
            },
        },
        "prompt": """你是“北辰人才科技”的招聘 Agent，名字叫“北辰招聘官”。

你的职责：
1. 先解析候选人简历信息，再对照岗位 JD 进行匹配。
2. 给出匹配评分时，必须说明理由与风险点。
3. 对于是否进入下一轮，要给清晰建议。
4. 可以生成邀约话术和面试安排建议。
5. 不得输出任何违法歧视性筛选标准。

回答格式优先按下面结构：
- 岗位匹配评分：
- 核心优势：
- 风险点：
- 是否建议进入下一轮：
- 面试邀约建议：

【知识库内容开始】
{knowledge_context}
【知识库内容结束】""",
        "knowledge": {
            "permanent": {
                "01_岗位胜任力标准.md": """# 岗位胜任力标准

## 高级产品经理
- 3 年以上产品经验
- 有 B 端项目经历
- 能独立输出 PRD、原型和需求拆解
- 有跨部门推进经验

## 新媒体运营
- 有内容策划经验
- 熟悉抖音/小红书平台规则
- 有数据复盘意识
""",
                "02_招聘流程规则.md": """# 招聘流程规则

## 筛选规则
- 先看硬性门槛：经验、方向、核心技能
- 再看加分项：行业背景、项目成果、稳定性
- 明显不满足硬性门槛时，直接建议淘汰

## 面试流程
- 初筛通过：安排 30 分钟业务一面
- 业务一面通过：安排用人经理复试
- 核心岗位需增加案例作业环节
""",
            },
            "seasonal": {
                "03_当前JD与候选人示例.md": """# 当前 JD 与候选人示例

## JD：高级产品经理
- B 端 SaaS 方向
- 负责多租户后台、工作流、数据分析模块
- 需要较强跨团队沟通推进能力

## 候选人示例：林岚
- 4 年产品经验
- 做过 CRM、审批流和报表分析
- 有 1 个教育 SaaS 项目和 1 个企服项目
""",
            },
            "hotfix": {
                "04_本周招聘公告.md": """# 本周招聘公告

## 本周提醒
- 高级产品经理岗位本周优先看有企服 SaaS 背景的候选人。
- 邀约文案统一强调“现场/视频面试二选一”。
- 若候选人薪资要求超预算 20% 以上，需先做备注再进入下一轮。
""",
            },
        },
    },
    {
        "tenant_id": "logistics_route",
        "tenant_name": "迅达智慧物流",
        "admin_username": "logistics_admin",
        "phone": "16600010007",
        "display_name": "迅达调度中枢",
        "app_config": {
            "app_name": "迅达智慧物流",
            "app_subtitle": "订单派单、路线优化与异常通知中心",
            "chat_title": "迅达调度中枢",
            "chat_tagline": "订单进来后做路线与司机匹配，并对延误进行通知和补偿建议",
            "welcome_message": "你好，我是迅达调度中枢。你可以输入订单需求、配送区域、时效要求或延误场景，我会给出调度建议。",
            "agent_description": "面向物流调度与配送异常场景的物流 Agent，负责路线优化、司机派单、轨迹跟踪与延误处理建议。",
            "recommended_questions": [
                "今天浦东到闵行的 12 单怎么分配司机更合理？",
                "订单延误 90 分钟，需要怎么通知客户？",
                "冷链订单应该优先派给哪位司机？",
            ],
            "login_hint": "物流调度后台登录 · 先查看运力、路线与赔付规则",
            "input_placeholder": "输入订单批次、区域、时效、司机情况或延误事件...",
            "send_button_text": "生成调度",
            "theme": {
                "bg": "#f4fbfb",
                "surface": "#ffffff",
                "surface_strong": "#ffffff",
                "line": "#d5ecec",
                "text": "#204545",
                "muted": "#628585",
                "accent": "#16a5a1",
                "accent_strong": "#0b7f7b",
                "accent_soft": "rgba(22, 165, 161, 0.14)",
                "danger": "#d56a55",
            },
        },
        "prompt": """你是“迅达智慧物流”的物流调度 Agent，名字叫“迅达调度中枢”。

你的职责：
1. 根据订单数量、区域、时效和车型，给出路线优化和司机分配建议。
2. 对冷链、急件、延误订单做优先级判断。
3. 出现延误时，给出客户通知话术和补偿建议，但必须按规则执行。
4. 输出要像调度中心指令，不要像泛泛建议。
5. 没有依据时，不要编造司机轨迹或赔付标准。

回答格式优先按下面结构：
- 调度判断：
- 路线建议：
- 司机派单：
- 延误风险：
- 客户通知与补偿建议：

【知识库内容开始】
{knowledge_context}
【知识库内容结束】""",
        "knowledge": {
            "permanent": {
                "01_运力与调度规则.md": """# 运力与调度规则

## 调度优先级
- 冷链订单优先
- 时效小于 4 小时的订单优先
- 同一区域集中派单优先

## 派单原则
- 先看车型是否匹配
- 再看区域熟悉度
- 再看当前载货量与可接单数
""",
                "02_延误与补偿规则.md": """# 延误与补偿规则

## 延误定义
- 超过承诺送达时间 30 分钟以上视为延误

## 补偿建议
- 延误 30-60 分钟：发送致歉通知，提供下次运费券
- 延误 60-120 分钟：可追加小额赔付建议，需客服确认
- 超过 120 分钟或影响冷链品质：必须人工介入
""",
            },
            "seasonal": {
                "03_司机与线路示例.md": """# 司机与线路示例

## 司机信息
### 王强
- 车型：中型厢货
- 区域熟悉度：浦东、闵行
- 特长：大单统配

### 刘敏
- 车型：冷链车
- 区域熟悉度：静安、徐汇、浦东
- 特长：冷链订单、时效件

### 赵峰
- 车型：轻型面包车
- 区域熟悉度：徐汇、长宁
- 特长：小件高频配送
""",
            },
            "hotfix": {
                "04_当前物流公告.md": """# 当前物流公告

## 本周公告
- 受道路管制影响，浦东机场周边线路平均增加 25 分钟。
- 冷链订单本周统一优先安排刘敏与备用冷链车。
- 超过 90 分钟的延误，必须同步客户服务中心。
""",
            },
        },
    },
]


def _ensure_tenant_row(item: dict) -> None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT tenant_id FROM tenants WHERE tenant_id = ?",
            (item["tenant_id"],),
        ).fetchone()
    finally:
        conn.close()
    if row:
        update_tenant(
            tenant_id=item["tenant_id"],
            tenant_name=item["tenant_name"],
            admin_username=item["admin_username"],
            enabled=True,
            admin_password=ADMIN_PASSWORD,
        )
    else:
        create_tenant(
            tenant_id=item["tenant_id"],
            tenant_name=item["tenant_name"],
            admin_username=item["admin_username"],
            admin_password=ADMIN_PASSWORD,
        )


def _write_knowledge(item: dict) -> None:
    root = Path(get_tenant_knowledge_dir(item["tenant_id"]))
    if root.exists():
        shutil.rmtree(root)
    for tier, files in item["knowledge"].items():
        tier_dir = root / tier
        tier_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (tier_dir / filename).write_text(content.strip() + "\n", encoding="utf-8")


def _save_front_account(item: dict) -> None:
    save_tenant_phone_account(
        tenant_id=item["tenant_id"],
        phone=item["phone"],
        display_name=item["display_name"],
        password=PHONE_PASSWORD,
        enabled=True,
    )
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            UPDATE phone_accounts
            SET must_change_password = 0,
                balance = 200,
                enabled = 1,
                tenant_id = ?,
                display_name = ?
            WHERE phone = ?
            """,
            (item["tenant_id"], item["display_name"], item["phone"]),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_one(item: dict) -> None:
    _ensure_tenant_row(item)
    ensure_tenant_storage(item["tenant_id"], item["tenant_name"])
    save_tenant_app_config(item["tenant_id"], item["tenant_name"], item["app_config"])
    save_tenant_system_prompt(item["tenant_id"], item["tenant_name"], item["prompt"])
    save_tool_config(load_tool_config(), tenant_id=item["tenant_id"], tenant_name=item["tenant_name"])
    _write_knowledge(item)
    _save_front_account(item)


def main() -> None:
    summary = []
    for item in TENANTS:
        _seed_one(item)
        summary.append(
            {
                "tenant_id": item["tenant_id"],
                "tenant_name": item["tenant_name"],
                "admin_username": item["admin_username"],
                "admin_password": ADMIN_PASSWORD,
                "phone": item["phone"],
                "phone_password": PHONE_PASSWORD,
                "agent_name": item["display_name"],
            }
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
