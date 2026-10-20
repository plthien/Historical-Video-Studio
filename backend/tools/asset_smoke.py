"""Optional A3 live checks; no paid fallback request without A3-04 authorization."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from backend.app.archives.wikimedia import Wikimedia
from backend.app.archives.loc import LOC
from backend.app.archives.europeana import Europeana
from backend.app.assets.download import download
from backend.app.projects.storage import ProjectStore
from backend.app.contracts import ContractViolation

def run(case,mode):
    if mode!="live":
        raise SystemExit("A3 source live check must use --mode live; offline behavior uses pytest.")
    if case=="glabs-image":
        raise SystemExit("glabs-image: BLOCKED — A3-04 managed fallback authorization not implemented; no paid task sent")
    if case=="archives-all":
        failed=[]
        for name,adapter in (("wikimedia",Wikimedia()),("loc",LOC()),("europeana",Europeana())):
            try:
                page=adapter.search(os.getenv("HVS_A3_LIVE_QUERY","historical map"),page_size=2)
                if not page["candidates"]:
                    raise RuntimeError("No discovered candidates")
                print(name+": LIVE_PASS search "+str(len(page["candidates"]))+" unapproved candidates")
            except (ContractViolation,RuntimeError) as exc:
                print(name+": BLOCKED/FAIL "+(exc.code if isinstance(exc,ContractViolation) else str(exc)))
                failed.append(name)
        if failed:
            raise SystemExit(2)
        return
    if case=="archive-original-download":
        provider=os.getenv("HVS_A3_LIVE_PROVIDER")
        item_id=os.getenv("HVS_A3_LIVE_ITEM_ID")
        if not provider or not item_id:
            raise SystemExit("archive-original-download: BLOCKED — explicit provider/item identity required")
        adapters={"wikimedia_commons":Wikimedia,"loc":LOC,"europeana":Europeana}
        if provider not in adapters:
            raise SystemExit("archive-original-download: provider not supported")
        candidate=adapters[provider]().hydrate(item_id)
        raw,info,url=download(candidate)
        with tempfile.TemporaryDirectory() as dirname:
            store=ProjectStore(Path(dirname)/"state.sqlite",Path(dirname)/"bytes")
            sha=store.put_artifact(raw,"original")
            opened=ProjectStore(Path(dirname)/"state.sqlite",Path(dirname)/"bytes")
            if opened.get_artifact(sha)!=raw or sha!=hashlib.sha256(raw).hexdigest():
                raise RuntimeError("Persisted source bytes were corrupted")
        print("archive-original-download: LIVE_PASS verified original sha="+sha+
              " mime="+info["mime_type"]+" bytes="+str(len(raw)))
        return
    raise SystemExit("Unsupported A3 live case")
