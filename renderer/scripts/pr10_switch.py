"""Only the actual FastAPI G4 scene PATCH may change this synthetic approved source."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.api.server import create_app
from backend.app.projects.storage import ProjectStore
from backend.app.projects.gates import GateService

ROOT=Path(__file__).resolve().parents[2]


def choose(label):
    config=json.loads((ROOT/"renderer"/".artifacts"/"pr10-mask.json").read_text())
    client=TestClient(create_app(config["db"],config["artifactRoot"]))
    project=config["project"]
    store=ProjectStore(config["db"],config["artifactRoot"])
    root=f"/api/v1/projects/{project}/storyboard"
    page=client.get(root+"/scenes").json()
    assert page["scenes"]
    scene=page["scenes"][0]
    layer=next(x for x in scene["layers"] if x["source_asset_slot_id"]==config["g3"]["slot_id"])
    candidate=config["g3"][label]["candidate_id"]
    before={x["gate_id"]:x["approval_id"] for x in _gate_heads(store,project)}
    options=client.get(root+f"/scenes/{scene['scene_id']}/asset-options/{layer['layer_id']}")
    assert options.status_code==200,options.text
    pool=options.json()
    assert candidate in {x["candidate_id"] for x in pool["options"]}
    if layer["asset_id"]!=candidate:
        change=client.patch(root+f"/scenes/{scene['scene_id']}",
            json={"expected_revision":page["project_revision"],
                  "scene_id":scene["scene_id"],
                  "changes":{"layer_edits":[{"layer_id":layer["layer_id"],"approved_asset_id":candidate}]}},
            headers={"Idempotency-Key":f"PR10-synthetic-set-{label}-{page['project_revision']}"})
        assert change.status_code==200,change.text
        assert change.json()["recomputed_setup_ids"]==[scene["setup_id"]]
        new_page=client.get(root+"/scenes").json()
        new_layer=next(x for x in new_page["scenes"][0]["layers"] if x["layer_id"]==layer["layer_id"])
        assert new_layer["asset_id"]==candidate
    if label=="b":
        # G07: a subsequent real operator placement edit must not reset B to A.
        baseline_x=layer["rect_px"]["x"]
        delta=1 if baseline_x+layer["rect_px"]["w"]<1920 else -1
        for step,new_x in (("move",baseline_x+delta),("restore",baseline_x)):
            persisted=client.get(root+"/scenes").json()
            updated=client.patch(root+f"/scenes/{scene['scene_id']}",
                json={"expected_revision":persisted["project_revision"],
                      "scene_id":scene["scene_id"],
                      "changes":{"layer_edits":[{"layer_id":layer["layer_id"],"x_px":new_x}]}},
                headers={"Idempotency-Key":f"PR10-A-B-persist-{step}-{persisted['project_revision']}"})
            assert updated.status_code==200,updated.text
            reread=client.get(root+"/scenes").json()
            reread_layer=next(x for x in reread["scenes"][0]["layers"]
                              if x["layer_id"]==layer["layer_id"])
            assert reread_layer["asset_id"]==candidate,("G4_SELECTED_SOURCE_REVERTED",step)
            assert reread_layer["rect_px"]["x"]==new_x
    after={x["gate_id"]:x["approval_id"] for x in _gate_heads(store,project)}
    assert before==after,"G4 selection must not mint G1/G2/G3 approvals"
    print(json.dumps({"state":"LOCAL_PASS","selection":label,"candidate":candidate,
                      "gate_heads_unchanged":True,"revision":store.revision(project)}))


def _gate_heads(store,project):
    with store._connection() as db:
        return [{"gate_id":x[0],"approval_id":x[1]} for x in db.execute(
            "SELECT gate_id,approval_id FROM gate_heads WHERE project_id=? AND gate_id IN ('G1','G2','G3') ORDER BY gate_id",
            (project,)).fetchall()]


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--selected",choices=["a","b"],required=True)
    choose(p.parse_args().selected)
