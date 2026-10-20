"""Private backend service. One uvicorn worker; persistent jobs, explicit restart/resume."""
import hmac
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from fastapi import FastAPI, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from filelock import Timeout
from .pipeline import create_job,run_job,approve,retry_stage,load,resolve_job
from .spec import STAGES, STATES


def create_app(root=None, token=None, provider_factory=None):
    root=Path(root or os.getenv("AVATAR_DATA_DIR","data"))
    token=token or os.getenv("AVATAR_SERVICE_TOKEN","")
    if len(token)<16:
        raise ValueError("Set AVATAR_SERVICE_TOKEN to a secret of at least 16 characters")
    executor=ThreadPoolExecutor(max_workers=2)
    active=set(); mutex=threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        yield
        executor.shutdown(wait=True)

    app=FastAPI(title="Pixel Avatar & Memory",version="0.2.0",lifespan=lifespan)

    def auth(authorization: str=Header(default="")):
        if not hmac.compare_digest(authorization.encode(),("Bearer "+token).encode()):
            raise HTTPException(401,"Invalid service token")

    def folder(job_id):
        try: return resolve_job(root,job_id)
        except (ValueError,FileNotFoundError): raise HTTPException(404,"Job not found")

    def dispatch(path,runner=None):
        with mutex:
            if path.name in active: raise HTTPException(409,"Job already running")
            if len(active)>=8: raise HTTPException(429,"Queue full; retry later")
            active.add(path.name)
        def work():
            try:
                if runner: runner(path)
                else: run_job(path,provider_factory() if provider_factory else None)
            except Exception: pass  # pipeline persists failures; no provider secrets in HTTP errors
            finally:
                with mutex: active.discard(path.name)
        executor.submit(work)

    def ensure_idle(path):
        with mutex:
            if path.name in active: raise HTTPException(409,"Wait for active task to finish")

    @app.get("/health")
    def health(): return {"ok":True}

    web=Path(__file__).parent/"web"
    @app.get("/")
    def index(): return FileResponse(web/"index.html")

    @app.get("/player.js")
    def player(): return FileResponse(web/"player.js",media_type="text/javascript")

    @app.post("/v1/avatars",dependencies=[Depends(auth)],status_code=201)
    async def create(photos:list[UploadFile]=File(...),name:str=Form("Avatar"),
                     notes:str=Form(""),pixel_block:int=Form(2)):
        if not 1<=len(photos)<=4: raise HTTPException(422,"Supply 1–4 photos of one person")
        sources=[]
        try:
            for photo in photos:
                data=await photo.read(10*1024*1024+1)
                if len(data)>10*1024*1024: raise ValueError("Each photo must be at most 10 MB")
                sources.append(BytesIO(data))
            path=create_job(root,sources,name,notes,pixel_block)
            return load(path)
        except (ValueError,OSError) as exc: raise HTTPException(422,str(exc))
        finally:
            for photo in photos: await photo.close()

    @app.get("/v1/avatars/{job_id}",dependencies=[Depends(auth)])
    def status(job_id:str):
        result=load(folder(job_id))
        with mutex: result["active"]=job_id in active
        # Detailed exceptions stay in private job.json, not in browser responses.
        if result.get("error"): result["error"]="Generation/processing failed; inspect server job.json and retry."
        return result

    @app.post("/v1/avatars/{job_id}/run",dependencies=[Depends(auth)],status_code=202)
    def run(job_id:str):
        path=folder(job_id)
        if load(path)["status"] in ("needs_review","ready"):
            raise HTTPException(409,"Review current output before continuing")
        dispatch(path); return {"id":job_id,"status":"queued"}

    class Review(BaseModel):
        stage:str
        note:str=Field(min_length=1,max_length=4000)

    @app.post("/v1/avatars/{job_id}/approve",dependencies=[Depends(auth)])
    def review(job_id:str,body:Review):
        path=folder(job_id); ensure_idle(path)
        try: return approve(path,body.stage,body.note)
        except (ValueError,Timeout) as exc: raise HTTPException(409,str(exc))

    @app.post("/v1/avatars/{job_id}/retry",dependencies=[Depends(auth)])
    def retry(job_id:str,body:Review):
        path=folder(job_id); ensure_idle(path)
        try: return retry_stage(path,body.stage,body.note)
        except (ValueError,Timeout) as exc: raise HTTPException(409,str(exc))

    @app.get("/v1/avatars/{job_id}/files/{name}",dependencies=[Depends(auth)])
    def artifact(job_id:str,name:str):
        path=folder(job_id)
        if name in {f"{s}.png" for s in STAGES}|{f"{s}.gif" for s in STATES[:9]}:
            file=path/"processed"/name
        elif name in {"contact-sheet.png","spritesheet.png","spritesheet.webp","avatar.json"}|{f"{s}.gif" for s in STATES[:9]}:
            file=path/"output"/name
        else: raise HTTPException(404,"Unknown artifact")
        if not file.is_file(): raise HTTPException(404,"Artifact not available")
        return FileResponse(file,headers={"Cache-Control":"no-store"})

    from .media_api import register_media
    def is_active(job_id):
        with mutex: return job_id in active
    register_media(app,root,auth,dispatch,ensure_idle,is_active,provider_factory)
    return app
