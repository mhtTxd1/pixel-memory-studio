import base64
import os
from contextlib import ExitStack
from io import BytesIO
from PIL import Image


class OpenAIProvider:
    """Replace this class with any provider implementing generate(prompt, refs, stage)."""
    def __init__(self):
        from openai import OpenAI
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("Set OPENAI_API_KEY on the server before generation")
        self.client = OpenAI(timeout=600, max_retries=0)
        self.model = os.getenv("IMAGE_MODEL", "gpt-image-1.5")

    def generate(self, prompt, refs, stage):
        # No automatic retry of billable calls. Explicit resume/retry is caller-owned.
        with ExitStack() as stack:
            images = [stack.enter_context(p.open("rb")) for p in refs]
            options = dict(model=self.model, prompt=prompt,
                           size=("1024x1024" if stage in ("base","scene-square") else
                                 "1024x1536" if stage=="scene-portrait" else "1536x1024"),
                           quality=os.getenv("IMAGE_QUALITY", "high"), n=1)
            result = (self.client.images.edit(image=images, **options) if images
                      else self.client.images.generate(**options))
        if not result.data or not result.data[0].b64_json:
            raise ValueError("Provider did not return base64 image data")
        raw = base64.b64decode(result.data[0].b64_json, validate=True)
        with Image.open(BytesIO(raw)) as im:
            im.load()
            return im.convert("RGBA")
