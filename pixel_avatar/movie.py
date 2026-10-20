"""Deterministic sprite animation + generated background -> H.264 MP4."""
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Literal
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, ConfigDict, model_validator
from .pipeline import load, save, lock, write_json


class Cue(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    start:float=Field(ge=0)
    end:float=Field(gt=0)
    action:str='idle'
    x:float=Field(default=.5,ge=.12,le=.88)
    to_x:float|None=Field(default=None,ge=.12,le=.88)
    gaze:int|None=Field(default=None,ge=0,le=15)

    @model_validator(mode='after')
    def interval(self):
        if self.end<=self.start: raise ValueError('Cue end must exceed start')
        return self


class MovieOptions(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    duration:int=Field(default=8,ge=2,le=15)
    fps:Literal[12,24,30]=24
    preset:Literal['meet','celebrate','quiet']='meet'
    caption:str=Field(default='',max_length=100)
    ground_y:float=Field(default=.84,ge=.55,le=.95)
    actor_height:float=Field(default=.31,ge=.15,le=.38)
    tracks:list[list[Cue]]|None=None

    @model_validator(mode='after')
    def check_tracks(self):
        if self.tracks is not None:
            if not 1<=len(self.tracks)<=2: raise ValueError('Use 1 or 2 tracks')
            for track in self.tracks:
                if not 1<=len(track)<=24: raise ValueError('Use 1–24 cues per track')
                end=0
                for cue in track:
                    if cue.start<end or cue.end>self.duration:
                        raise ValueError('Cues must be ordered, nonoverlapping, and within duration')
                    end=cue.end
        return self


def default_tracks(count, options):
    d=options.duration
    tracks=[]
    for i in range(count):
        dest=.5 if count==1 else (.39 if i==0 else .61)
        origin=.2 if i==0 else .8
        if options.preset=='quiet':
            track=[Cue(start=0,end=d,action='idle',x=dest)]
        else:
            track=[Cue(start=0,end=d*.3,action='running-right' if i==0 else 'running-left',x=origin,to_x=dest),
                   Cue(start=d*.3,end=d*.7,action='jumping' if options.preset=='celebrate' else 'waving',x=dest),
                   Cue(start=d*.7,end=d,action='idle',x=dest,gaze=(4 if i==0 else 12) if count==2 else None)]
        tracks.append(track)
    return tracks


def create_movie(root, scene_folder, avatars, options=None):
    options=MovieOptions.model_validate(options or {})
    if not 1<=len(avatars)<=2: raise ValueError('Supply 1 or 2 approved avatars')
    tracks=options.tracks or default_tracks(len(avatars),options)
    if len(tracks)!=len(avatars): raise ValueError('One timeline track is required per avatar')
    folder=Path(root)/uuid.uuid4().hex;folder.mkdir(parents=True)
    try:
        with lock(scene_folder):
            if load(scene_folder)['status']!='ready': raise ValueError('Scene is not ready')
            shutil.copyfile(Path(scene_folder)/'background.png',folder/'background.png')
            shutil.copyfile(Path(scene_folder)/'scene.json',folder/'scene.json')
        for i,avatar in enumerate(avatars):
            with lock(avatar):
                if load(avatar)['status']!='ready': raise ValueError('Avatar must pass final review first')
                target=folder/f'actor-{i}';target.mkdir()
                for name in ('avatar.json','spritesheet.png'):
                    shutil.copyfile(Path(avatar)/'output'/name,target/name)
                manifest=json.loads((target/'avatar.json').read_text(encoding='utf-8'))
                for cue in tracks[i]:
                    if cue.action not in manifest['animations']: raise ValueError(f'Unknown action: {cue.action}')
        # Store input snapshots, not live paths: later retries cannot alter this recording.
        payload=options.model_dump();payload['tracks']=[[c.model_dump() for c in t] for t in tracks]
        save(folder,{'id':folder.name,'kind':'movie','status':'created','error':None,'progress':0,
                     'sceneId':Path(scene_folder).name,'avatarIds':[Path(a).name for a in avatars],
                     'options':payload})
    except Exception:
        shutil.rmtree(folder)
        raise
    return folder


def frame_for(manifest,cue,t):
    if cue.gaze is not None:
        p=manifest['gaze'][cue.gaze];return p['row'],p['column']
    animation=manifest['animations'][cue.action]
    durations=animation['durations'];remaining=((t-cue.start)*1000)%sum(durations)
    for col,ms in enumerate(durations):
        if remaining<ms: return animation['row'],col
        remaining-=ms
    return animation['row'],len(durations)-1


def choose_font(size,text):
    candidates=[os.getenv('AVATAR_FONT_PATH',''),'/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                'C:/Windows/Fonts/msyh.ttc','/System/Library/Fonts/PingFang.ttc',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for path in candidates:
        if path and Path(path).is_file():
            if any(ord(c)>255 for c in text) and 'DejaVuSans' in path: continue
            return ImageFont.truetype(path,size)
    if any(ord(c)>255 for c in text):
        raise ValueError('Set AVATAR_FONT_PATH to a font supporting your caption language')
    return ImageFont.load_default(size=size)


def caption_layer(size,text):
    layer=Image.new('RGBA',size)
    if not text:return layer
    width,height=size;font=choose_font(max(14,round(height*.032)),text)
    draw=ImageDraw.Draw(layer);lines=[];line=''
    for char in text:
        if char=='\n' or draw.textlength(line+char,font=font)>width*.86:
            lines.append(line);line='' if char=='\n' else char
        else:line+=char
    if line:lines.append(line)
    if len(lines)>3:raise ValueError('Caption exceeds three lines; shorten it')
    step=round(height*.048);top=round(height*.045)
    draw.rounded_rectangle((width*.04,top-8,width*.96,top+len(lines)*step+8),radius=8,fill=(22,34,28,190))
    for i,line in enumerate(lines):
        draw.text((width/2,top+i*step),line,anchor='mt',font=font,fill=(255,250,232))
    return layer


def render_movie(folder):
    import imageio_ffmpeg
    folder=Path(folder)
    with lock(folder):
        job=load(folder)
        if job['status']=='ready':return job
        proc=None
        try:
            options=MovieOptions.model_validate(job['options']);tracks=options.tracks
            job.update(status='running',error=None,progress=0);save(folder,job)
            with Image.open(folder/'background.png') as im:background=im.convert('RGBA')
            width,height=background.size
            if width%2 or height%2 or width*height>2_000_000:raise ValueError('Video dimensions must be even and at most 2 MP')
            scene=json.loads((folder/'scene.json').read_text(encoding='utf-8'));block=scene['pixelBlock']
            caption=caption_layer(background.size,options.caption)
            actors=[]
            for i in range(len(tracks)):
                manifest=json.loads((folder/f'actor-{i}/avatar.json').read_text(encoding='utf-8'))
                with Image.open(folder/f'actor-{i}/spritesheet.png') as im:atlas=im.convert('RGBA')
                cw,ch=manifest['cellWidth'],manifest['cellHeight']
                if atlas.size!=(cw*8,ch*11):raise ValueError('Invalid avatar atlas dimensions')
                neutral=atlas.crop((0,0,cw,ch));bbox=neutral.getbbox()
                if not bbox:raise ValueError('Empty neutral avatar')
                scale=min(height*options.actor_height/(bbox[3]-bbox[1]),
                          width*(.24 if len(tracks)==2 else .36)/(bbox[2]-bbox[0]))
                # Anchor every frame to the neutral feet, keeping jump Y differences.
                baseline=bbox[3]*scale
                size=(max(1,round(cw*scale)),max(1,round(ch*scale)))
                frames={(r,c):atlas.crop((c*cw,r*ch,(c+1)*cw,(r+1)*ch)).resize(size,Image.Resampling.NEAREST)
                        for r in range(11) for c in range(8)}
                actors.append((manifest,frames,baseline))
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            args=[ffmpeg,'-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24',
                  '-s',f'{width}x{height}','-r',str(options.fps),'-i','-','-an','-c:v','libx264',
                  '-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'rendering.mp4')]
            total=options.duration*options.fps
            with (folder/'encoder.log').open('wb') as log:
                proc=subprocess.Popen(args,stdin=subprocess.PIPE,stderr=log,stdout=subprocess.DEVNULL)
                for index in range(total):
                    t=index/options.fps;frame=background.copy()
                    for track,(manifest,frames,baseline) in zip(tracks,actors):
                        cue=next((c for c in track if c.start<=t<c.end),None)
                        if cue is None:continue  # An explicit gap hides this actor.
                        sprite=frames[frame_for(manifest,cue,t)]
                        ratio=(t-cue.start)/(cue.end-cue.start)
                        x=cue.x if cue.to_x is None else cue.x+(cue.to_x-cue.x)*ratio
                        left=round((x*width-sprite.width/2)/block)*block
                        top=round((options.ground_y*height-baseline)/block)*block
                        frame.alpha_composite(sprite,(left,top))
                    frame=frame.resize((width//block,height//block),Image.Resampling.NEAREST).resize((width,height),Image.Resampling.NEAREST)
                    frame.alpha_composite(caption)
                    if index==total//2:frame.convert('RGB').save(folder/'poster.png')
                    proc.stdin.write(frame.convert('RGB').tobytes())
                    if index%options.fps==0:
                        job['progress']=round(index/total,3);save(folder,job)
                proc.stdin.close()
                if proc.wait(timeout=120)!=0:raise RuntimeError('FFmpeg failed; inspect encoder.log')
            (folder/'rendering.mp4').replace(folder/'memory.mp4')
            write_json(folder/'timeline.json',job['options'])
            job.update(status='ready',progress=1,width=width,height=height,frames=total,error=None)
            save(folder,job);return job
        except Exception as exc:
            if proc and proc.poll() is None:proc.kill();proc.wait()
            job.update(status='failed',error=f'{type(exc).__name__}: {exc}');save(folder,job)
            raise
