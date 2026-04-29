"""Welcome-message C4 diagram builder.

Generates a Mermaid C4Context diagram from just the welcome message text —
no chunk retrieval needed. Called after the wiki step during indexing.
"""

from __future__ import annotations

import logging

from langchain_core.output_parsers import StrOutputParser

from .llm_instrument import traced_llm_call
from .prompts.c4 import C4_PROMPT

logger = logging.getLogger(__name__)

_MAX_WELCOME_CHARS = 8_000  # welcome messages are rarely longer than this
_MAX_OUTPUT_CHARS = 4_000   # C4 diagram is compact


def build_welcome_c4(
    *,
    conversation_id: str,
    welcome_message: str,
) -> str | None:
    """Return a mermaid C4Context string (with ``` fences) from the welcome message.

    Returns None on failure — callers should treat this as best-effort.
    """
    if not welcome_message.strip():
        return None

    clipped = welcome_message[:_MAX_WELCOME_CHARS]

    from .rag import get_llm  # local import — avoids circular at module load

    llm = get_llm()
    chain = C4_PROMPT | llm | StrOutputParser()
    model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"

    logger.info("🧩 C4: building (conv=%s)", conversation_id)

    try:
        result, _usage = traced_llm_call(
            chain=chain,
            params={"welcome_message": clipped},
            operation="build_welcome_c4",
            model=model,
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning("🧩 C4 generation failed (conv=%s): %s", conversation_id, exc)
        return None

    result = (result or "").strip()
    if not result:
        logger.info("🧩 C4 generation produced empty output (conv=%s)", conversation_id)
        return None

    if len(result) > _MAX_OUTPUT_CHARS:
        result = result[:_MAX_OUTPUT_CHARS]

    return result

