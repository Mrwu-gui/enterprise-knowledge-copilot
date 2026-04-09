"""租户工作流执行引擎。"""
from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import re
import shutil
import smtplib
import ssl
import textwrap
import time
from types import SimpleNamespace
from copy import deepcopy
from email.mime.text import MIMEText
from typing import Any, Callable, TypedDict

import aiohttp

from backend.llm_service import build_provider_route
from backend.model_config import load_model_config
from backend.rag import build_runtime_rag_engine
from backend.retrieval_config import load_retrieval_config
from backend.tenant_config import get_tenant_knowledge_dir, load_tenant_app_config, load_tenant_system_prompt
from backend.tool_config import load_tool_config
from backend.workflow_config import load_workflow_config

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


class WorkflowRuntimeError(RuntimeError):
    """工作流运行错误。"""


class WorkflowGraphState(TypedDict, total=False):
    input: dict[str, Any]
    nodes: dict[str, Any]
    last_result: dict[str, Any]
    notifications: list[dict[str, Any]]
    forms: dict[str, Any]
    workflow: dict[str, Any]
    logs: list[dict[str, Any]]
    next_node_id: str
    entry_node_id: str
    stop_before: list[str]
    stopped_at: str


_verify_ssl = os.environ.get("VERIFY_SSL", "0").strip()
if _verify_ssl == "1":
    try:
        import certifi

        WORKFLOW_SSL_CTX = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        WORKFLOW_SSL_CTX = ssl.create_default_context()
else:
    WORKFLOW_SSL_CTX = False


def _now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _safe_json_loads(value: object, fallback):
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    text = str(value or "").strip()
    if not text:
        return deepcopy(fallback)
    try:
        parsed = json.loads(text)
    except Exception:
        return deepcopy(fallback)
    return parsed


def _to_number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _contains(container: object, needle: object) -> bool:
    if container is None:
        return False
    return str(needle) in str(container)


def _dot_get(data: object, path: str, default: object = "") -> object:
    if not path:
        return data
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part, default)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else default
        else:
            current = getattr(current, part, default)
        if current is default:
            break
    return current


_TPL_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def _render_template(value: object, context: dict) -> object:
    if isinstance(value, dict):
        return {k: _render_template(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_template(item, context) for item in value]
    text = str(value or "")
    if "{{" not in text:
        return text
    return _TPL_RE.sub(lambda m: str(_dot_get(context, m.group(1), "")), text)


def _prepare_condition(expr: str) -> str:
    result = str(expr or "").strip()
    result = result.replace("&&", " and ").replace("||", " or ")
    result = result.replace("===", "==").replace("!==", "!=")
    result = re.sub(r"(\S+)\.includes\(", r"contains(\1, ", result)
    return result


def _to_attr_object(value: object):
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _to_attr_object(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_to_attr_object(item) for item in value]
    return value


def _eval_condition(expr: str, context: dict) -> bool:
    safe_expr = _prepare_condition(expr)
    if not safe_expr:
        return False
    attr_context = {key: _to_attr_object(value) for key, value in context.items()}
    locals_map = {
        "contains": _contains,
        "len": len,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "math": math,
        **attr_context,
    }
    return bool(eval(safe_expr, {"__builtins__": {}}, locals_map))


def _parse_bool(value: object) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "是"}


def _node_label(node: dict) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return str(data.get("label") or node.get("type") or node.get("id") or "node")


async def _call_llm(*, prompt: str, model_settings: dict, node_data: dict) -> dict:
    workflow_route = []
    chosen_model = str(node_data.get("model") or "").strip()
    if chosen_model and chosen_model != "__default__":
        workflow_route.append(chosen_model)
    provider_routes = build_provider_route(
        model_settings=model_settings,
        workflow_route=workflow_route,
        default_base_url=str(model_settings.get("base_url") or ""),
    )
    if not provider_routes:
        raise WorkflowRuntimeError("当前租户没有可用模型供应商")
    temperature = _to_number(node_data.get("temperature"), 0.7)
    max_tokens = int(_to_number(node_data.get("max_tokens"), 1200))
    last_error = "模型请求失败"
    for provider in provider_routes:
        for model in provider.get("model_route") or []:
            api_keys = list(provider.get("api_keys") or [])
            for api_key in api_keys[:3]:
                try:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "你是企业自动化流程中的智能处理节点，请只输出对后续节点有用的结果。"},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    }
                    connector = aiohttp.TCPConnector(ssl=WORKFLOW_SSL_CTX)
                    async with aiohttp.ClientSession(connector=connector) as session:
                        async with session.post(
                            f"{str(provider.get('base_url') or '').rstrip('/')}/chat/completions",
                            json=payload,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=120),
                        ) as resp:
                            text = await resp.text()
                            if resp.status >= 400:
                                last_error = f"模型接口异常: HTTP {resp.status}"
                                continue
                            data = json.loads(text)
                            content = (
                                data.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )
                            return {
                                "provider_id": provider.get("provider_id", ""),
                                "provider_label": provider.get("provider_label", ""),
                                "model": model,
                                "text": str(content or "").strip(),
                                "raw": data,
                            }
                except Exception as exc:
                    last_error = str(exc)
                    continue
    raise WorkflowRuntimeError(last_error)


