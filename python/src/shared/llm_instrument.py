"""LLM call instrumentation: OTel spans + metrics + prompt history logging.

Provides `traced_llm_call()` — a wrapper that adds distributed tracing,
operation counters, latency histograms, and prompt history DB logging
around any LangChain chain invocation or direct OpenAI call.
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

import sentry_sdk
from opentelemetry import trace

from .otel import get_meter, get_tracer
from .prompt_history import log_prompt

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _sentry_llm_span(operation: str, model: str, conversation_id: str | None, prompt_len: int):
    """Open a Sentry child span around an LLM call so it appears in the trace
    waterfall. Hard failures in Sentry must not break the LLM path, so we
    swallow any errors from the SDK itself.
    """
    span_cm = None
    span = None
    try:
        span_cm = sentry_sdk.start_span(op="ai.openai", name=f"llm.{operation}")
        span = span_cm.__enter__()
        span.set_data("llm.operation", operation)
        span.set_data("llm.model", model)
        span.set_data("llm.prompt_chars", prompt_len)
        if conversation_id:
            span.set_data("llm.conversation_id", conversation_id)
        sentry_sdk.add_breadcrumb(
            category="llm",
            level="info",
            message=f"{operation} → {model}",
            data={"prompt_chars": prompt_len, "conversation_id": conversation_id},
        )
    except Exception:
        span_cm = None
        span = None

    try:
        yield span
    finally:
        if span_cm is not None:
            with contextlib.suppress(Exception):
                span_cm.__exit__(None, None, None)

# ── OTel metrics (lazy-init on first use) ─────────────────────────────────────
_meter = None
_llm_call_counter = None
_llm_latency_histogram = None
_llm_token_counter = None
_llm_prompt_size_histogram = None
_llm_error_counter = None


def _ensure_metrics():
    global _meter, _llm_call_counter, _llm_latency_histogram, _llm_token_counter
    global _llm_prompt_size_histogram, _llm_error_counter
    if _meter is not None:
        return
    _meter = get_meter("chatrag.llm")
    _llm_call_counter = _meter.create_counter(
        "llm.calls",
        description="Number of LLM invocations",
        unit="1",
    )
    _llm_latency_histogram = _meter.create_histogram(
        "llm.latency",
        description="LLM call latency",
        unit="ms",
    )
    _llm_token_counter = _meter.create_counter(
        "llm.tokens",
        description="Total tokens consumed by LLM calls",
        unit="1",
    )
    _llm_prompt_size_histogram = _meter.create_histogram(
        "llm.prompt_size",
        description="Size of prompts sent to LLM",
        unit="chars",
    )
    _llm_error_counter = _meter.create_counter(
        "llm.errors",
        description="Number of failed LLM calls",
        unit="1",
    )


def traced_llm_call(
    *,
    chain: Any,
    params: dict,
    operation: str,
    model: str,
    conversation_id: str | None = None,
    rendered_prompt: str | None = None,
) -> tuple[str, dict]:
    """Invoke a LangChain chain with full OTel tracing, metrics, and prompt logging.

    Returns (response_text, usage_metadata) where usage_metadata contains
    token counts extracted from the LLM response.
    """
    _ensure_metrics()
    tracer = get_tracer("chatrag.llm")

    prompt_text = rendered_prompt or str(params)
    prompt_len = len(prompt_text)

    attributes = {
        "llm.operation": operation,
        "llm.model": model,
        "llm.prompt_chars": prompt_len,
    }
    if conversation_id:
        attributes["llm.conversation_id"] = conversation_id

    _llm_prompt_size_histogram.record(prompt_len, {"operation": operation, "model": model})

    with _sentry_llm_span(operation, model, conversation_id, prompt_len) as sentry_span, \
        tracer.start_as_current_span(
            f"llm.{operation}",
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
        ) as span:
        logger.info(f"▶️  [LLM] {operation} | model={model} | starting (prompt={prompt_len} chars)")
        start = time.monotonic()
        try:
            result = chain.invoke(params)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            # Extract response text and usage from LangChain AIMessage or plain string
            if hasattr(result, "content"):
                response_text = result.content
                response_metadata = getattr(result, "response_metadata", {})
            else:
                response_text = str(result)
                response_metadata = {}

            # Extract token usage
            usage = (
                response_metadata.get("token_usage")
                or response_metadata.get("usage")
                or {}
            )
            prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
            completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
            cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)

            # Set span attributes
            span.set_attribute("llm.duration_ms", elapsed_ms)
            span.set_attribute("llm.prompt_tokens", prompt_tokens)
            span.set_attribute("llm.completion_tokens", completion_tokens)
            span.set_attribute("llm.total_tokens", total_tokens)
            span.set_attribute("llm.cached_tokens", cached_tokens)
            span.set_attribute("llm.response_chars", len(response_text))
            span.set_status(trace.StatusCode.OK)

            if sentry_span is not None:
                sentry_span.set_data("llm.duration_ms", elapsed_ms)
                sentry_span.set_data("llm.total_tokens", total_tokens)
                sentry_span.set_data("llm.response_chars", len(response_text))
                sentry_span.set_status("ok")

            # Record metrics
            _llm_call_counter.add(1, {"operation": operation, "model": model, "status": "ok"})
            _llm_latency_histogram.record(elapsed_ms, {"operation": operation, "model": model})
            if total_tokens:
                _llm_token_counter.add(
                    total_tokens,
                    {"operation": operation, "model": model, "type": "total"},
                )
            if prompt_tokens:
                _llm_token_counter.add(
                    prompt_tokens,
                    {"operation": operation, "model": model, "type": "prompt"},
                )
            if completion_tokens:
                _llm_token_counter.add(
                    completion_tokens,
                    {"operation": operation, "model": model, "type": "completion"},
                )

            # Log to prompt_history DB table
            log_prompt(
                conversation_id=conversation_id,
                operation=operation,
                model=model,
                prompt_text=prompt_text,
                response_text=response_text,
                prompt_tokens=prompt_tokens or None,
                completion_tokens=completion_tokens or None,
                total_tokens=total_tokens or None,
                cached_tokens=cached_tokens or None,
                duration_ms=elapsed_ms,
            )

            logger.info(
                f"📊 [LLM] {operation} | model={model} | {elapsed_ms}ms | "
                f"tokens: {prompt_tokens}+{completion_tokens}={total_tokens} "
                f"(cached={cached_tokens}) | prompt={prompt_len} chars"
            )

            usage_meta = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cached_tokens": cached_tokens,
                "duration_ms": elapsed_ms,
            }
            return response_text, usage_meta

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            span.set_attribute("llm.duration_ms", elapsed_ms)

            if sentry_span is not None:
                sentry_span.set_data("llm.duration_ms", elapsed_ms)
                sentry_span.set_status("internal_error")

            _llm_call_counter.add(1, {"operation": operation, "model": model, "status": "error"})
            _llm_error_counter.add(1, {"operation": operation, "model": model})
            _llm_latency_histogram.record(elapsed_ms, {"operation": operation, "model": model})

            # Still log failed prompts for debugging
            log_prompt(
                conversation_id=conversation_id,
                operation=operation,
                model=model,
                prompt_text=prompt_text,
                response_text=f"ERROR: {str(exc)[:1000]}",
                duration_ms=elapsed_ms,
            )

            logger.error(
                f"❌ [LLM] {operation} | model={model} | {elapsed_ms}ms | ERROR: {exc}"
            )
            raise


def traced_openai_call(
    *,
    client: Any,
    messages: list[dict],
    model: str,
    operation: str,
    conversation_id: str | None = None,
    max_completion_tokens: int | None = None,
    **kwargs: Any,
) -> tuple[str, dict]:
    """Wrap a direct OpenAI client.chat.completions.create() call with tracing.

    Returns (response_text, usage_metadata).
    """
    _ensure_metrics()
    tracer = get_tracer("chatrag.llm")

    prompt_text = "\n\n---MSG---\n\n".join(
        f"[{m.get('role', '?')}]\n{m.get('content', '')}"
        for m in messages
        if isinstance(m.get("content"), str)
    )
    prompt_len = len(prompt_text)

    attributes = {
        "llm.operation": operation,
        "llm.model": model,
        "llm.prompt_chars": prompt_len,
    }
    if conversation_id:
        attributes["llm.conversation_id"] = conversation_id

    _llm_prompt_size_histogram.record(prompt_len, {"operation": operation, "model": model})

    with _sentry_llm_span(operation, model, conversation_id, prompt_len) as sentry_span, \
        tracer.start_as_current_span(
            f"llm.{operation}",
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
        ) as span:
        logger.info(f"▶️  [LLM] {operation} | model={model} | starting (prompt={prompt_len} chars)")
        start = time.monotonic()
        try:
            create_kwargs = {"model": model, "messages": messages, **kwargs}
            if max_completion_tokens is not None:
                create_kwargs["max_completion_tokens"] = max_completion_tokens
            resp = client.chat.completions.create(**create_kwargs)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            response_text = resp.choices[0].message.content or ""
            usage = resp.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            total_tokens = usage.total_tokens if usage else 0
            cached_tokens = 0
            if usage and hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
                cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0

            span.set_attribute("llm.duration_ms", elapsed_ms)
            span.set_attribute("llm.prompt_tokens", prompt_tokens)
            span.set_attribute("llm.completion_tokens", completion_tokens)
            span.set_attribute("llm.total_tokens", total_tokens)
            span.set_attribute("llm.cached_tokens", cached_tokens)
            span.set_attribute("llm.response_chars", len(response_text))
            span.set_status(trace.StatusCode.OK)

            if sentry_span is not None:
                sentry_span.set_data("llm.duration_ms", elapsed_ms)
                sentry_span.set_data("llm.total_tokens", total_tokens)
                sentry_span.set_data("llm.response_chars", len(response_text))
                sentry_span.set_status("ok")

            _llm_call_counter.add(1, {"operation": operation, "model": model, "status": "ok"})
            _llm_latency_histogram.record(elapsed_ms, {"operation": operation, "model": model})
            if total_tokens:
                _llm_token_counter.add(
                    total_tokens, {"operation": operation, "model": model, "type": "total"}
                )

            log_prompt(
                conversation_id=conversation_id,
                operation=operation,
                model=model,
                prompt_text=prompt_text,
                response_text=response_text,
                prompt_tokens=prompt_tokens or None,
                completion_tokens=completion_tokens or None,
                total_tokens=total_tokens or None,
                cached_tokens=cached_tokens or None,
                duration_ms=elapsed_ms,
            )

            logger.info(
                f"📊 [LLM] {operation} | model={model} | {elapsed_ms}ms | "
                f"tokens: {prompt_tokens}+{completion_tokens}={total_tokens}"
            )

            return response_text, {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cached_tokens": cached_tokens,
                "duration_ms": elapsed_ms,
            }

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            span.record_exception(exc)

            if sentry_span is not None:
                sentry_span.set_data("llm.duration_ms", elapsed_ms)
                sentry_span.set_status("internal_error")

            _llm_call_counter.add(1, {"operation": operation, "model": model, "status": "error"})
            _llm_error_counter.add(1, {"operation": operation, "model": model})
            _llm_latency_histogram.record(elapsed_ms, {"operation": operation, "model": model})

            log_prompt(
                conversation_id=conversation_id,
                operation=operation,
                model=model,
                prompt_text=prompt_text,
                response_text=f"ERROR: {str(exc)[:1000]}",
                duration_ms=elapsed_ms,
            )

            logger.error(f"❌ [LLM] {operation} | model={model} | {elapsed_ms}ms | ERROR: {exc}")
            raise
