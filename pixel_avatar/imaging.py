from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from .spec import STATES, COUNTS, DURATIONS, manifest
from .vendor.extract_strip_frames import remove_chroma_background, component_frame_groups, component_group_image
from .vendor.despill_chroma_edges import decontaminate_image


def normalize_photo(source, target):
    with Image.open(source) as im:
        if im.format not in {"JPEG", "PNG", "WEBP"} or im.width*im.height > 25_000_000:
            raise ValueError("Use PNG/JPEG/WebP, at most 25 megapixels")
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((1536,1536))
        im.save(target, format="PNG")  # Strip metadata and normalize orientation.


def choose_key(photos):
    candidates = [(0,0,255),(255,0,255),(0,255,0),(0,255,255)]
    pixels = []
    for path in photos:
        with Image.open(path) as im:
            pixels += list(im.convert("RGB").resize((48,48)).getdata())
    return max(candidates, key=lambda c: sorted(sum((a-b)**2 for a,b in zip(c,p)) for p in pixels)[len(pixels)//20])


def layout(n, path, key):
    im = Image.new("RGB", (n*192,208), key)
    draw = ImageDraw.Draw(im)
    for i in range(n):
        draw.rectangle((i*192+18,16,(i+1)*192-18,192), outline="white", width=2)
    im.save(path)


def extract(source, count, key, block, preserve_y=False):
    with Image.open(source) as original:
        im = remove_chroma_background(original, tuple(key), 80)
    box = im.getbbox()
    if not box or box[0] < 2 or box[1] < 2 or box[2] > im.width-2 or box[3] > im.height-2:
        raise ValueError("Empty or edge-clipped source; regenerate the whole strip")
    groups = component_frame_groups(im, count)
    if not groups or len(groups) != count:
        raise ValueError(f"Cannot detect {count} separate poses; regenerate strip")
    bounds = [(min(c['bbox'][0] for c in g), min(c['bbox'][1] for c in g),
               max(c['bbox'][2] for c in g), max(c['bbox'][3] for c in g)) for g in groups]
    if any(a[2] >= b[0] for a,b in zip(bounds,bounds[1:])):
        raise ValueError("Overlapping pose groups; regenerate strip")
    top, bottom = min(b[1] for b in bounds), max(b[3] for b in bounds)
    # One scale per strip, never stretch each pose separately. Keep jumping's Y travel.
    max_height = bottom-top if preserve_y else max(b[3]-b[1] for b in bounds)
    scale = min(160/max(b[2]-b[0] for b in bounds), 176/max_height)
    cells = []
    for group,b in zip(groups,bounds):
        sprite = component_group_image(im, group, padding=0)
        w,h = max(1,round(sprite.width*scale)), max(1,round(sprite.height*scale))
        sprite = sprite.resize((w,h), Image.Resampling.NEAREST)
        cell = Image.new("RGBA",(192,208))
        y = 192-round((bottom-b[1])*scale) if preserve_y else 192-h
        cell.alpha_composite(sprite, ((192-w)//2,y))
        cell, _ = decontaminate_image(cell, chroma_key=tuple(key))
        cell = cell.resize((192//block,208//block),Image.Resampling.NEAREST).resize((192,208),Image.Resampling.NEAREST)
        if not cell.getbbox():
            raise ValueError("Pixel conversion erased a pose")
        cells.append(cell)
    return cells


def save_strip(cells, path):
    im = Image.new("RGBA",(192*len(cells),208))
    for i,cell in enumerate(cells):
        im.alpha_composite(cell,(192*i,0))
    im.save(path)


def read_strip(path, n):
    with Image.open(path) as im:
        return [im.convert("RGBA").crop((192*i,0,192*(i+1),208)) for i in range(n)]


def save_motion(cells, state, path):
    gif=[]
    for cell in cells:
        bg=Image.new("RGB",cell.size,(239,234,224))
        bg.paste(cell,mask=cell.getchannel("A")); gif.append(bg)
    gif[0].save(path,save_all=True,append_images=gif[1:],duration=DURATIONS[STATES.index(state)],loop=0)


def assemble(folder, name, block):
    final = folder / "output"
    final.mkdir(exist_ok=True)
    atlas = Image.new("RGBA",(1536,2288))
    contact = Image.new("RGB",(1536,11*236),(239,234,224))
    draw = ImageDraw.Draw(contact)
    for row,(state,n) in enumerate(zip(STATES,COUNTS)):
        cells = read_strip(folder / "processed" / f"{state}.png",n)
        for i,cell in enumerate(cells):
            if not cell.getbbox():
                raise ValueError(f"Blank cell {state}/{i}")
            atlas.alpha_composite(cell,(i*192,row*208))
            contact.paste(cell,(i*192,row*236+28),cell)
            label = f"{(row-9)*180+i*22.5:g} deg" if row>=9 else str(i+1)
            draw.text((i*192+8,row*236+8),f"{state} / {label}",fill=(45,48,52))
        if row < 9:
            save_motion(cells,state,final/f"{state}.gif")
    atlas.save(final/"spritesheet.png")
    atlas.save(final/"spritesheet.webp",lossless=True,exact=True)
    contact.save(final/"contact-sheet.png")
    return manifest(name,block)
