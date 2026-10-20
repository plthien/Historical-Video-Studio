"""A3-02 original-only download: bounded media, allowlisted HTTPS, no previews."""
import os
import struct
from urllib.parse import urlparse
from ipaddress import ip_address
import httpx
from backend.app.contracts import ContractViolation

MAX_BYTES=20*1024*1024
HOSTS={"wikimedia_commons":("upload.wikimedia.org",),
       "loc":("www.loc.gov","tile.loc.gov","cdn.loc.gov","memory.loc.gov","loc.gov"),
       "europeana":("www.europeana.eu","api.europeana.eu","data.europeana.eu")}

def verify_url(candidate):
    url=candidate.get("original_download_url")
    if not url:
        raise ContractViolation("SOURCE_FILE_UNAVAILABLE","source","Original unavailable; preview is not an original.")
    u=urlparse(url)
    hostname=(u.hostname or "").lower().rstrip(".")
    if u.scheme!="https" or u.username or u.password or u.port not in (None,443):
        raise ContractViolation("ORIGINAL_HOST_FORBIDDEN","source","Use verified HTTPS media.")
    try:
        ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ContractViolation("ORIGINAL_HOST_FORBIDDEN","source","IP literal not permitted.")
    extra=tuple(x.strip().lower() for x in os.getenv("HVS_ARCHIVE_MEDIA_HOSTS","").split(",") if x.strip())
    if hostname not in (*HOSTS.get(candidate.get("provider"),()),*extra):
        raise ContractViolation("ORIGINAL_HOST_FORBIDDEN","source","Verify the provider's media host first.")
    path=u.path.lower()
    if "thumb" in path or "preview" in path or "icon" in path:
        raise ContractViolation("ORIGINAL_NOT_VERIFIED","source","Thumbnail is not an original.")
    return url

def inspect(data):
    if not data or len(data)>MAX_BYTES:
        raise ContractViolation("ORIGINAL_SIZE_INVALID","media","Original missing or larger than 20MB.")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data)>45:
        width,height=struct.unpack(">II",data[16:24])
        if data[12:16]!=b"IHDR" or not data.endswith(b"IEND\xaeB`\x82"):
            raise ContractViolation("ORIGINAL_MEDIA_INVALID","media","Invalid PNG.")
        mime="image/png"
    elif data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9") and len(data)>32:
        width=height=None
        mime="image/jpeg"
    elif data[:4]==b"RIFF" and data[8:12]==b"WEBP" and len(data)>24:
        if int.from_bytes(data[4:8],"little")+8!=len(data):
            raise ContractViolation("ORIGINAL_MEDIA_INVALID","media","Invalid WebP length.")
        width=height=None
        mime="image/webp"
    else:
        raise ContractViolation("ORIGINAL_MEDIA_INVALID","media","Bytes are not a supported image.")
    if width is not None and not (1<=width<=25000 and 1<=height<=25000):
        raise ContractViolation("ORIGINAL_MEDIA_INVALID","media","Invalid dimensions.")
    return {"mime_type":mime,"byte_count":len(data),"width":width,"height":height}

def download(candidate,client=None):
    url=verify_url(candidate)
    owned=client is None
    client=client or httpx.Client(timeout=15,follow_redirects=False)
    try:
        try:
            with client.stream("GET",url,follow_redirects=False,timeout=15) as r:
                if r.is_redirect:
                    raise ContractViolation("ORIGINAL_REDIRECT_FORBIDDEN","source","Media redirect requires review.")
                if r.status_code>=400:
                    raise ContractViolation("ORIGINAL_DOWNLOAD_FAILED","source","Provider media HTTP failure.")
                try: advertised=int(r.headers.get("content-length","0"))
                except ValueError: advertised=0
                if advertised>MAX_BYTES:
                    raise ContractViolation("ORIGINAL_SIZE_INVALID","media","Advertised file too large.")
                chunks=bytearray()
                for part in r.iter_bytes():
                    chunks.extend(part)
                    if len(chunks)>MAX_BYTES:
                        raise ContractViolation("ORIGINAL_SIZE_INVALID","media","Stream exceeded maximum.")
                payload=bytes(chunks)
                metadata=inspect(payload)
                mime=r.headers.get("content-type","").split(";")[0].lower().strip()
                if mime and mime not in (metadata["mime_type"],"application/octet-stream"):
                    raise ContractViolation("ORIGINAL_MIME_MISMATCH","media","Content type differs from bytes.")
                return payload,metadata,url
        except (httpx.TimeoutException,httpx.TransportError) as exc:
            raise ContractViolation("ORIGINAL_DOWNLOAD_FAILED","source","Original download failed.") from exc
    finally:
        if owned: client.close()
