import json
import re
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from filelock import FileLock
from PIL import Image
from . import imaging
from .spec import STAGES, STATES, COUNTS, prompt


def write_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows may briefly deny replacement while a status request is reading.
    for attempt in range(20):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt==19: raise
            time.sleep(.01)


def load(folder):
    return json.loads((Path(folder)/"job.json").read_text(encoding="utf-8"))


def save(folder, job):
    job["updatedAt"] = datetime.now(timezone.utc).isoformat()
    write_json(Path(folder)/"job.json",job)


def lock(folder):
    return FileLock(str(Path(folder)/".lock"), timeout=0)


def create_job(root, photos, name="Avatar", notes="", pixel_block=2):
    if not 1 <= len(photos) <= 4:
        raise ValueError("Supply 1–4 photos of ONE person; create two jobs for a couple")
    if pixel_block not in (1,2,4):
        raise ValueError("pixel_block must be 1, 2 or 4")
    if not 1 <= len(name) <= 80 or len(notes) > 2000:
        raise ValueError("Name must be 1–80 characters and notes at most 2000")
    folder = Path(root)/uuid.uuid4().hex
    for sub in ("references","raw","processed","prompts","guides","output"):
        (folder/sub).mkdir(parents=True,exist_ok=True)
    try:
        for i,photo in enumerate(photos):
            imaging.normalize_photo(photo,folder/"references"/f"{i}.png")
    except Exception:
        import shutil
        shutil.rmtree(folder)  # Newly allocated UUID directory owned by this call only.
        raise
    key = imaging.choose_key(sorted((folder/"references").glob("*.png")))
    job = {"id":folder.name,"name":name,"notes":notes,"pixelBlock":pixel_block,
           "key":key,"status":"created","current":None,"error":None,
           "stages":{s:{"status":"pending","attempt":0,"correction":""} for s in STAGES},
           "review":None,"published":False}
    save(folder,job)
    return folder


def references(folder, stage):
    if stage == "base":
        return sorted((folder/"references").glob("*.png"))
    refs = [folder/"processed/base.png",folder/"guides"/f"{stage}.png"]
    if stage.startswith("look-row"):
        refs.append(folder/"processed/cardinals.png")
    if stage == "look-row-10":
        refs.append(folder/"processed/look-row-9.png")
    return refs


def run_job(folder, provider=None):
    """Run until the next visual review. Resumable, one exclusive writer per job."""
    folder = Path(folder)
    with lock(folder):
        job = load(folder)
        if job["status"] in ("needs_review","ready"):
            return job
        try:
            for stage in STAGES:
                item = job["stages"][stage]
                if item["status"] == "approved":
                    if not (folder/"processed"/f"{stage}.png").is_file():
                        raise ValueError(f"Missing approved output: {stage}; restore data or retry stage")
                    continue
                job.update(status="running",current=stage,error=None)
                save(folder,job)
                count = 1 if stage=="base" else (4 if stage=="cardinals" else COUNTS[STATES.index(stage)])
                raw = folder/"raw"/f"{stage}.png"
                if not raw.exists():
                    if provider is None:
                        from .provider import OpenAIProvider
                        provider = OpenAIProvider()
                    imaging.layout(count,folder/"guides"/f"{stage}.png",tuple(job["key"]))
                    text = prompt(stage,job["notes"],"#%02X%02X%02X"%tuple(job["key"]),item["correction"])
                    (folder/"prompts"/f"{stage}.txt").write_text(text,encoding="utf-8")
                    item["attempt"] += 1
                    save(folder,job)
                    image = provider.generate(text,references(folder,stage),stage)
                    tmp = raw.with_suffix(".tmp")
                    image.save(tmp,format="PNG")
                    tmp.replace(raw)
                cells = imaging.extract(raw,count,job["key"],job["pixelBlock"],stage=="jumping")
                imaging.save_strip(cells,folder/"processed"/f"{stage}.png")
                if stage in STATES[:9]:
                    imaging.save_motion(cells,stage,folder/"processed"/f"{stage}.gif")
                item["status"] = "needs_review"
                job.update(status="needs_review",review=stage)
                save(folder,job)
                return job
            data = imaging.assemble(folder,job["name"],job["pixelBlock"])
            write_json(folder/"output/avatar.json",data)
            job.update(status="needs_review",review="final",current="final")
        except Exception as exc:
            job.update(status="failed",error=f"{type(exc).__name__}: {exc}")
            save(folder,job)
            raise
        save(folder,job)
        return job


def approve(folder, stage, note):
    if not note.strip() or len(note)>4000:
        raise ValueError("A 1–4000 character visual review note is required")
    folder = Path(folder)
    with lock(folder):
        job = load(folder)
        if job["status"] != "needs_review" or job["review"] != stage:
            raise ValueError("Review stage no longer matches job; reload status")
        if stage == "final":
            job.update(status="ready",published=True,review=None,finalReview=note)
        else:
            job["stages"][stage].update(status="approved",reviewNote=note)
            job.update(status="paused",review=None)
        save(folder,job)
    return job


def retry_stage(folder, stage, correction):
    if stage not in STAGES or not correction.strip() or len(correction)>2000:
        raise ValueError("Specify a valid stage and a 1–2000 character correction")
    folder = Path(folder)
    with lock(folder):
        job = load(folder)
        # Invalidate dependencies, not unrelated approved motions.
        affected = set(STAGES if stage=="base" else [stage])
        if stage=="cardinals": affected.update(STATES[9:])
        if stage=="look-row-9": affected.add("look-row-10")
        history = folder/"history"/uuid.uuid4().hex
        for s in affected:
            item = job["stages"][s]
            for sub in ("raw","processed"):
                for suffix in ("png","gif"):
                    path = folder/sub/f"{s}.{suffix}"
                    if path.exists():
                        (history/sub).mkdir(parents=True,exist_ok=True)
                        path.replace(history/sub/path.name)
            item["status"] = "pending"
            item.pop("reviewNote",None)
        job["stages"][stage]["correction"] = correction
        # Old outputs must never remain downloadable after invalidation.
        for path in (folder/"output").iterdir():
            if path.is_file():
                (history/"output").mkdir(parents=True,exist_ok=True)
                path.replace(history/"output"/path.name)
        job.update(status="paused",review=None,published=False,current=stage,error=None)
        save(folder,job)
        return job


def resolve_job(root, job_id):
    if not re.fullmatch(r"[a-f0-9]{32}",job_id):
        raise ValueError("Invalid job ID")
    path = Path(root)/job_id
    if not (path/"job.json").is_file():
        raise FileNotFoundError("Job not found")
    return path
