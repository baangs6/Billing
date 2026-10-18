"""Bounded product thumbnails, decoded and re-encoded without upload metadata."""
import base64
import io
import warnings
from PIL import Image, UnidentifiedImageError


def thumbnail(upload):
    content=upload.stream.read(2*1024*1024+1)
    if len(content)>2*1024*1024: raise ValueError('Product photos must be under 2 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ('PNG','JPEG') or max(image.size)>4096: raise ValueError('Choose a PNG or JPEG image up to 4096 pixels per side.')
                image.load();image.thumbnail((320,320))
                clean=Image.new('RGB',image.size);clean.paste(image.convert('RGB'))
                output=io.BytesIO();clean.save(output,format='JPEG',quality=80)
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ValueError('Upload a valid PNG or JPEG product photo.')
    if output.tell()>128*1024: raise ValueError('Choose a simpler product photo; the thumbnail exceeds 128 KB.')
    return base64.b64encode(output.getvalue()).decode('ascii')
