"""Real mask decoding plus bounded, failure-aware image segmentation."""
import base64
import io
import json
import struct
import zlib
from pathlib import Path

import pytest
from integrations.meta import sam
from integrations.meta.spark import ModelError

ROOT = Path(__file__).resolve().parents[1]
# Our own 2x2 binary raster, encoded once by the official Meta encoder.
MASK = '!!!!!&T:u9`'
RECORD = '<0f>7<|box;x1=0;y1=0;x2=1;y2=1;w=2;h=2;c=0.9|><|mask;x=0;y=0;data=2,2,' + MASK + '|>'
IMAGE = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()


def test_official_decoder_and_png_preserve_actual_alpha():
    parsed = sam.parse_output_text(RECORD, decode_masks=True)
    mask = parsed['frames'][0]['records'][0]['mask']
    assert mask['decoded'] is True and (mask['width'], mask['height']) == (2, 2)
    png = base64.b64decode(mask['png_data_url'].split(',')[1])
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    offset, chunks = 8, {}
    while offset < len(png):
        size = struct.unpack('>I', png[offset:offset+4])[0]
        kind, data = png[offset+4:offset+8], png[offset+8:offset+8+size]
        assert zlib.crc32(kind + data) & 0xffffffff == struct.unpack('>I', png[offset+8+size:offset+12+size])[0]
        chunks[kind] = data
        offset += size + 12
    assert struct.unpack('>IIBBBBB', chunks[b'IHDR']) == (2, 2, 8, 4, 0, 0, 0)
    assert zlib.decompress(chunks[b'IDAT']) == b'\0\xff\xff\xff\0\0\xff\0\xff\xff'
    assert parsed['objects'] == [7] and not parsed['diagnostics']


@pytest.mark.parametrize('replacement', ['2,2,!bad', '-2,-2,'+MASK, '100000,100000,'+MASK, '2,2,?bad'])
def test_undecodable_masks_are_explicit_not_fabricated(replacement):
    out = sam.parse_output_text(RECORD.replace('2,2,'+MASK, replacement), decode_masks=True)
    assert out['frames'][0]['records'][0]['mask']['decoded'] is False
    assert out['diagnostics'][0]['code'] == 'mask_not_decoded'


def test_invalid_box_and_decode_budgets(monkeypatch):
    out = sam.parse_output_text(RECORD.replace('x1=0', 'x1=3'), decode_masks=True)
    assert not out['objects'] and out['diagnostics'][0]['code'] == 'malformed_record'
    with pytest.raises(ValueError, match='budget'): sam.parse_output_text('x' * (8*1024*1024+1))
    with pytest.raises(ValueError): sam._mask_png(b'\2', 1, 1)
    calls = []
    monkeypatch.setattr(sam, '_decode_complete_mask', lambda payload,w,h: calls.append((w,h)) or b'\0'*(w*h))
    many = '\n'.join(RECORD.replace('<0f>', f'<{i}f>').replace('2,2,'+MASK, '1000,1000,'+MASK) for i in range(5))
    out = sam.parse_output_text(many, decode_masks=True)
    assert len(calls) == 4 and out['diagnostics'][-1]['code'] == 'mask_not_decoded'


class Stream(io.BytesIO):
    status = 200


def stream(monkeypatch, events):
    body = b''.join(('data: '+json.dumps(event)+'\n\n').encode() for event in events)
    monkeypatch.setenv('MODEL_API_KEY', 'local-test-fixture')
    monkeypatch.setattr(sam.urllib.request, 'urlopen', lambda request,timeout: Stream(body))


def test_stream_completion_required_and_zero_matches_valid(monkeypatch):
    stream(monkeypatch, [{'type': 'response.completed'}])
    assert sam.segment_image(IMAGE, 'robot')['objects'] == []
    stream(monkeypatch, [{'type': 'response.output_text.delta', 'delta': RECORD}])
    with pytest.raises(ModelError, match='without completion'): sam.segment_image(IMAGE, 'robot')
    stream(monkeypatch, [{'type': 'response.output_text.delta', 'delta': RECORD}, {'type': 'response.completed'}])
    assert sam.segment_image(IMAGE, 'robot')['frames'][0]['records'][0]['mask']['decoded']


@pytest.mark.parametrize('failure', ['response.failed', 'response.incomplete', 'error'])
def test_provider_failure_is_not_reported_as_zero_matches(monkeypatch, failure):
    stream(monkeypatch, [{'type': failure}])
    with pytest.raises(ModelError, match='did not complete'): sam.segment_image(IMAGE, 'robot')


def test_inputs_rejected_before_provider_call(monkeypatch):
    monkeypatch.setenv('MODEL_API_KEY', 'local-test-fixture')
    monkeypatch.setattr(sam.urllib.request, 'urlopen', lambda *args,**kwargs: pytest.fail('Unexpected external request'))
    for image, concept in [(IMAGE, ''), (IMAGE, 4), (IMAGE, 'a,b'), ('https://example.com/x.png', 'robot'),
                           (IMAGE.replace('image/png', 'image/jpeg'), 'robot'), ('data:image/png;base64,####', 'robot')]:
        with pytest.raises(ValueError): sam.segment_image(image, concept)


def test_gallery_photos_have_integrity_and_visible_attribution():
    import hashlib
    rows = json.loads((ROOT/'apps/web/sam-gallery.json').read_text())
    assert len(rows) == 3 and len({row['id'] for row in rows}) == 3
    for row in rows:
        image = ROOT/'apps/web'/row['src'].lstrip('/')
        assert image.stat().st_size > 20_000
        assert hashlib.sha256(image.read_bytes()).hexdigest() == row['sha256']
        assert row['author'] and row['photo_url'].startswith('https://unsplash.com/photos/')
    html = (ROOT/'apps/web/index.html').read_text()
    assert 'sam-photo-credit' in html and 'sam-previous' in html and 'sam-next' in html


def test_new_assets_served_with_correct_types_and_traversal_denied():
    import threading
    import urllib.request
    import urllib.error
    from http.server import ThreadingHTTPServer
    from services.api.server import H
    server = ThreadingHTTPServer(('127.0.0.1',0),H)
    thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        for path, content_type in [('/image-scene.mjs','text/javascript'),('/sam-gallery.json','application/json'),
                                  ('/mobile-nav.js','text/javascript'),('/api/index?ep=scenerycore','text/javascript'),
                                  ('/api/index?ep=asset&file=sam-gallery/warehouse.jpg','image/jpeg')]:
            with urllib.request.urlopen(base+path) as response:
                assert response.status == 200 and response.headers['Content-Type'] == content_type
                assert len(response.read()) > 10
        with pytest.raises(urllib.error.HTTPError) as failed:
            urllib.request.urlopen(base+'/api/index?ep=asset&file=../../../../pyproject.toml')
        assert failed.value.code == 404
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
