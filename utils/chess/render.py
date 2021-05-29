import io
import os
from PIL import Image, ImageDraw, ImageFont
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from . import models

FONT = ImageFont.truetype("./static/fonts/arial.ttf", 48)

def draw(board: "models.Board", arrow: Optional[str]=None) -> io.BytesIO:
    base = Image.open(board.get_asset()).convert("RGBA") # type: Image.Image
    dr = ImageDraw.Draw(base)
    cached_images = {}
    drew_nums = False

    for r, c in enumerate(board.pieces.items()):
        x = r*150
        dr.text((r*150, 0), c[0], stroke_fill=0xffffff, font=FONT)

        for t, v in enumerate(c[1]):
            if not drew_nums:
                dr.text((0, 1200-(t*150)-48), str(t+1), stroke_fill=0xffffff, font=FONT)

            if not v:
                continue

            y = 1200-((t+1)*150)
            if v.type in cached_images:
                img, mask = cached_images[v.type]
            else:
                fp = v.get_asset(board.white_theme if v.white else board.black_theme)
                img = Image.open(fp, formats=("PNG",)) # type: Image.Image
                mask = img.convert("RGBA")
                cached_images[v.type] = img, mask

            base.paste(img, (x, y), mask=mask)
            #dr.text((x,y), f"{v.position}", font=FONT)

        drew_nums = True

    if arrow is not None:
        pass

    b = io.BytesIO()
    base.save(b, format="png")
    base.close()
    for i in cached_images.values():
        i[0].close()
        i[1].close()

    b.seek(0)
    return b
