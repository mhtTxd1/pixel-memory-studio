from io import BytesIO
from pathlib import Path
from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from filelock import Timeout
from pydantic import BaseModel, Field, ConfigDict
from .pipeline import load, resolve_job
from .scenes import create_scene, run_scene, retry_scene
from .movie import MovieOptions, create_movie, render_movie


class MovieRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scene_id:str
    avatar_ids:list[str]=Field(min_length=1,max_length=2)
    options:MovieOptions=Field(default_factory=MovieOptions)


class SceneRetry(BaseModel):
    description:str=Field(min_length=1,max_length=3000)


def register_media(app,root,auth,dispatch,ensure_idle,is_active,provider_factory):
    def get(kind,identifier):
        try:return resolve_job(root/kind,identifier)
        except (ValueError,FileNotFoundError):raise HTTPException(404,'Task not found')

    def public(path):
        job=load(path);job['active']=is_active(path.name)
        if job.get('error'):job['error']='Task failed; inspect server job.json for details'
        return job

    @app.get('/memory')
    def studio():return FileResponse(Path(__file__).parent/'web/memory.html')

    @app.post('/v1/scenes',dependencies=[Depends(auth)],status_code=201)
    async def create(description:str=Form(''),photo:UploadFile|None=File(None),
                     style_avatar_id:str=Form(''),aspect:str=Form('landscape'),pixel_block:int=Form(2)):
        try:
            source=None
            if photo:
                data=await photo.read(10*1024*1024+1)
                if len(data)>10*1024*1024:raise ValueError('Photo must be at most 10 MB')
                source=BytesIO(data)
            style=resolve_job(root,style_avatar_id) if style_avatar_id else None
            return public(create_scene(root/'scenes',description,source,style,aspect,pixel_block))
        except (ValueError,OSError,Timeout) as exc:raise HTTPException(422,str(exc))
        finally:
            if photo:await photo.close()

    @app.get('/v1/scenes/{identifier}',dependencies=[Depends(auth)])
    def scene_status(identifier:str):return public(get('scenes',identifier))

    @app.post('/v1/scenes/{identifier}/run',dependencies=[Depends(auth)],status_code=202)
    def scene_run(identifier:str):
        path=get('scenes',identifier)
        if load(path)['status']=='ready':raise HTTPException(409,'Scene ready; retry to regenerate')
        dispatch(path,lambda p:run_scene(p,provider_factory() if provider_factory else None))
        return {'id':identifier,'status':'queued'}

    @app.post('/v1/scenes/{identifier}/retry',dependencies=[Depends(auth)])
    def scene_retry(identifier:str,body:SceneRetry):
        path=get('scenes',identifier);ensure_idle(path)
        try:return retry_scene(path,body.description)
        except (ValueError,Timeout) as exc:raise HTTPException(409,str(exc))

    @app.get('/v1/scenes/{identifier}/files/{name}',dependencies=[Depends(auth)])
    def scene_file(identifier:str,name:str):
        if name not in ('background.png','scene.json'):raise HTTPException(404,'Unknown artifact')
        path=get('scenes',identifier)/name
        if not path.is_file():raise HTTPException(404,'Artifact not ready')
        return FileResponse(path,headers={'Cache-Control':'no-store'})

    @app.post('/v1/memories',dependencies=[Depends(auth)],status_code=201)
    def movie_create(body:MovieRequest):
        try:
            avatars=[resolve_job(root,i) for i in body.avatar_ids]
            return public(create_movie(root/'movies',get('scenes',body.scene_id),avatars,body.options.model_dump()))
        except (ValueError,OSError,Timeout) as exc:raise HTTPException(422,str(exc))

    @app.get('/v1/memories/{identifier}',dependencies=[Depends(auth)])
    def movie_status(identifier:str):return public(get('movies',identifier))

    @app.post('/v1/memories/{identifier}/run',dependencies=[Depends(auth)],status_code=202)
    def movie_run(identifier:str):
        path=get('movies',identifier)
        if load(path)['status']=='ready':raise HTTPException(409,'Recording already rendered')
        dispatch(path,render_movie);return {'id':identifier,'status':'queued'}

    @app.get('/v1/memories/{identifier}/files/{name}',dependencies=[Depends(auth)])
    def movie_file(identifier:str,name:str):
        if name not in ('memory.mp4','poster.png','timeline.json'):raise HTTPException(404,'Unknown artifact')
        path=get('movies',identifier)
        if load(path)['status']!='ready' or not (path/name).is_file():raise HTTPException(404,'Artifact not ready')
        return FileResponse(path/name,headers={'Cache-Control':'no-store'})
