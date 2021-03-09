import asyncio
import pathlib
from concurrent.futures import ThreadPoolExecutor

import pytesseract

pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="OCR_Worker")

def _do_img(path):
    try:
        return pytesseract.image_to_string(path)
    except RuntimeError:
        return None

async def do_ocr(path: pathlib.Path, loop: asyncio.AbstractEventLoop):
    return await loop.run_in_executor(pool, _do_img, path)
