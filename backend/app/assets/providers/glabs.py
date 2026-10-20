"""A3-03 G-Labs original webhook. Paid task submits only with explicit controlled authorization."""
import base64
import hashlib
import json
import os
import re
from urllib.parse import urlparse
import httpx
from backend.app.contracts import ContractViolation
from backend.app.archives.interfaces import digest
from backend.app.assets.download import inspect
from backend.app.assets.provenance import AssetCandidates

FLOW={"nano_banana_pro","nano_banana_2","nano_banana_2_lite"}
RATIOS={"1:1","3:4","4:3","9:16","16:9"}
PICS_RATIOS=RATIOS|{"3:2","2:3","5:4","4:5","21:9"}
STATUS={"pending","running","completed","failed"}
MAX_BODY=50*1024*1024

def validate_request(prompt,model,ratio,refs,upscale=(),mode=None,keep=1):
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>10000:
        raise ContractViolation("GLABS_INPUT_INVALID","prompt","Nonempty bounded image prompt required.")
    if model not in FLOW|{"nano_pics"}:
        raise ContractViolation("GLABS_MODEL_UNSUPPORTED","model","Select a supported image model explicitly.")
    if ratio not in (PICS_RATIOS if model=="nano_pics" else RATIOS):
        raise ContractViolation("GLABS_RATIO_UNSUPPORTED","aspect_ratio","Ratio unsupported by selected model.")
    if not isinstance(refs,list):
        raise ContractViolation("GLABS_REFERENCE_INVALID","references","Expected ordered reference array.")
    if model=="nano_pics":
        if mode not in ("text_to_image","image_to_image"):
            raise ContractViolation("GLABS_MODE_INVALID","mode","Explicit Pics mode required.")
        if mode=="image_to_image" and not 1<=len(refs)<=14:
            raise ContractViolation("GLABS_REFERENCE_INVALID","references","Pics i2i needs 1-14 images.")
        if mode=="text_to_image" and refs:
            raise ContractViolation("GLABS_REFERENCE_INVALID","references","Pics t2i rejects image references.")
        if type(keep)!=int or keep not in (0,1,2,3,4) or upscale:
            raise ContractViolation("GLABS_INPUT_INVALID","keep/upscale","Invalid Pics keep or upscale.")
    elif len(refs)>10 or mode or any(x not in ("2K","4K") for x in upscale):
        raise ContractViolation("GLABS_INPUT_INVALID","references/upscale","Unsupported Flow image settings.")
    if "4K" in upscale and os.getenv("HVS_GLABS_4K_ENTITLEMENT_CONFIRMED")!="1":
        raise ContractViolation("GLABS_UPSCALE_ENTITLEMENT_UNVERIFIED","upscale",
                                "Confirm 4K plan entitlement before provider submission.")
    for ref in refs:
        if model=="nano_pics" and isinstance(ref,dict) and set(ref)!={"data"}:
            raise ContractViolation("GLABS_REFERENCE_INVALID","references",
                                    "Pics accepts positional images without Flow named tags.")
        data=ref if isinstance(ref,str) else ref.get("data") if isinstance(ref,dict) else None
        if not isinstance(data,str) or not data.startswith("data:image/") or ";base64," not in data:
            raise ContractViolation("GLABS_REFERENCE_INVALID","references","Use inline base64 images.")
        try:
            part=base64.b64decode(data.partition(";base64,")[2],validate=True)
        except (ValueError,base64.binascii.Error):
            raise ContractViolation("GLABS_REFERENCE_INVALID","references","Invalid base64 reference.")
        actual=inspect(part)
        claimed=data[5:].partition(";base64,")[0]
        if claimed!=actual["mime_type"]:
            raise ContractViolation("GLABS_REFERENCE_INVALID","references",
                                    "Reference MIME label differs from actual image bytes.")
    body={"prompt":prompt,"model":model,"aspect_ratio":ratio,"reference_images":refs}
    if model=="nano_pics":
        body.update(mode=mode,keep=keep)
    elif upscale:
        body["upscale"]=list(upscale)
    encoded=json.dumps(body,ensure_ascii=False,separators=(",",":")).encode()
    if len(encoded)>MAX_BODY:
        raise ContractViolation("GLABS_REQUEST_TOO_LARGE","body","50 MB webhook cap.")
    return body