def _filter_knowledge_hits(results: list[dict], node_data: dict) -> list[dict]:
    threshold = _to_number(node_data.get("threshold"), 0.0)
    knowledge_base = str(node_data.get("knowledgeBase") or "").strip()
    legacy_tier_map = {
        "默认知识库": "",
        "L1 基础库": "permanent",
        "L2 增量库": "seasonal",
        "L3 热库": "hotfix",
    }
    legacy_tier = legacy_tier_map.get(knowledge_base, None)
    filtered = []
    for item in results:
        score = _to_number(item.get("score"), 0.0)
        if score < threshold:
            continue
        if legacy_tier is not None:
            if legacy_tier and str(item.get("tier") or "") != legacy_tier:
                continue
        elif knowledge_base and knowledge_base != "全部知识库":
            item_library = str(item.get("library_id") or "").strip()
            item_library_name = str(item.get("library_name") or "").strip()
            if knowledge_base not in {item_library, item_library_name}:
                continue
        filtered.append(item)
    return filtered


def _outgoing_map(connections: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for item in connections:
        result.setdefault(str(item.get("from") or ""), []).append(item)
    return result


def _incoming_map(connections: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for item in connections:
        result.setdefault(str(item.get("to") or ""), []).append(item)
    return result


def _find_start_node(nodes: list[dict]) -> dict:
    start = next((node for node in nodes if node.get("type") == "start"), None)
    if start:
        return start
    if nodes:
        return nodes[0]
    raise WorkflowRuntimeError("工作流没有节点")


def _find_merge_node(start_ids: list[str], outgoing: dict[str, list[dict]]) -> str | None:
    reachable_sets: list[set[str]] = []
    for start_id in start_ids:
        seen: set[str] = set()
        queue = [start_id]
        while queue:
            current = queue.pop(0)
            for conn in outgoing.get(current, []):
                nxt = str(conn.get("to") or "")
                if nxt and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        reachable_sets.append(seen)
    if not reachable_sets:
        return None
    common = set.intersection(*reachable_sets) if len(reachable_sets) > 1 else reachable_sets[0]
    if not common:
        return None
    for node_id in common:
        return node_id
    return None


def _merge_runtime_state(
    parent_state: WorkflowGraphState,
    branch_state: WorkflowGraphState,
    *,
    base_log_count: int = 0,
    base_notification_count: int = 0,
    base_node_keys: set[str] | None = None,
    base_form_keys: set[str] | None = None,
) -> None:
    branch_nodes = branch_state.get("nodes") or {}
    for key, value in branch_nodes.items():
        if not base_node_keys or key not in base_node_keys or parent_state["nodes"].get(key) != value:
            parent_state["nodes"][key] = deepcopy(value)
    branch_forms = branch_state.get("forms") or {}
    for key, value in branch_forms.items():
        if not base_form_keys or key not in base_form_keys or parent_state["forms"].get(key) != value:
            parent_state["forms"][key] = deepcopy(value)
    branch_notifications = list(branch_state.get("notifications") or [])
    if base_notification_count <= len(branch_notifications):
        parent_state["notifications"].extend(deepcopy(branch_notifications[base_notification_count:]))
    else:
        parent_state["notifications"] = deepcopy(branch_notifications)
    parent_state["last_result"] = deepcopy(branch_state.get("last_result") or {})
    branch_logs = list(branch_state.get("logs") or [])
    if base_log_count <= len(branch_logs):
        parent_state["logs"].extend(deepcopy(branch_logs[base_log_count:]))
    else:
        parent_state["logs"][:] = deepcopy(branch_logs)
    parent_state["stopped_at"] = str(branch_state.get("stopped_at") or "")
    parent_state["next_node_id"] = str(branch_state.get("next_node_id") or "")


async def _send_email(tool_cfg: dict, *, to_email: str, subject: str, content: str) -> dict:
    email_cfg = tool_cfg.get("email") if isinstance(tool_cfg.get("email"), dict) else {}
    if not email_cfg.get("enabled"):
        return {"ok": False, "msg": "邮件工具未启用"}
    host = str(email_cfg.get("smtp_host") or "").strip()
    port = int(email_cfg.get("smtp_port") or 465)
    username = str(email_cfg.get("username") or "").strip()
    password = str(email_cfg.get("password") or "").strip()
    from_email = str(email_cfg.get("from_email") or username).strip()
    from_name = str(email_cfg.get("from_name") or "企业知识助手").strip()
    if not host or not from_email:
        return {"ok": False, "msg": "邮件配置不完整"}
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email

    def _send() -> None:
        if email_cfg.get("use_ssl", True):
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        with server:
            if email_cfg.get("use_tls"):
                server.starttls(context=ssl.create_default_context())
            if username:
                server.login(username, password)
            server.send_message(msg)

    try:
        await asyncio.to_thread(_send)
        return {"ok": True, "msg": "邮件已发送"}
    except Exception as exc:
        return {"ok": False, "msg": str(exc)}


async def _call_mcp_server(
    tool_cfg: dict,
    *,
    node_data: dict,
    context: dict,
    tenant_id: str,
    tenant_name: str,
) -> dict:
    mcp_cfg = tool_cfg.get("mcp") if isinstance(tool_cfg.get("mcp"), dict) else {}
    if not mcp_cfg.get("enabled"):
        raise WorkflowRuntimeError("MCP 工具未启用")
    server_id = str(_render_template(node_data.get("serverId") or "", context)).strip()
    tool_name = str(_render_template(node_data.get("toolName") or "", context)).strip()
    payload_rendered = _render_template(node_data.get("payload") or "{}", context)
    payload_data = _safe_json_loads(payload_rendered, None)
    if not server_id:
        raise WorkflowRuntimeError("MCP 节点缺少服务 ID")
    if not tool_name:
        raise WorkflowRuntimeError("MCP 节点缺少工具名称")
    servers = mcp_cfg.get("servers") if isinstance(mcp_cfg.get("servers"), list) else []
    target = None
    for item in servers:
        if not isinstance(item, dict):
            continue
        if item.get("enabled") is False:
            continue
        current_id = str(item.get("server_id") or item.get("id") or "").strip()
        if current_id == server_id:
            target = item
            break
    if not target:
        raise WorkflowRuntimeError(f"MCP 服务不存在或未启用：{server_id}")
    bridge_url = str(target.get("bridge_url") or "").strip()
    if not bridge_url:
        raise WorkflowRuntimeError(f"MCP 服务未配置调用地址：{server_id}")
    headers = {}
    if isinstance(target.get("headers"), dict):
        headers.update({str(k): str(v) for k, v in target.get("headers", {}).items()})
    auth_token = str(target.get("auth_token") or "").strip()
    if auth_token:
        headers.setdefault("Authorization", f"Bearer {auth_token}")
    headers.setdefault("Content-Type", "application/json")
    timeout_seconds = max(3, int(_to_number(mcp_cfg.get("request_timeout_seconds"), 30)))
    request_body = {
        "tool": tool_name,
        "input": payload_data if payload_data is not None else str(payload_rendered or ""),
        "context": {
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "input": deepcopy(context.get("input") or {}),
            "last": deepcopy(context.get("last") or {}),
        },
    }
    connector = aiohttp.TCPConnector(ssl=WORKFLOW_SSL_CTX)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(
            bridge_url,
            json=request_body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        ) as resp:
            text = await resp.text()
            parsed = _safe_json_loads(text, {})
            ok = resp.status < 400 and not (isinstance(parsed, dict) and parsed.get("ok") is False)
            return {
                "ok": ok,
                "status": resp.status,
                "server_id": server_id,
                "server_label": str(target.get("label") or server_id),
                "tool": tool_name,
                "request": request_body,
                "body": parsed if parsed else text,
                "result": parsed.get("result") if isinstance(parsed, dict) and "result" in parsed else (parsed if parsed else text),
                "message": str(parsed.get("message") or "") if isinstance(parsed, dict) else "",
            }


async def _run_script(node_data: dict, runtime_context: dict) -> dict:
    script_type = str(node_data.get("scriptType") or "Python").strip()
    code = str(node_data.get("code") or "").strip()
    if not code:
        return {"ok": True, "stdout": "", "stderr": "", "result": None}
    timeout_seconds = max(1, int(_to_number(node_data.get("timeout"), 30)))
    input_payload = {
        "input": runtime_context.get("input") or {},
        "state": runtime_context.get("state") or {},
        "last_result": runtime_context.get("last_result") or {},
    }
    if script_type.lower() == "javascript":
        node_bin = shutil.which("node")
        if not node_bin:
            raise WorkflowRuntimeError("当前环境未安装 Node.js，无法执行 JavaScript 节点")
        wrapper = textwrap.dedent(
            """
            const input = JSON.parse(process.env.WF_INPUT || "{}");
            let result = null;
            let exports = {};
            let module = { exports };
            async function main(ctx) {
            %s
            }
            Promise.resolve(main(input)).then((value) => {
              const output = value === undefined ? (module.exports || exports || result) : value;
              process.stdout.write(JSON.stringify({ result: output }));
            }).catch((err) => {
              process.stderr.write(String(err && err.stack ? err.stack : err));
              process.exit(1);
            });
            """
        ).strip() % textwrap.indent(code, "  ")
        proc = await asyncio.create_subprocess_exec(
            node_bin,
            "-e",
            wrapper,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"WF_INPUT": json.dumps(input_payload, ensure_ascii=False)},
        )
    else:
        payload_literal = repr(input_payload)
        wrapper = textwrap.dedent(
            f"""
            import json
            ctx = {payload_literal}
            result = None
            {code}
            print(json.dumps({{"result": result}}, ensure_ascii=False))
            """
        ).strip()
        proc = await asyncio.create_subprocess_exec(
            shutil.which("python3") or "python3",
            "-c",
            wrapper,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError as exc:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        raise WorkflowRuntimeError(f"脚本执行超时（>{timeout_seconds}s）") from exc
    stdout_text = stdout.decode("utf-8", errors="ignore").strip()
    stderr_text = stderr.decode("utf-8", errors="ignore").strip()
    if proc.returncode != 0:
        raise WorkflowRuntimeError(stderr_text or "脚本执行失败")
    parsed = _safe_json_loads(stdout_text, {})
    return {
        "ok": True,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "result": parsed.get("result") if isinstance(parsed, dict) else stdout_text,
    }


async def _execute_node_logic(
    *,
    current_id: str,
    node: dict,
    state: WorkflowGraphState,
    node_map: dict[str, dict],
    outgoing: dict[str, list[dict]],
    tenant_id: str,
    tenant_name: str,
    model_settings: dict,
    rag_runtime,
    tool_settings: dict,
    max_depth: int,
    branch_runner: Callable[[str, set[str] | None, set[str] | None], Any],
) -> tuple[dict, str | None]:
    node_type = str(node.get("type") or "").strip()
    node_data = node.get("data") if isinstance(node.get("data"), dict) else {}
    context = {
        "input": state["input"],
        "state": state,
        "nodes": state["nodes"],
        "last": state["last_result"],
        "workflow": state["workflow"],
        "now": _now_text(),
    }
    result: dict = {"ok": True}
    next_id: str | None = None

    if node_type == "start":
        result = {
            "ok": True,
            "triggerType": str(node_data.get("triggerType") or "手动触发"),
            "payload": deepcopy(state["input"]),
        }
    elif node_type == "ai":
        rendered_prompt = str(_render_template(node_data.get("prompt") or "{{input.text}}", context))
        llm_result = await _call_llm(prompt=rendered_prompt, model_settings=model_settings, node_data=node_data)
        result = {
            "ok": True,
            "prompt": rendered_prompt,
            "model": llm_result.get("model", ""),
            "provider": llm_result.get("provider_label", ""),
            "text": llm_result.get("text", ""),
            "raw": llm_result.get("raw", {}),
        }
    elif node_type == "knowledge":
        query = str(_render_template(node_data.get("query") or "{{input.text}}", context)).strip()
        top_k = max(1, int(_to_number(node_data.get("topK"), 5)))
        search_results = rag_runtime.search(query=query, top_k=max(top_k, 5))
        filtered = _filter_knowledge_hits(search_results, node_data)[:top_k]
        result = {
            "ok": True,
            "query": query,
            "top_k": top_k,
            "hits": filtered,
            "knowledge_text": "\n\n".join(str(item.get("content") or "") for item in filtered),
        }
    elif node_type == "condition":
        expression = str(node_data.get("condition") or "").strip()
        matched = _eval_condition(expression, context)
        result = {
            "ok": True,
            "expression": expression,
            "matched": matched,
        }
        branches = list(outgoing.get(current_id, []))
        next_id = str((branches[0] if matched else (branches[1] if len(branches) > 1 else {})).get("to") or "") or None
    elif node_type == "http":
        url = str(_render_template(node_data.get("url") or "", context)).strip()
        method = str(node_data.get("method") or "GET").strip().upper()
        headers = _safe_json_loads(_render_template(node_data.get("headers") or "", context), {})
        body = _render_template(node_data.get("body") or "", context)
        json_body = _safe_json_loads(body, None)
        connector = aiohttp.TCPConnector(ssl=WORKFLOW_SSL_CTX)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.request(
                method,
                url,
                headers=headers if isinstance(headers, dict) else {},
                json=json_body if isinstance(json_body, (dict, list)) else None,
                data=None if isinstance(json_body, (dict, list)) else (str(body) if body else None),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                text = await resp.text()
                parsed = _safe_json_loads(text, {})
                result = {
                    "ok": resp.status < 400,
                    "status": resp.status,
                    "url": url,
                    "method": method,
                    "headers": dict(resp.headers),
                    "body": parsed if parsed else text,
                }
    elif node_type == "script":
        result = await _run_script(node_data, context)
    elif node_type == "notify":
        channel = str(node_data.get("channel") or "站内推送").strip()
        to_value = str(_render_template(node_data.get("to") or "", context)).strip()
        title = str(_render_template(node_data.get("title") or "", context)).strip()
        content = str(_render_template(node_data.get("content") or "", context)).strip()
        delivery = {"ok": True, "channel": channel, "to": to_value, "title": title, "content": content}
        if channel == "邮件" and to_value:
            delivery = {"channel": channel, "to": to_value, "title": title, "content": content}
            delivery.update(await _send_email(tool_settings, to_email=to_value, subject=title or "工作流通知", content=content))
        state["notifications"].append(delivery)
        result = delivery
    elif node_type == "mcp":
        result = await _call_mcp_server(
            tool_cfg=tool_settings,
            node_data=node_data,
            context=context,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
        )
    elif node_type == "delay":
        duration = max(0, _to_number(node_data.get("duration"), 0))
        unit = str(node_data.get("timeUnit") or "秒").strip()
        multiplier = {"秒": 1, "分钟": 60, "小时": 3600, "天": 86400}.get(unit, 1)
        actual_seconds = duration * multiplier
        sleep_seconds = min(actual_seconds, 5)
        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)
        result = {
            "ok": True,
            "requested_seconds": actual_seconds,
            "slept_seconds": sleep_seconds,
        }
    elif node_type == "form":
        fields = _safe_json_loads(node_data.get("fields") or "[]", [])
        form_values = state["input"].get("forms", {}).get(current_id)
        if form_values is None:
            form_values = state["input"].get("form", {})
        state["forms"][current_id] = {"schema": fields, "values": deepcopy(form_values or {})}
        result = {
            "ok": True,
            "formName": str(node_data.get("formName") or _node_label(node)),
            "fields": fields,
            "values": deepcopy(form_values or {}),
        }
    elif node_type == "parallel":
        branch_conns = list(outgoing.get(current_id, []))
        branch_ids = [str(item.get("to") or "") for item in branch_conns if str(item.get("to") or "").strip()]
        merge_id = _find_merge_node(branch_ids, outgoing)
        branch_tasks = [
            branch_runner(branch_id, stop_before={merge_id} if merge_id else set(), stack=set())
            for branch_id in branch_ids
        ]
        branch_results = await asyncio.gather(*branch_tasks) if branch_tasks else []
        normalized_results = []
        for item in branch_results:
            if isinstance(item, dict) and isinstance(item.get("graph_state"), dict):
                _merge_runtime_state(
                    state,
                    item.get("graph_state") or {},
                    base_log_count=int(item.get("base_log_count") or 0),
                    base_notification_count=int(item.get("base_notification_count") or 0),
                    base_node_keys={str(key) for key in item.get("base_node_keys") or []},
                    base_form_keys={str(key) for key in item.get("base_form_keys") or []},
                )
                normalized_results.append(
                    {
                        "last_result": deepcopy(item.get("last_result") or {}),
                        "stopped_at": str(item.get("stopped_at") or ""),
                    }
                )
            else:
                normalized_results.append(item)
        result = {
            "ok": True,
            "branches": normalized_results,
            "merge_node_id": merge_id or "",
        }
        next_id = merge_id
    elif node_type == "loop":
        loop_type = str(node_data.get("loopType") or "次数循环").strip()
        loop_count = max(0, int(_to_number(node_data.get("loopCount"), 0)))
        branch_conns = list(outgoing.get(current_id, []))
        body_id = str((branch_conns[0] if branch_conns else {}).get("to") or "")
        exit_id = str((branch_conns[1] if len(branch_conns) > 1 else {}).get("to") or "")
        runs = []
        if loop_type == "次数循环" and body_id:
            for index in range(loop_count):
                state["input"]["loop_index"] = index
                branch_result = await branch_runner(body_id, stop_before={current_id}, stack=set())
                if isinstance(branch_result, dict) and isinstance(branch_result.get("graph_state"), dict):
                    _merge_runtime_state(
                        state,
                        branch_result.get("graph_state") or {},
                        base_log_count=int(branch_result.get("base_log_count") or 0),
                        base_notification_count=int(branch_result.get("base_notification_count") or 0),
                        base_node_keys={str(key) for key in branch_result.get("base_node_keys") or []},
                        base_form_keys={str(key) for key in branch_result.get("base_form_keys") or []},
                    )
                    branch_result = {
                        "last_result": deepcopy(branch_result.get("last_result") or {}),
                        "stopped_at": str(branch_result.get("stopped_at") or ""),
                    }
                runs.append(branch_result)
        elif loop_type == "条件循环" and body_id:
            max_turns = max(1, int(_to_number(node_data.get("maxTurns"), 10)))
            for index in range(max_turns):
                state["input"]["loop_index"] = index
                loop_context = {
                    "input": state["input"],
                    "state": state,
                    "nodes": state["nodes"],
                    "last": state["last_result"],
                    "workflow": state["workflow"],
                    "now": _now_text(),
                }
                if not _eval_condition(str(node_data.get("condition") or ""), loop_context):
                    break
                branch_result = await branch_runner(body_id, stop_before={current_id}, stack=set())
                if isinstance(branch_result, dict) and isinstance(branch_result.get("graph_state"), dict):
                    _merge_runtime_state(
                        state,
                        branch_result.get("graph_state") or {},
                        base_log_count=int(branch_result.get("base_log_count") or 0),
                        base_notification_count=int(branch_result.get("base_notification_count") or 0),
                        base_node_keys={str(key) for key in branch_result.get("base_node_keys") or []},
                        base_form_keys={str(key) for key in branch_result.get("base_form_keys") or []},
                    )
                    branch_result = {
                        "last_result": deepcopy(branch_result.get("last_result") or {}),
                        "stopped_at": str(branch_result.get("stopped_at") or ""),
                    }
                runs.append(branch_result)
        result = {
            "ok": True,
            "loopType": loop_type,
            "iterations": len(runs),
            "runs": runs,
        }
        next_id = exit_id or None
    elif node_type == "subflow":
        subflow_id = str(node_data.get("subflowId") or "").strip()
        subflow_input = _safe_json_loads(_render_template(node_data.get("input") or "{}", context), {})
        subflow_result = await execute_tenant_workflow(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            workflow_id=subflow_id,
            input_payload=subflow_input if isinstance(subflow_input, dict) else {"value": subflow_input},
            max_depth=max_depth - 1,
        )
        result = {
            "ok": True,
            "subflow_id": subflow_id,
            "subflow_result": subflow_result,
        }
    elif node_type == "end":
        result = {
            "ok": True,
            "endType": str(node_data.get("endType") or "正常结束"),
            "message": str(_render_template(node_data.get("endMessage") or "", context)).strip(),
        }
        next_id = None
    else:
        result = {"ok": True, "msg": f"未识别节点类型 {node_type}，已跳过"}

    if next_id is None and node_type not in {"condition", "parallel", "loop", "end"}:
        next_candidates = [str(item.get("to") or "") for item in outgoing.get(current_id, []) if str(item.get("to") or "").strip()]
        next_id = next_candidates[0] if next_candidates else None
    return result, next_id


async def execute_tenant_workflow(
    *,
    tenant_id: str,
    tenant_name: str,
    workflow_id: str | None,
    input_payload: dict | None = None,
    max_depth: int = 3,
) -> dict:
    config = load_workflow_config(tenant_id=tenant_id, tenant_name=tenant_name)
    workflow_items = list(config.get("items") or [])
    target_id = str(workflow_id or config.get("default_workflow_id") or "").strip()
    workflow = next((item for item in workflow_items if item.get("workflow_id") == target_id), None)
    if workflow is None:
        raise WorkflowRuntimeError("未找到对应工作流")
    if not workflow.get("enabled", True):
        raise WorkflowRuntimeError("当前工作流未启用")
    if max_depth <= 0:
        raise WorkflowRuntimeError("子流程嵌套层级过深")

    app_settings = load_tenant_app_config(tenant_id, tenant_name)
    model_settings = load_model_config(tenant_id=tenant_id, tenant_name=tenant_name)
    retrieval_settings = load_retrieval_config(tenant_id=tenant_id, tenant_name=tenant_name)
    tool_settings = load_tool_config(tenant_id=tenant_id, tenant_name=tenant_name)
    rag_runtime = build_runtime_rag_engine(
        knowledge_dir=get_tenant_knowledge_dir(tenant_id),
        app_config=app_settings,
        retrieval_config=retrieval_settings,
    )
    system_prompt = load_tenant_system_prompt(tenant_id, tenant_name)
    nodes = list(workflow.get("nodes") or [])
    connections = list(workflow.get("connections") or [])
    node_map = {str(node.get("id") or ""): node for node in nodes}
    outgoing = _outgoing_map(connections)
    incoming = _incoming_map(connections)
    start_node = _find_start_node(nodes)
    logs: list[dict] = []
    runtime_state: WorkflowGraphState = {
        "input": deepcopy(input_payload or {}),
        "nodes": {},
        "last_result": {},
        "notifications": [],
        "forms": {},
        "workflow": {
            "id": workflow.get("workflow_id"),
            "name": workflow.get("name"),
        },
        "logs": logs,
        "next_node_id": "",
        "entry_node_id": str(start_node.get("id") or ""),
        "stop_before": [],
        "stopped_at": "",
    }

    async def run_path_legacy(node_id: str, *, stop_before: set[str] | None = None, stack: set[str] | None = None) -> dict:
        stop_before = stop_before or set()
        stack = stack or set()
        current_id = node_id
        last_result: dict = {}
        while current_id:
            if current_id in stop_before:
                return {"last_result": last_result, "stopped_at": current_id}
            if current_id in stack:
                raise WorkflowRuntimeError(f"检测到循环依赖: {current_id}")
            stack.add(current_id)
            node = node_map.get(current_id)
            if not node:
                raise WorkflowRuntimeError(f"节点不存在: {current_id}")
            started_at = time.time()
            result, next_id = await _execute_node_logic(
                current_id=current_id,
                node=node,
                state=runtime_state,
                node_map=node_map,
                outgoing=outgoing,
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                model_settings=model_settings,
                rag_runtime=rag_runtime,
                tool_settings=tool_settings,
                max_depth=max_depth,
                branch_runner=run_path_legacy,
            )
            node_type = str(node.get("type") or "").strip()
            finished_at = time.time()
            runtime_state["nodes"][current_id] = {
                "node_id": current_id,
                "type": node_type,
                "label": _node_label(node),
                "result": deepcopy(result),
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": int((finished_at - started_at) * 1000),
            }
            runtime_state["last_result"] = deepcopy(result)
            logs.append(
                {
                    "node_id": current_id,
                    "label": _node_label(node),
                    "type": node_type,
                    "result": deepcopy(result),
                    "duration_ms": int((finished_at - started_at) * 1000),
                }
            )
            last_result = result
            stack.remove(current_id)
            if not next_id:
                return {"last_result": last_result, "stopped_at": ""}
            current_id = next_id
        return {"last_result": last_result, "stopped_at": ""}

    async def _run_langgraph(initial_state: WorkflowGraphState) -> WorkflowGraphState:
        if not LANGGRAPH_AVAILABLE or StateGraph is None:
            raise WorkflowRuntimeError("LangGraph 不可用")
        graph = StateGraph(WorkflowGraphState)
        path_map = {node_id: node_id for node_id in node_map.keys()}
        path_map["__end__"] = END
        compiled = None

        async def run_path_langgraph(node_id: str, *, stop_before: set[str] | None = None, stack: set[str] | None = None) -> dict:
            if compiled is None:
                return await run_path_legacy(node_id, stop_before=stop_before, stack=stack)
            base_log_count = len(runtime_state["logs"])
            base_notification_count = len(runtime_state["notifications"])
            base_node_keys = set(runtime_state["nodes"].keys())
            base_form_keys = set(runtime_state["forms"].keys())
            branch_state = deepcopy(runtime_state)
            branch_state["entry_node_id"] = node_id
            branch_state["stop_before"] = sorted(stop_before or set())
            branch_state["stopped_at"] = ""
            branch_state["next_node_id"] = node_id
            final_branch_state = await compiled.ainvoke(branch_state)
            return {
                "last_result": deepcopy(final_branch_state.get("last_result") or {}),
                "stopped_at": str(final_branch_state.get("stopped_at") or ""),
                "graph_state": final_branch_state,
                "base_log_count": base_log_count,
                "base_notification_count": base_notification_count,
                "base_node_keys": sorted(base_node_keys),
                "base_form_keys": sorted(base_form_keys),
            }

        for workflow_node in nodes:
            node_id = str(workflow_node.get("id") or "")
            if not node_id:
                continue

            async def _node_runner(state: WorkflowGraphState, *, _node=workflow_node, _node_id=node_id):
                started_at = time.time()
                result, next_id = await _execute_node_logic(
                    current_id=_node_id,
                    node=_node,
                    state=state,
                    node_map=node_map,
                    outgoing=outgoing,
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    model_settings=model_settings,
                    rag_runtime=rag_runtime,
                    tool_settings=tool_settings,
                    max_depth=max_depth,
                    branch_runner=run_path_langgraph,
                )
                finished_at = time.time()
                node_type = str(_node.get("type") or "").strip()
                state["nodes"][_node_id] = {
                    "node_id": _node_id,
                    "type": node_type,
                    "label": _node_label(_node),
                    "result": deepcopy(result),
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "duration_ms": int((finished_at - started_at) * 1000),
                }
                state["last_result"] = deepcopy(result)
                state["logs"].append(
                    {
                        "node_id": _node_id,
                        "label": _node_label(_node),
                        "type": node_type,
                        "result": deepcopy(result),
                        "duration_ms": int((finished_at - started_at) * 1000),
                    }
                )
                stop_before = {str(item or "").strip() for item in state.get("stop_before") or [] if str(item or "").strip()}
                if next_id and next_id in stop_before:
                    state["stopped_at"] = str(next_id)
                    state["next_node_id"] = "__end__"
                else:
                    state["next_node_id"] = str(next_id or "__end__")
                return state

            def _route_next(state: WorkflowGraphState):
                target = str(state.get("next_node_id") or "__end__")
                return target if target in path_map else "__end__"

            graph.add_node(node_id, _node_runner)
            graph.add_conditional_edges(node_id, _route_next, path_map)

        def _route_entry(state: WorkflowGraphState):
            entry_id = str(state.get("entry_node_id") or start_node.get("id") or "__end__")
            return entry_id if entry_id in path_map else "__end__"

        graph.add_conditional_edges(START, _route_entry, path_map)
        compiled = graph.compile()
        return await compiled.ainvoke(initial_state)

    if LANGGRAPH_AVAILABLE and StateGraph is not None:
        final_state = await _run_langgraph(runtime_state)
        final_result = final_state.get("last_result") or {}
        orchestration_backend = "langgraph"
    else:
        final = await run_path_legacy(str(start_node.get("id") or ""))
        final_result = final.get("last_result") or {}
        orchestration_backend = "legacy"
    return {
        "ok": True,
        "workflow_id": workflow.get("workflow_id"),
        "workflow_name": workflow.get("name"),
        "default_prompt": system_prompt,
        "logs": logs,
        "state": runtime_state,
        "final_result": final_result,
        "node_count": len(nodes),
        "connection_count": len(connections),
        "entry_node_id": start_node.get("id"),
        "default_workflow_id": config.get("default_workflow_id"),
        "incoming_count": {key: len(value) for key, value in incoming.items()},
        "orchestration_backend": orchestration_backend,
    }
