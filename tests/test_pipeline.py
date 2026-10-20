import json
import shutil
import re
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
from pixel_avatar.pipeline import create_job, run_job, approve, retry_stage, load
from pixel_avatar.spec import STAGES, STATES, COUNTS
from pixel_avatar.imaging import extract


@pytest.fixture
def photo(tmp_path):
    path=tmp_path/'photo.png'
    Image.new('RGB',(100,120),(130,90,70)).save(path)
    return path


class FixtureProvider:
    """Geometry fixture only; deliberately NOT a generated character."""
    def __init__(self): self.calls=[]
    def generate(self,prompt,refs,stage):
        self.calls.append(stage)
        assert refs and all(p.exists() for p in refs)
        n=1 if stage=='base' else 4 if stage=='cardinals' else COUNTS[STATES.index(stage)]
        key=re.search(r'background (#[0-9A-F]{6})',prompt)
        im=Image.new('RGBA',(192*n,208),key.group(1) if key else '#0000FF')
        draw=ImageDraw.Draw(im)
        for i in range(n):
            offset=-20 if stage=='jumping' and i==2 else 0
            draw.rectangle((i*192+65,40+offset,i*192+125,180+offset),fill=(130+i*8,75,65,255))
        return im


def test_full_pipeline_resume_and_migrate(tmp_path,photo):
    folder=create_job(tmp_path/'data',[photo],name='她')
    provider=FixtureProvider()
    for stage in STAGES:
        result=run_job(folder,provider)
        assert result['review']==stage
        assert run_job(folder,provider)['status']=='needs_review'
        approve(folder,stage,'Fixture-only approval, not a visual quality verdict')
    moved=tmp_path/'new-host'/folder.name
    moved.parent.mkdir()
    shutil.move(str(folder),moved)
    result=run_job(moved,provider)
    assert result['review']=='final'
    assert provider.calls==STAGES
    approve(moved,'final','Layout test')
    assert load(moved)['published']
    with Image.open(moved/'output/spritesheet.png') as im:
        assert im.size==(1536,2288)
        assert not im.crop((6*192,0,8*192,208)).getbbox()
        for row,n in enumerate(COUNTS):
            for col in range(n): assert im.crop((col*192,row*208,(col+1)*192,(row+1)*208)).getbbox()
    manifest=json.loads((moved/'output/avatar.json').read_text(encoding='utf-8'))
    assert [x['degrees'] for x in manifest['gaze']]==[i*22.5 for i in range(16)]
    retry_stage(moved,'look-row-9','Wrong screen-right gaze')
    job=load(moved)
    assert not job['published']
    assert not (moved/'output/spritesheet.png').exists()
    assert job['stages']['look-row-10']['status']=='pending'
    assert job['stages']['waving']['status']=='approved'


def test_failure_reuses_saved_raw(tmp_path,photo,monkeypatch):
    from pixel_avatar import imaging
    folder=create_job(tmp_path/'data',[photo]); provider=FixtureProvider()
    original=imaging.extract
    def fail(*args,**kwargs): raise ValueError('test processing failure')
    monkeypatch.setattr(imaging,'extract',fail)
    with pytest.raises(ValueError):run_job(folder,provider)
    assert load(folder)['status']=='failed'
    monkeypatch.setattr(imaging,'extract',original)
    assert run_job(folder,provider)['review']=='base'
    assert provider.calls==['base']


def test_bad_review_and_base_invalidation(tmp_path,photo):
    folder=create_job(tmp_path/'data',[photo]);p=FixtureProvider()
    run_job(folder,p)
    with pytest.raises(ValueError):approve(folder,'waving','out of order')
    with pytest.raises(ValueError):approve(folder,'base',' ')
    approve(folder,'base','ok');run_job(folder,p)
    retry_stage(folder,'base','Change hairstyle')
    assert all(s['status']=='pending' for s in load(folder)['stages'].values())
    assert not list((folder/'processed').glob('*.png'))


def test_extraction_preserves_jump(tmp_path):
    p=tmp_path/'strip.png'
    im=FixtureProvider().generate('',[Path(__file__)],'jumping');im.save(p)
    frames=extract(p,5,[0,0,255],2,preserve_y=True)
    assert frames[2].getbbox()[3]<frames[0].getbbox()[3]
    assert all(set(f.getchannel('A').getdata())<={0,255} for f in frames)


def test_invalid_inputs_and_clipping(tmp_path,photo):
    with pytest.raises(ValueError):create_job(tmp_path,[],pixel_block=2)
    with pytest.raises(ValueError):create_job(tmp_path,[photo],pixel_block=3)
    p=tmp_path/'bad.png';Image.new('RGB',(192,208),'red').save(p)
    with pytest.raises(ValueError,match='edge-clipped'):extract(p,1,[0,0,255],2)