class GLabs:
    def __init__(self,client=None,base_url=None,api_key=None):
        self.base=(base_url or os.getenv("HVS_GLABS_BASE_URL","http://127.0.0.1:8765")).rstrip("/")
        parsed=urlparse(self.base)
        if parsed.scheme!="http" or parsed.hostname not in ("127.0.0.1","localhost") or parsed.path:
            raise ContractViolation("GLABS_ENDPOINT_INVALID","base","Local webhook loopback required.")
        self.client=client or httpx.Client(timeout=20,follow_redirects=False)
        self.key=api_key if api_key is not None else os.getenv("HVS_GLABS_API_KEY","")
    def _request(self,method,path,*,body=None,binary=False):
        if not self.key and not path.startswith("/api/files/"):
            raise ContractViolation("GLABS_KEY_MISSING","api_key","Configure webhook API key locally.")
        headers={"X-API-Key":self.key} if not path.startswith("/api/files/") else {}
        try:
            r=self.client.request(method,self.base+path,headers=headers,json=body,
                                  follow_redirects=False,timeout=20)
        except (httpx.TimeoutException,httpx.TransportError) as exc:
            raise ContractViolation("GLABS_NETWORK_ERROR","webhook","Task network uncertain; reconcile before retry.") from exc
        if r.is_redirect:
            raise ContractViolation("GLABS_REDIRECT_UNVERIFIED","webhook","Unexpected webhook redirect.")
        if r.status_code==499:
            raise ContractViolation("STOPPED_BY_CLIENT","task","Provider task stopped.")
        codes={400:"GLABS_INPUT_INVALID",401:"GLABS_AUTH_REQUIRED",403:"GLABS_PLAN_REQUIRED",
               404:"GLABS_TASK_NOT_FOUND",413:"GLABS_REQUEST_TOO_LARGE",
               429:"GLABS_RATE_LIMITED"}
        if r.status_code>=400:
            raise ContractViolation(codes.get(r.status_code,"GLABS_SERVER_ERROR"),"webhook",
                                    f"Webhook HTTP {r.status_code}; inspect provider locally.")
        if binary: return r.content
        try: data=r.json()
        except ValueError as exc:
            raise ContractViolation("GLABS_JSON_INVALID","webhook","Invalid JSON from webhook.") from exc
        if not isinstance(data,dict):
            raise ContractViolation("GLABS_JSON_INVALID","webhook","Expected object.")
        return r.status_code,data
    def submit(self,body):
        status,info=self._request("POST","/api/image/generate",body=body)
        tid=info.get("task_id")
        if status!=202 or info.get("status")!="pending" or not isinstance(tid,str) or not re.fullmatch(r"[a-fA-F0-9]{8}",tid):
            raise ContractViolation("GLABS_202_INVALID","webhook","Expected pending task and durable task_id.")
        return tid
    def poll(self,task_id):
        if not re.fullmatch(r"[a-fA-F0-9]{8}",task_id):
            raise ContractViolation("GLABS_TASK_ID_INVALID","task","Invalid task identifier.")
        _,result=self._request("GET","/api/status/"+task_id)
        if result.get("task_id")!=task_id or result.get("status") not in STATUS:
            raise ContractViolation("GLABS_STATUS_INVALID",task_id,"Task/status mismatch.")
        if result["status"]=="failed":
            code=result.get("error_code")
            raise ContractViolation("STOPPED_BY_CLIENT" if code==499 else "GLABS_PROVIDER_FAILED",
                                    task_id,"Webhook task failed; inspect provider diagnostics.")
        return result
    def result(self,task_id):
        if not re.fullmatch(r"[a-fA-F0-9]{8}",task_id):
            raise ContractViolation("GLABS_TASK_ID_INVALID","task","Invalid task identifier.")
        _,info=self._request("GET","/api/result/"+task_id)
        urls=info.get("results")
        if info.get("task_id")!=task_id or info.get("status")!="completed" or not isinstance(urls,list) or not urls:
            raise ContractViolation("GLABS_RESULT_INVALID",task_id,"Expected completed image list.")
        files=[]
        for url in urls:
            u=urlparse(url)
            root=urlparse(self.base)
            if (u.scheme!=root.scheme or u.hostname!=root.hostname or u.port!=root.port
                    or not u.path.startswith("/api/files/") or u.query or u.fragment):
                raise ContractViolation("GLABS_FILE_URL_INVALID",task_id,"Result must be an exact local webhook file.")
            binary=self._request("GET",u.path,binary=True)
            metadata=inspect(binary)
            files.append((binary,metadata))
        return files
    def stop(self,task_id):
        if not re.fullmatch(r"[a-fA-F0-9]{8}",task_id):
            raise ContractViolation("GLABS_TASK_ID_INVALID","task","Invalid task identifier.")
        _,info=self._request("POST","/api/stop/"+task_id,body={})
        if task_id not in info.get("stopped",[]) and task_id not in info.get("skipped",[]):
            raise ContractViolation("GLABS_STOP_UNCONFIRMED",task_id,"No task-specific stop evidence.")
        return info
