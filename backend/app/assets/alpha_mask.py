"""Validate a genuine alpha-bearing PNG used as a G3-reviewed T02 derivative.

Only RGBA8, non-interlaced mask PNGs are accepted.  This intentionally does not
reinterpret arbitrary image bytes or infer a source crop from CSS.
"""
from __future__ import annotations

import struct
import zlib
from backend.app.contracts import ContractViolation


def rgba_alpha_extent(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data)>20_000_000:
        raise ContractViolation("MASK_DERIVATIVE_INVALID", "mask", "Require a bounded PNG source.")
    offset=8
    width=height=None
    stream=bytearray()
    end_found=False
    while offset+12<=len(data):
        size=int.from_bytes(data[offset:offset+4],"big")
        end=offset+12+size
        if size>20_000_000 or end>len(data):
            raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","Malformed PNG chunk length.")
        tag=data[offset+4:offset+8]
        payload=data[offset+8:offset+8+size]
        crc=struct.unpack(">I",data[offset+8+size:end])[0]
        if zlib.crc32(tag+payload)!=crc:
            raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","PNG integrity check failed.")
        if tag==b"IHDR":
            if size!=13 or width is not None:
                raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","Invalid PNG IHDR.")
            width,height,depth,kind,comp,filt,interlace=struct.unpack(">IIBBBBB",payload)
            if not (4<=width<=4096 and 4<=height<=4096 and width*height<=8_000_000
                    and depth==8 and kind==6 and comp==0 and filt==0 and interlace==0):
                raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","Review noninterlaced RGBA8 at supported dimensions.")
        elif tag==b"IDAT":
            stream.extend(payload)
        elif tag==b"IEND":
            if size!=0:raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","Invalid PNG terminator.")
            end_found=True
            offset=end
            break
        offset=end
    if not end_found or offset!=len(data) or width is None or not stream:
        raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","Missing PNG image data.")
    stride=width*4
    decoder=zlib.decompressobj()
    try:
        decoded=decoder.decompress(bytes(stream),(stride+1)*height+1)
        decoded+=decoder.flush()
    except zlib.error as exc:
        raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","Corrupt RGBA scanlines.") from exc
    if len(decoded)!=(stride+1)*height or not decoder.eof:
        raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","Incomplete or oversized RGBA raster.")
    prev=bytearray(stride)
    at=0
    transparent=opaque=0
    for _ in range(height):
        method=decoded[at]
        at+=1
        cur=bytearray(decoded[at:at+stride])
        at+=stride
        if method>4:
            raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","Unsupported PNG filter.")
        for k in range(stride):
            left=cur[k-4] if k>=4 else 0
            above=prev[k]
            corner=prev[k-4] if k>=4 else 0
            if method==1:v=left
            elif method==2:v=above
            elif method==3:v=(left+above)//2
            elif method==4:
                p=left+above-corner
                choices=(abs(p-left),abs(p-above),abs(p-corner))
                v=(left,above,corner)[choices.index(min(choices))]
            else:v=0
            cur[k]=(cur[k]+v)&255
        for col in range(3,stride,4):
            if cur[col]==0:transparent+=1
            elif cur[col]==255:opaque+=1
        prev=cur
    if not transparent or not opaque:
        raise ContractViolation("MASK_DERIVATIVE_INVALID","mask","Review a nonempty cutout with transparent and opaque pixels.")
    return width,height
