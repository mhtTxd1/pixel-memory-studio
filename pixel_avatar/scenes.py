"""Text/photo -> a reusable micro-pixel background. No generation on import/create."""
import shutil
import uuid
from pathlib import Path
from PIL import Image, ImageOps
from .imaging import normalize_photo
from .pipeline import load, save, lock, write_json

SIZES = {"landscape":(1280,720), "portrait":(720,1280), "square":(960,960)}


def create_scene(root, description="", photo=None, style_avatar=None, aspect="landscape", pixel_block=2):
    if not description.strip() and photo is None:
        raise ValueError("Provide a scene photo or a text description")
    if len(description)>3000 or aspect not in SIZES or pixel_block not in (1,2,4):
        raise ValueError("Invalid description (max 3000), aspect or pixel_block")
    folder=Path(root)/uuid.uuid4().hex
    folder.mkdir(parents=True)
    try:
        if photo is not None: normalize_photo(photo,folder/"reference.png")
        if style_avatar:
            with lock(style_avatar):
                avatar=load(style_avatar)
                if avatar["stages"]["base"]["status"]!="approved":
                    raise ValueError("Approve the avatar base before using it as a style reference")
                shutil.copyfile(Path(style_avatar)/"processed/base.png",folder/"style.png")
        save(folder,{"id":folder.name,"kind":"scene","status":"created","description":description,
                     "aspect":aspect,"pixelBlock":pixel_block,"error":None,"attempt":0,
                     "visualReviewed":False})
    except Exception:
        shutil.rmtree(folder)
        raise
    return folder


def scene_prompt(job, has_photo=False, has_style=False):
    width,height=SIZES[job['aspect']]
    return ("Create one cohesive 2D micro-pixel game background for a warm personal memory. "
            f"Composition aspect {width}:{height}. Deliberate small square pixel clusters, crisp stepped "
            "contours, restrained warm palette and simple shading. Match cute 2.5-head-tall human chibi "
            "sprites with readable outlines; not photorealistic, not smooth 3D, not coarse 8-bit art. "
            "No people, characters, silhouettes, text, logos, borders or UI. A complete opaque scene. "
            "Keep a clear walkable foreground floor across the middle 20–80% of image width. "
            "Characters' feet will sit at 84% of image height: keep this ground visible, leave space "
            "above it for two characters. Place important scenery in the upper two-thirds and sides. "
            "Use a nearly frontal game-stage perspective, not top-down or isometric. "
            + ("The FIRST image is a scene reference: preserve its recognizable setting, layout and colors; "
               "remove all people and reinterpret the scenery in micro-pixel style. " if has_photo else "")
            + ("The LAST image is ONLY an avatar style reference: match palette, line weight and shading; "
               "do NOT copy its person or transparency background into the scene. " if has_style else "")
            + f"Scene requested: {job['description'] or 'Recreate the supplied location'}. ")


def run_scene(folder, provider=None):
    folder=Path(folder)
    with lock(folder):
        job=load(folder)
        if job['status']=='ready': return job
        try:
            job.update(status='running',error=None);save(folder,job)
            raw=folder/'raw.png'
            if not raw.exists():
                if provider is None:
                    from .provider import OpenAIProvider
                    provider=OpenAIProvider()
                refs=[folder/name for name in ('reference.png','style.png') if (folder/name).exists()]
                prompt=scene_prompt(job,(folder/'reference.png').exists(),(folder/'style.png').exists())
                (folder/'prompt.txt').write_text(prompt,encoding='utf-8')
                job['attempt']+=1;save(folder,job)
                im=provider.generate(prompt,refs,'scene-'+job['aspect'])
                im.save(folder/'raw.tmp',format='PNG');(folder/'raw.tmp').replace(raw)
            size=SIZES[job['aspect']];block=job['pixelBlock']
            with Image.open(raw) as im:
                bg=ImageOps.fit(im.convert('RGB'),size,method=Image.Resampling.LANCZOS)
                bg=bg.resize((size[0]//block,size[1]//block),Image.Resampling.BOX)
                bg=bg.quantize(colors=96,dither=Image.Dither.NONE).convert('RGB')
                bg=bg.resize(size,Image.Resampling.NEAREST)
                bg.save(folder/'background.png')
            write_json(folder/'scene.json',{'schemaVersion':1,'image':'background.png',
                       'width':size[0],'height':size[1],'pixelBlock':block,'groundY':.84,
                       'visualReviewed':False,'description':job['description']})
            job.update(status='ready',error=None);save(folder,job)
            return job
        except Exception as exc:
            job.update(status='failed',error=f'{type(exc).__name__}: {exc}');save(folder,job)
            raise


def retry_scene(folder, description):
    if not description.strip() or len(description)>3000:
        raise ValueError('Provide a revised description (1–3000 characters)')
    folder=Path(folder)
    with lock(folder):
        job=load(folder);history=folder/'history'/uuid.uuid4().hex
        history.mkdir(parents=True)
        for name in ('raw.png','background.png','scene.json','prompt.txt'):
            if (folder/name).exists(): (folder/name).replace(history/name)
        job.update(status='created',description=description,error=None,visualReviewed=False)
        save(folder,job)
    return job
