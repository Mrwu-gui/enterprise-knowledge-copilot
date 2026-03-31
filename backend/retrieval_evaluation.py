"""检索评测体系。

先做一套最小可用的评测能力：
- 输入标准问题集
- 运行当前检索链
- 统计 hit@1 / hit@3 / hit@5
- 输出每题命中详情
"""
from __future__ import annotations

from typing import Any


def _normalize_case(case: dict[str, Any]) -> dict[str, Any]:
    """清洗评测题，保证字段稳定。"""
    return {
        "question": str(case.get("question") or "").strip(),
        "expected_keywords": [str(item).strip() for item in (case.get("expected_keywords") or []) if str(item).strip()],
        "expected_tier": str(case.get("expected_tier") or "").strip(),
        "expected_source": str(case.get("expected_source") or "").strip(),
    }


def _is_hit(result: dict[str, Any], case: dict[str, Any]) -> bool:
    """判断单条召回结果是否命中预期。"""
    source_text = " ".join(
        [
            str(result.get("source") or ""),
            str(result.get("title") or ""),
            str(result.get("content") or ""),
            str(result.get("snippet") or ""),
        ]
    ).lower()
    expected_keywords = [item.lower() for item in case.get("expected_keywords") or []]
    expected_tier = str(case.get("expected_tier") or "").strip().lower()
    expected_source = str(case.get("expected_source") or "").strip().lower()

    keyword_hit = True if not expected_keywords else any(keyword in source_text for keyword in expected_keywords)
    tier_hit = True if not expected_tier else str(result.get("tier") or "").strip().lower() == expected_tier
    source_hit = True if not expected_source else expected_source in source_text
    return keyword_hit and tier_hit and source_hit


def run_retrieval_evaluation(
    *,
    rag_runtime: Any,
    cases: list[dict[str, Any]],
    retrieval_config: dict[str, Any] | None = None,
    backend_override: str | None = None,
) -> dict[str, Any]:
    """运行一轮检索评测。"""
    normalized_cases = [_normalize_case(case) for case in cases]
    valid_cases = [case for case in normalized_cases if case["question"]]
    details: list[dict[str, Any]] = []
    hit_at_1 = 0
    hit_at_3 = 0
    hit_at_5 = 0
    top_scores: list[float] = []

    for case in valid_cases:
        results = rag_runtime.search(
            case["question"],
            top_k=5,
            backend_override=backend_override,
        )
        top_scores.append(float(results[0].get("score") or 0) if results else 0.0)
        top1 = results[:1]
        top3 = results[:3]
        top5 = results[:5]
        top1_hit = any(_is_hit(item, case) for item in top1)
        top3_hit = any(_is_hit(item, case) for item in top3)
        top5_hit = any(_is_hit(item, case) for item in top5)
        if top1_hit:
            hit_at_1 += 1
        if top3_hit:
            hit_at_3 += 1
        if top5_hit:
            hit_at_5 += 1
        details.append(
            {
                "question": case["question"],
                "expected_keywords": case["expected_keywords"],
                "expected_tier": case["expected_tier"],
                "expected_source": case["expected_source"],
                "top1_hit": top1_hit,
                "top3_hit": top3_hit,
                "top5_hit": top5_hit,
                "top_score": round(float(results[0].get("score") or 0), 4) if results else 0.0,
                "results": [
                    {
                        "source": item.get("source", ""),
                        "tier": item.get("tier", ""),
                        "score": round(float(item.get("score") or 0), 4),
                        "backend": item.get("backend", ""),
                    }
                    for item in results
                ],
            }
        )

    total = len(valid_cases)
    avg_top_score = round(sum(top_scores) / total, 4) if total else 0.0
    return {
        "total_questions": total,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "hit_at_5": hit_at_5,
        "avg_top_score": avg_top_score,
        "detail": details,
        "config_snapshot": {
            "backend_override": backend_override or "",
            "retrieval_config": retrieval_config or {},
        },
    }
