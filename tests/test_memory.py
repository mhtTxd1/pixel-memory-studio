import json
import subprocess
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from pixel_avatar.scenes import create_scene, run_scene, retry_scene
from pixel_avatar.movie import create_movie,render_movie,MovieOptions,Cue,frame_for
from pixel_avatar.pipeline import load,save,write_json
from pixel_avatar.spec import manifest,COUNTS
from pixel_avatar.api import create_app


class SceneFixture:
    def __init__(self):self.calls=[]
    def generate(self,prompt,refs,stage):
        self.calls.append((prompt,refs,stage))
        # Geometric test fixture, NOT a generated background or a visual-quality example.
        im=Image.new('RGB',(640,360),(190,215,200));d=ImageDraw.Draw(im)
        d.rectangle((0,280,640,360),fill=(130,150,110))
        return im


def make_avatar(root,name='test-actor'):
    folder=root/name;(folder/'output').mkdir(parents=True)
    im=Image.new('RGBA',(1536,2288));draw=ImageDraw.Draw(im)
    for row,count in enumerate(COUNTS):
        for col in range(count):
            dy=-20 if row==4 and col==2 else 0
            draw.rectangle((col*192+65,row*208+40+dy,col*192+125,row*208+190+dy),fill=(180+col*6,90,100,255))
    im.save(folder/'output/spritesheet.png')
    write_json(folder/'output/avatar.json',manifest('test',2))
    save(folder,{'status':'ready','stages':{'base':{'status':'approved'}}})
    (folder/'processed').mkdir()
    im.crop((0,0,192,208)).save(folder/'processed/base.png')
    return folder


def test_scene_sources_resume_and_retry(tmp_path):
    provider=SceneFixture()
    folder=create_scene(tmp_path/'scenes','A quiet park')
    result=run_scene(folder,provider);assert result['status']=='ready'
    assert provider.calls[0][1]==[]
    assert provider.calls[0][2]=='scene-landscape'
    run_scene(folder,provider);assert len(provider.calls)==1
    with Image.open(folder/'background.png') as bg:assert bg.size==(1280,720)
    retry_scene(folder,'Same park at night')
    assert not (folder/'background.png').exists()
    run_scene(folder,provider);assert len(provider.calls)==2
    avatar=make_avatar(tmp_path)
    photo=tmp_path/'scene-photo.png';Image.new('RGB',(200,100),'green').save(photo)
    portrait=create_scene(tmp_path/'scenes','',photo,avatar,'portrait',4)
    run_scene(portrait,provider)
    assert len(provider.calls[-1][1])==2
    assert provider.calls[-1][2]=='scene-portrait'
    assert 'ONLY an avatar style reference' in provider.calls[-1][0]
    with Image.open(portrait/'background.png') as bg:assert bg.size==(720,1280)
    with pytest.raises(ValueError):create_scene(tmp_path/'scenes')


def test_eight_second_video_and_snapshot(tmp_path):
    import imageio_ffmpeg
    scene=create_scene(tmp_path/'scenes','A park');run_scene(scene,SceneFixture())
    a=make_avatar(tmp_path,'a');b=make_avatar(tmp_path,'b')
    movie=create_movie(tmp_path/'movies',scene,[a,b],{'caption':'Our little memory','preset':'meet'})
    # Invalidate live source after creation: recording snapshots must remain usable.
    retry_scene(scene,'Night park')
    result=render_movie(movie)
    assert result['frames']==192 and result['status']=='ready'
    assert (movie/'memory.mp4').stat().st_size>1000
    assert (movie/'poster.png').exists()
    reader=imageio_ffmpeg.read_frames(str(movie/'memory.mp4'),pix_fmt='rgb24')
    meta=next(reader)
    assert meta['size']==(1280,720)
    assert abs(meta['duration']-8)<.1 and meta['fps']==24
    first=next(reader);different=False;count=1
    for index,frame in enumerate(reader,1):
        if index==60:different=frame!=first
        count+=1
    assert count==192 and different
    # Decode via the actual FFmpeg binary: catches broken encodes/truncated trailers.
    process=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(movie/'memory.mp4'),'-f','null','-'],capture_output=True)
    assert process.returncode==0,process.stderr


def test_timeline_validation_and_gaze():
    with pytest.raises(ValueError):MovieOptions(duration=100)
    with pytest.raises(ValueError):MovieOptions(tracks=[[Cue(start=0,end=5),Cue(start=4,end=6)]])
    with pytest.raises(ValueError):Cue(start=float('nan'),end=3)
    m=manifest('test',2)
    assert frame_for(m,Cue(start=0,end=8,gaze=12),1)==(10,4)
    assert frame_for(m,Cue(start=0,end=8,action='idle'),.3)==(0,1)


def test_scene_api_and_security(tmp_path):
    import time
    import uuid
    with TestClient(create_app(tmp_path,'test-only-secret-token',SceneFixture)) as client:
        headers={'Authorization':'Bearer test-only-secret-token'}
        assert client.get('/memory').status_code==200
        assert client.post('/v1/scenes',data={'description':'park'}).status_code==401
        response=client.post('/v1/scenes',headers=headers,data={'description':'park'})
        assert response.status_code==201,response.text
        jid=response.json()['id'];url='/v1/scenes/'+jid
        assert client.post(url+'/run',headers=headers).status_code==202
        for _ in range(200):
            state=client.get(url,headers=headers).json()
            if not state['active']:break
            time.sleep(.02)
        assert state['status']=='ready',state
        assert client.get(url+'/files/background.png',headers=headers).status_code==200
        assert client.get(url+'/files/reference.png',headers=headers).status_code==404
        assert client.get(url+'/files/job.json',headers=headers).status_code==404
        invalid=client.post('/v1/memories',headers=headers,json={'scene_id':jid,'avatar_ids':['../secret']})
        assert invalid.status_code==422
        actor=make_avatar(tmp_path,uuid.uuid4().hex)
        response=client.post('/v1/memories',headers=headers,json={'scene_id':jid,'avatar_ids':[actor.name],
                                                              'options':{'duration':2,'fps':12}})
        assert response.status_code==201,response.text
        movie='/v1/memories/'+response.json()['id']
        assert client.get(movie+'/files/memory.mp4',headers=headers).status_code==404
        assert client.post(movie+'/run',headers=headers).status_code==202
        for _ in range(400):
            state=client.get(movie,headers=headers).json()
            if not state['active']:break
            time.sleep(.02)
        assert state['status']=='ready',state
        assert client.get(movie+'/files/memory.mp4',headers=headers).status_code==200
        assert client.get(movie+'/files/memory.mp4').status_code==401
        assert client.get(movie+'/files/background.png',headers=headers).status_code==404
