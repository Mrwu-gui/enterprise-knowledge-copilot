# 本地演示企业账号

本地地址：

- 租户后台：`http://localhost:6090/tenant`
- 前台登录：`http://localhost:6090/login`

统一密码：

- 租户后台密码：`AgentDemo2026!`
- 前台手机号密码：`ChatDemo2026!`

## 账号清单

| 企业 | 场景 | 租户 ID | 后台账号 | 前台手机号 | Agent 名称 |
| --- | --- | --- | --- | --- | --- |
| 速修联维（上海）科技有限公司 | 维修调度 | `repair_dispatch` | `repair_admin` | `16600010001` | 小维调度官 |
| 悦程生活服务集团 | 客服中心 | `service_desk` | `service_admin` | `16600010002` | 小悦客服 |
| 启航职业成长学院 | 培训方案 | `training_coach` | `training_admin` | `16600010003` | 启航教练 |
| 星火增长实验室 | 营销策划 | `marketing_lab` | `marketing_admin` | `16600010004` | 火花增长官 |
| 云帆企业服务 | CRM 销售 | `crm_sales` | `crm_admin` | `16600010005` | 云帆销售助手 |
| 北辰人才科技 | 招聘筛选 | `recruiting_hub` | `recruit_admin` | `16600010006` | 北辰招聘官 |
| 迅达智慧物流 | 物流调度 | `logistics_route` | `logistics_admin` | `16600010007` | 迅达调度中枢 |

## 已初始化内容

- 企业名称与后台账号
- 前台手机号账号
- 企业欢迎语与页面文案
- 各自的基础知识库目录：`permanent` / `seasonal` / `hotfix`
- 企业级默认系统提示词

## 说明

- 这 7 个企业当前共用同一套模型配置与 Key 配置。
- 当前先完成“企业账号与资料底座”，后续再在此基础上讨论并接入工作流能力。
