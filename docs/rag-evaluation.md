# RAG Evaluation

项目现在的评测分成两层：

- 检索层：保留 `hit@1 / hit@3 / hit@5 / avg_top_score`
- 生成层：复用真实聊天工作流生成答案，再计算答案质量

## Case 结构

支持的题集字段：

```json
[
  {
    "question": "报销流程怎么走",
    "expected_keywords": ["报销", "审批"],
    "expected_tier": "permanent",
    "expected_source": "财务制度",
    "reference_answer": "先提交报销申请并走审批流程。"
  }
]
```

其中：

- `question` 必填
- `expected_keywords / expected_tier / expected_source` 用于检索命中判断
- `reference_answer` 目前是可选字段，后续可继续扩展 correctness 类指标

## 当前行为

评测接口现在会：

1. 复用真实 `run_chat_workflow_with_runtime` 生成答案
2. 统计检索 hit@k
3. 始终产出一个本地 `answer_relevance_proxy`
4. 如果环境里安装了 `ragas` 且评测 LLM 可用，则额外计算：
   - `Faithfulness`
   - `Response Relevancy`

## 依赖说明

当前代码是“自动启用、缺依赖自动降级”模式。

如果要真正开启 Ragas 指标，建议补装：

```bash
pip install ragas langchain-openai
```

如果当前 embedding 仍是 `local_hash`，那么：

- `Faithfulness` 可以启用
- `Response Relevancy` 可能因为缺少兼容 embedding 而回退
- 回退时前端会显示 `provider/status/reason`

## Phoenix

这轮先把“可量化评测”落在项目现有评测链路里，重点解决：

- 不再只看召回
- 可以量化 Prompt/模型迭代后的答案忠实度

Arize Phoenix 更适合做下一层：

- 在线 tracing
- span 级观测
- 评测结果与线上请求关联

也就是说，这次已经把“评测数据面”铺好了；下一步如果要接 Phoenix，建议从聊天链路的 tracing 和 evaluation export 开始。
