"""LLM 流式调用服务。

把模型调用、降级重试、输出护栏统一收口，避免主路由里堆太多细节。
"""
from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncGenerator, Callable

import aiohttp


def mask_api_key(key: str) -> str:
    """把 Key 做脱敏，避免日志泄露。"""
    if len(key or "") <= 10:
        return "***"
    return f"{key[:5]}...{key[-4:]}"


def build_model_route(model_settings: dict, workflow_route: list[str] | None) -> list[str]:
    """统一产出模型候选顺序。"""
    route = [item for item in (workflow_route or []) if str(item).strip()]
    if route:
        return route
    primary_model = str(model_settings.get("model_primary") or "").strip()
    fallback_model = str(model_settings.get("model_fallback") or "").strip()
    deduped: list[str] = []
    for item in [primary_model, fallback_model]:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def pick_unused_api_key(api_keys: list[str], tried_key_masked: set[str]) -> str:
    """优先挑没试过的 Key，避免同一个坏 Key 连续命中。"""
    if not api_keys:
        return ""
    candidates = [key for key in api_keys if mask_api_key(key) not in tried_key_masked]
    if candidates:
        return random.choice(candidates)
    return random.choice(api_keys)


async def stream_chat_completion(
    *,
    question: str,
    system_prompt: str,
    model_settings: dict,
    workflow_route: list[str] | None,
    default_base_url: str,
    ssl_ctx,
    on_model_selected: Callable[[str], None],
    on_output_event: Callable[[dict], None],
    on_error: Callable[[str], None],
    protect_output: Callable[[str], tuple[str, list[dict]]],
    user_facing_error: Callable[[], str],
    collector: list[str],
) -> AsyncGenerator[str, None]:
    """执行带重试和降级的流式模型调用。"""
    api_keys = list(model_settings.get("api_keys") or [])
    base_url = str(model_settings.get("base_url") or default_base_url or "").rstrip("/")
    model_route = build_model_route(model_settings, workflow_route)
    tried_key_masked: set[str] = set()

    for attempt_idx, model in enumerate(model_route):
        max_key_attempts = min(max(len(api_keys), 1), 3)
        for key_attempt in range(max_key_attempts):
            current_key = pick_unused_api_key(api_keys, tried_key_masked)
            tried_key_masked.add(mask_api_key(current_key))
            try:
                on_model_selected(model)
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as session:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": question},
                        ],
                        "stream": True,
                        "temperature": 0.7,
                        "max_tokens": 2000,
                    }
                    headers = {
                        "Authorization": f"Bearer {current_key}",
                        "Content-Type": "application/json",
                    }
                    async with session.post(
                        f"{base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        if resp.status == 200:
                            async for line in resp.content:
                                line = line.decode("utf-8").strip()
                                if not line or not line.startswith("data: "):
                                    continue
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                except json.JSONDecodeError:
                                    continue
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if not content:
                                    continue
                                safe_content, output_events = protect_output(content)
                                for event in output_events:
                                    on_output_event(event)
                                collector.append(safe_content)
                                yield f"data: {json.dumps({'content': safe_content})}\n\n"
                            return

                        error_text = await resp.text()
                        should_retry_key = resp.status in {401, 429, 500, 502, 503, 504}
                        can_retry_key = key_attempt < max_key_attempts - 1
                        can_degrade_model = attempt_idx < len(model_route) - 1
                        if should_retry_key and can_retry_key:
                            yield f"data: {json.dumps({'status': 'degrading', 'content': ''})}\n\n"
                            continue
                        if can_degrade_model:
                            yield f"data: {json.dumps({'status': 'degrading', 'content': ''})}\n\n"
                            break
                        on_error(f"llm_status_{resp.status}:{error_text[:200]}")
                        yield f"data: {json.dumps({'content': user_facing_error()})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
            except asyncio.TimeoutError:
                if key_attempt < max_key_attempts - 1:
                    yield f"data: {json.dumps({'status': 'degrading', 'content': ''})}\n\n"
                    continue
                if attempt_idx < len(model_route) - 1:
                    yield f"data: {json.dumps({'status': 'degrading', 'content': ''})}\n\n"
                    break
                on_error("llm_timeout")
                yield f"data: {json.dumps({'content': '当前访问人数较多，请稍后再试一次。'})}\n\n"
                yield "data: [DONE]\n\n"
                return
            except Exception as exc:  # pragma: no cover - 网络故障难稳定复现
                if key_attempt < max_key_attempts - 1:
                    yield f"data: {json.dumps({'status': 'degrading', 'content': ''})}\n\n"
                    continue
                if attempt_idx < len(model_route) - 1:
                    yield f"data: {json.dumps({'status': 'degrading', 'content': ''})}\n\n"
                    break
                on_error(str(exc))
                yield f"data: {json.dumps({'content': user_facing_error()})}\n\n"
                yield "data: [DONE]\n\n"
                return
