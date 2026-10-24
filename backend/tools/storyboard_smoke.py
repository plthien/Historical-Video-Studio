"""B2-05 real SQLite/G4 host-authorized API regression, SYNTHETIC inputs only."""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from backend.app.api.server import create_app
from backend.app.director import draft
from backend.app.director.fingerprint import canonical
from backend.app.projects.storage import ProjectStore

ROOT = Path(__file__).resolve().parents[2]

def main():
    source = ROOT / "renderer" / ".artifacts" / "approved-player-test"
    assert (source / "g4.sqlite").is_file(), "Run native Windows prepare_host_fixture first"
    with TemporaryDirectory(prefix="hvs-b2-storyboard-") as directory:
        dest = Path(directory)
        shutil.copy2(source / "g4.sqlite", dest / "g4.sqlite")
        shutil.copytree(source / "artifacts", dest / "artifacts")
        store = ProjectStore(dest / "g4.sqlite", dest / "artifacts")
        project = "proj_001"
        before = draft.load(store, project)
        original_revision = store.revision(project)
        before_heads = draft.current_gate_heads(store, project)
        assert len(before["timeline"]["scenes"]) >= 2
        first, second = before["timeline"]["scenes"][:2]
        keys = {"Idempotency-Key": "synthetic-scene-edit-001"}
        payload = {"expected_revision": original_revision,"scene_id": first["scene_id"],
                   "changes":{"variant_id": "B" if first["variant_id"] != "B" else "A"}}
        with TestClient(create_app(dest / "g4.sqlite", dest / "artifacts")) as client:
            scenes=client.get(f"/api/v1/projects/{project}/storyboard/scenes?offset=0&limit=1")
            assert scenes.status_code == 200, scenes.text
            assert scenes.json()["total"] >= 2 and len(scenes.json()["scenes"]) == 1
            old=client.get(f"/api/v1/projects/{project}/storyboard/timeline")
            assert old.status_code==200 and old.json()["draft_manifest_sha256"]==before["manifest_sha256"]
            changed=client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json=payload,headers=keys)
            assert changed.status_code==200,changed.text
            output=changed.json()
            assert output["project_revision"]==original_revision+1
            assert output["stale_gates"]==["G4","G5"]
            assert output["recomputed_setup_ids"]==[first["setup_id"]]
            assert second["setup_id"] in output["retained_setup_ids"]
            assert canonical(output["timeline"]["scenes"][1])==canonical(second)
            assert store.revision(project)==original_revision+1
            assert draft.current_gate_heads(store,project)==before_heads
            dup=client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json=payload,headers=keys)
            assert dup.status_code==200 and dup.json()==output
            assert store.revision(project)==original_revision+1
            revised_layer=output["timeline"]["scenes"][0]["layers"][0]
            rect=revised_layer["rect_px"]
            shifted_x=rect["x"]+1 if rect["x"]+rect["w"]<1920 else rect["x"]-1
            position=client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json={"expected_revision":original_revision+1,"scene_id":first["scene_id"],
                      "changes":{"layer_edits":[{"layer_id":revised_layer["layer_id"],
                                                 "x_px":shifted_x}]}},
                headers={"Idempotency-Key":"synthetic-position-edit-02"})
            assert position.status_code==200,position.text
            positioned=position.json()
            assert positioned["project_revision"]==original_revision+2
            assert positioned["timeline"]["scenes"][0]["layers"][0]["rect_px"]["x"]==shifted_x
            assert canonical(positioned["timeline"]["scenes"][1])==canonical(second)
            assert draft.current_gate_heads(store,project)==before_heads
            crop_layer=positioned["timeline"]["scenes"][0]["layers"][0]
            crop={"x":0.01,"y":0.01,"w":0.98,"h":0.98}
            cropped=client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json={"expected_revision":original_revision+2,"scene_id":first["scene_id"],
                      "changes":{"layer_edits":[{"layer_id":crop_layer["layer_id"],
                                                   "crop_normalized":crop}]}},
                headers={"Idempotency-Key":"synthetic-crop-edit-03"})
            assert cropped.status_code==200,cropped.text
            crop_output=cropped.json()
            assert crop_output["project_revision"]==original_revision+3
            assert crop_output["timeline"]["scenes"][0]["layers"][0]["crop_normalized"]==crop
            assert canonical(crop_output["timeline"]["scenes"][1])==canonical(second)
            assert draft.current_gate_heads(store,project)==before_heads
            # Production camera events must recompile real bounded keyframes,
            # not persist an inert JSON-only scalar edit.
            camera_event = next((e for e in crop_output["timeline"]["scenes"][0]["events"]
                                 if e["preset_id"] in ("camera-push", "camera-pan")), None)
            assert camera_event is not None, "Synthetic G4 fixture requires a registered camera event"
            camera_param = "to_scale" if camera_event["preset_id"] == "camera-push" else "max_translate_px"
            old_param = camera_event["params"][camera_param]
            candidate = 1.1 if camera_param == "to_scale" and old_param != 1.1 else (
                1.12 if camera_param == "to_scale" else
                (min(350, old_param + 1) if old_param < 350 else old_param - 1))
            camera_edit = client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json={"expected_revision":original_revision+3, "scene_id":first["scene_id"],
                      "changes":{"motion_edits":[{"event_id":camera_event["event_id"],
                                                  "preset_id":camera_event["preset_id"],
                                                  "params":{camera_param:candidate}}]}},
                headers={"Idempotency-Key":"synthetic-camera-compiled-07"})
            assert camera_edit.status_code == 200, camera_edit.text
            camera_output = camera_edit.json()
            assert camera_output["project_revision"] == original_revision+4
            assert camera_output["recomputed_setup_ids"] == [first["setup_id"]]
            assert canonical(camera_output["timeline"]["scenes"][1]) == canonical(second)
            changed_camera = camera_output["timeline"]["scenes"][0]
            edited_event = next(e for e in changed_camera["events"] if e["event_id"] == camera_event["event_id"])
            assert edited_event["params"][camera_param] == candidate
            assert changed_camera["camera"]["keyframes"] != crop_output["timeline"]["scenes"][0]["camera"]["keyframes"]
            assert draft.current_gate_heads(store, project) == before_heads
            replay = client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json={"expected_revision":original_revision+3, "scene_id":first["scene_id"],
                      "changes":{"motion_edits":[{"event_id":camera_event["event_id"],
                                                  "preset_id":camera_event["preset_id"],
                                                  "params":{camera_param:candidate}}]}},
                headers={"Idempotency-Key":"synthetic-camera-compiled-07"})
            assert replay.status_code == 200 and replay.json() == camera_output
            assert store.revision(project) == original_revision+4
            # Reedit crop then position, preserving the first overlay and frozen
            # source heads through a real SQLite transaction chain.
            crop2 = {"x":0.02,"y":0.02,"w":0.96,"h":0.96}
            next_crop = client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json={"expected_revision":original_revision+4, "scene_id":first["scene_id"],
                      "changes":{"layer_edits":[{"layer_id":crop_layer["layer_id"],
                                                    "crop_normalized":crop2}]}},
                headers={"Idempotency-Key":"synthetic-second-crop-08"})
            assert next_crop.status_code==200,next_crop.text
            next_position = client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json={"expected_revision":original_revision+5, "scene_id":first["scene_id"],
                      "changes":{"layer_edits":[{"layer_id":revised_layer["layer_id"],
                                                    "x_px":rect["x"]}]}},
                headers={"Idempotency-Key":"synthetic-second-position-09"})
            assert next_position.status_code==200,next_position.text
            final_output = next_position.json()
            assert final_output["timeline"]["scenes"][0]["layers"][0]["crop_normalized"]==crop2
            assert final_output["timeline"]["scenes"][0]["layers"][0]["rect_px"]["x"]==rect["x"]
            assert canonical(final_output["timeline"]["scenes"][1])==canonical(second)
            assert draft.current_gate_heads(store,project)==before_heads
            stale=client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json=payload,headers={"Idempotency-Key":"synthetic-stale-cas-004"})
            assert stale.status_code==409,stale.text
            illegal=client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json={"expected_revision":original_revision+6,"scene_id":first["scene_id"],
                      "changes":{"layer_edits":[{"layer_id": first["layers"][0]["layer_id"],
                                                "approved_asset_id":"candidate_forged"}]}},
                headers={"Idempotency-Key":"synthetic-forged-asset-05"})
            assert illegal.status_code==422,illegal.text
            attempted=client.patch(
                f"/api/v1/projects/{project}/storyboard/scenes/{first['scene_id']}",
                json={"expected_revision":original_revision+6,"scene_id":first["scene_id"],
                      "changes":{"template_id":"T08" if first["template_id"]!="T08" else "T02"}},
                headers={"Idempotency-Key":"synthetic-template-edit-06"})
            assert attempted.status_code==422,attempted.text
            assert store.revision(project)==original_revision+6
            reread=client.get(f"/api/v1/projects/{project}/storyboard/timeline")
            assert reread.status_code==200
            assert reread.json()["timeline"]["dependency_fingerprint"]==final_output["timeline"]["dependency_fingerprint"]
            assert reread.json()["draft_manifest_sha256"]!=before["manifest_sha256"]
        # A cold process must read the newly published immutable G4 manifest.
        reopened=draft.load(ProjectStore(dest/"g4.sqlite",dest/"artifacts"),project)
        assert reopened["revision"]==original_revision+6
        assert reopened["timeline"]["scenes"][0]["layers"][0]["crop_normalized"]==crop2
        assert reopened["timeline"]["scenes"][0]["layers"][0]["rect_px"]["x"]==rect["x"]
        assert canonical(reopened["timeline"]["scenes"][1])==canonical(second)
        print(json.dumps({"status":"LOCAL_PASS","source":"SYNTHETIC_SQLITE_APPROVAL_FIXTURE_NOT_REAL_RIGHTS",
                          "cases":["paged_read","current_manifest","variant_CAS","position_CAS","selective_recompile",
                                   "upstream_heads","idempotent_replay","crop_cold_reload","stale_409","forged_asset_422",
                                   "template_rewrite_422","camera_motion_keys_changed_and_idempotent","repeat_crop_and_position","cold_reload"],
                          "changed_setup_ids": output["recomputed_setup_ids"],
                          "retained_setup_ids": output["retained_setup_ids"],
                          "stale_gates": output["stale_gates"]}))
if __name__=="__main__":
    main()
