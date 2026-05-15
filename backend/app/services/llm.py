"""LLM gateway. Defaults to local Ollama via its OpenAI-compatible API."""
import asyncio
from functools import lru_cache
from typing import AsyncIterator

from app.core.config import settings


SYSTEM_PROMPT_DEFAULT = (
    "你是智能客服。基于下方知识片段简洁作答；"
    "若片段无法回答则说'抱歉，建议联系人工客服'，不要编造。"
)


def build_messages(question: str, contexts: list[str], system_prompt: str | None = None,
                   history: list[dict] | None = None) -> list[dict]:
    sp = system_prompt or SYSTEM_PROMPT_DEFAULT
    if contexts:
        ctx_text = "\n\n".join(f"【片段{i+1}】{c}" for i, c in enumerate(contexts))
        sp = f"{sp}\n\n=== 知识片段 ===\n{ctx_text}\n=== 知识片段结束 ==="
    msgs = [{"role": "system", "content": sp}]
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": question})
    return msgs


async def chat(messages: list[dict], model: str | None = None,
               temperature: float | None = None, max_tokens: int | None = None) -> str:
    """Sync wrapper for the configured LLM provider; runs in a thread."""
    return await asyncio.to_thread(
        _chat_sync,
        messages,
        model or settings.LLM_MODEL,
        temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_tokens or settings.LLM_MAX_TOKENS,
    )


def _chat_sync(messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
    """Routes to OpenAI-compatible endpoints, or DashScope native if no base URL is set."""
    base = _llm_base_url()
    if base:
        return _chat_openai_compat(messages, model, temperature, max_tokens, base)
    return _chat_dashscope_native(messages, model, temperature, max_tokens, base)


def _chat_dashscope_native(messages, model, temperature, max_tokens, base):
    import dashscope
    from dashscope import Generation

    dashscope.api_key = settings.DASHSCOPE_API_KEY
    if base:
        dashscope.base_http_api_url = base.rstrip("/")
    kw = dict(
        model=model, messages=messages, result_format="message",
        temperature=temperature, max_tokens=max_tokens,
    )
    if settings.LLM_DISABLE_THINKING:
        kw["enable_thinking"] = False
    resp = Generation.call(**kw)
    if getattr(resp, "status_code", 200) != 200:
        raise RuntimeError(f"LLM error: {resp.code} {resp.message}")
    try:
        return resp.output.choices[0].message.content
    except Exception:
        return str(resp.output)


@lru_cache
def _openai_client(base: str):
    from openai import OpenAI
    b = base.rstrip("/")
    if b.endswith("/chat/completions"):
        b = b[: -len("/chat/completions")]
    return OpenAI(api_key=_llm_api_key(), base_url=b)


def _chat_openai_compat(messages, model, temperature, max_tokens, base):
    """OpenAI-compatible mode (works for Ollama, DashScope compatible-mode, DeepSeek, etc.)."""
    client = _openai_client(base)
    extra_body = _extra_body(base)
    resp = client.chat.completions.create(
        model=model, messages=messages,
        temperature=temperature, max_tokens=max_tokens,
        extra_body=extra_body or None,
    )
    return resp.choices[0].message.content or ""


def _llm_base_url() -> str:
    return (settings.LLM_BASE_URL or settings.DASHSCOPE_BASE_URL or "").strip()


def _llm_api_key() -> str:
    return (settings.LLM_API_KEY or settings.DASHSCOPE_API_KEY or "ollama").strip()


def _extra_body(base: str) -> dict:
    if settings.LLM_DISABLE_THINKING and _is_dashscope_compatible(base):
        return {"enable_thinking": False}
    return {}


def _is_dashscope_compatible(base: str) -> bool:
    normalized = base.lower()
    return "dashscope" in normalized or "compatible-mode" in normalized


# ---------------- streaming ----------------

async def chat_stream(messages: list[dict], model: str | None = None,
                      temperature: float | None = None,
                      max_tokens: int | None = None) -> AsyncIterator[str]:
    """Async generator yielding text deltas as they arrive."""
    model = model or settings.LLM_MODEL
    temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
    max_tokens = max_tokens or settings.LLM_MAX_TOKENS
    base = _llm_base_url()

    queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()
    loop = asyncio.get_running_loop()

    def _producer():
        try:
            if base:
                client = _openai_client(base)
                extra_body = _extra_body(base)
                stream = client.chat.completions.create(
                    model=model, messages=messages,
                    temperature=temperature, max_tokens=max_tokens, stream=True,
                    extra_body=extra_body or None,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        loop.call_soon_threadsafe(queue.put_nowait, delta)
            else:
                import dashscope
                from dashscope import Generation
                dashscope.api_key = settings.DASHSCOPE_API_KEY
                if base:
                    dashscope.base_http_api_url = base.rstrip("/")
                kw = dict(
                    model=model, messages=messages, result_format="message",
                    temperature=temperature, max_tokens=max_tokens,
                    stream=True, incremental_output=True,
                )
                if settings.LLM_DISABLE_THINKING:
                    kw["enable_thinking"] = False
                responses = Generation.call(**kw)
                for r in responses:
                    if getattr(r, "status_code", 200) != 200:
                        loop.call_soon_threadsafe(queue.put_nowait,
                            f"\n[LLM error: {r.code} {r.message}]")
                        break
                    try:
                        delta = r.output.choices[0].message.content or ""
                    except Exception:
                        delta = ""
                    if delta:
                        loop.call_soon_threadsafe(queue.put_nowait, delta)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, f"\n[stream error: {e}]")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

    asyncio.get_running_loop().run_in_executor(None, _producer)
    while True:
        item = await queue.get()
        if item is SENTINEL:
            break
        yield item
