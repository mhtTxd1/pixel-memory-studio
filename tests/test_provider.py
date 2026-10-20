import base64
from io import BytesIO
from types import SimpleNamespace
from PIL import Image
from pixel_avatar.provider import OpenAIProvider


def test_image_edit_contract_without_network(tmp_path,monkeypatch):
    import openai
    buf=BytesIO();Image.new('RGB',(20,20),'white').save(buf,format='PNG')
    ref=tmp_path/'reference.png';ref.write_bytes(buf.getvalue())
    calls=[]
    def edit(**kwargs):
        calls.append(kwargs)
        assert kwargs['image'][0].read()==buf.getvalue()
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(buf.getvalue()).decode())])
    def client(**kwargs):
        assert kwargs['max_retries']==0
        return SimpleNamespace(images=SimpleNamespace(edit=edit))
    monkeypatch.setenv('OPENAI_API_KEY','fake-test-key')
    monkeypatch.setattr(openai,'OpenAI',client)
    image=OpenAIProvider().generate('test',[ref],'base')
    assert image.size==(20,20)
    assert calls[0]['size']=='1024x1024'
    assert calls[0]['image'][0].closed


def test_text_only_background_uses_generate(monkeypatch):
    import openai
    buf=BytesIO();Image.new('RGB',(20,20),'white').save(buf,format='PNG')
    calls=[]
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(buf.getvalue()).decode())])
    monkeypatch.setenv('OPENAI_API_KEY','fake-test-key')
    monkeypatch.setattr(openai,'OpenAI',lambda **kwargs:SimpleNamespace(images=SimpleNamespace(generate=generate)))
    OpenAIProvider().generate('scene',[],'scene-portrait')
    assert calls[0]['size']=='1024x1536'
    assert 'image' not in calls[0]
