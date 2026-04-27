import asyncio
from pathlib import Path

from src import server


def test_generate_image_endpoint_passes_requested_size(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        server,
        'build_image_prompt',
        lambda **_kwargs: {
            'prompt': 'prompt from llm',
            'title': 'Image title',
            'source_indices': [],
        },
    )

    def fake_generate_image(**kwargs):
        captured['size'] = kwargs.get('size')
        file_name = 'generated-test.jpg'
        (tmp_path / file_name).write_bytes(b'test')
        return {'file_name': file_name}

    monkeypatch.setattr(server, 'generate_image', fake_generate_image)

    req = server.GenerateImageRequest(
        question='generate inspired image 🎨',
        storage_dir=str(tmp_path),
        size='1024x1536',
    )

    result = asyncio.run(server.generate_image_endpoint(req))

    assert captured['size'] == '1024x1536'
    assert result['file_name'] == 'generated-test.jpg'
