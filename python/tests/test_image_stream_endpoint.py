import asyncio
import json
from pathlib import Path

import pytest

from src import server


@pytest.mark.asyncio
async def test_stream_endpoint_skips_pdf_auto_refs_without_explicit_selection(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / 'cv.pdf'
    pdf_path.write_bytes(b'%PDF-1.4 test')

    captured: dict[str, object] = {'reference_image_paths': None}

    monkeypatch.setattr(
        server,
        'build_image_prompt',
        lambda **_kwargs: {
            'prompt': 'prompt from llm',
            'title': 'Image title',
            'source_indices': [],
        },
    )

    monkeypatch.setattr(
        server,
        '_discover_uploaded_reference_files',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError('stream endpoint should not auto-discover PDF references')
        ),
    )

    def fake_streaming(**kwargs):
        captured['reference_image_paths'] = kwargs.get('reference_image_paths')
        yield {'type': 'partial', 'b64': 'ZmFrZQ==', 'index': 0}
        yield {'type': 'completed', 'file_name': 'generated-test.png'}

    monkeypatch.setattr(server, 'generate_image_streaming', fake_streaming)

    req = server.GenerateImageRequest(
        question='generate inspired image 🎨',
        storage_dir=str(tmp_path),
    )

    response = await server.generate_image_stream_endpoint(req)

    emitted: list[str] = []

    async for chunk in response.body_iterator:
        emitted.append(chunk if isinstance(chunk, str) else chunk.decode())

    payloads = [json.loads(line) for line in emitted if line.strip()]
    assert payloads[0]['event'] == 'prompt_ready'
    assert payloads[1]['event'] == 'partial'
    assert payloads[-1]['event'] == 'complete'
    assert captured['reference_image_paths'] is None
