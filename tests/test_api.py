from io import BytesIO
import time
from PIL import Image
from fastapi.testclient import TestClient
from pixel_avatar.api import create_app
from test_pipeline import FixtureProvider


def test_private_api_lifecycle(tmp_path):
    token='test-only-secret-token'
    app=create_app(tmp_path,token,FixtureProvider)
    headers={'Authorization':'Bearer '+token}
    raw=BytesIO();Image.new('RGB',(100,120),(130,90,70)).save(raw,format='PNG')
    with TestClient(app) as client:
        assert client.get('/health').status_code==200
        assert client.get('/').status_code==200
        assert client.post('/v1/avatars').status_code==401
        result=client.post('/v1/avatars',headers=headers,files={'photos':('test.png',raw.getvalue(),'image/png')})
        assert result.status_code==201,result.text
        jid=result.json()['id'];url=f'/v1/avatars/{jid}'
        assert client.get(url).status_code==401
        assert client.get(url+'/files/job.json',headers=headers).status_code==404
        assert client.post(url+'/run',headers=headers).status_code==202
        for _ in range(200):
            status=client.get(url,headers=headers).json()
            if not status['active']:break
            time.sleep(.02)
        assert status['status']=='needs_review',status
        assert client.get(url+'/files/base.png',headers=headers).status_code==200
        assert client.post(url+'/run',headers=headers).status_code==409
        assert client.post(url+'/approve',headers=headers,json={'stage':'base','note':'Checked test fixture'}).status_code==200
        assert client.get('/v1/avatars/invalid-id',headers=headers).status_code==404
        bad=client.post('/v1/avatars',headers=headers,files={'photos':('bad.png',b'not an image','image/png')})
        assert bad.status_code==422
