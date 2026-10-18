"""Static cross-artifact checks for Step 01/02 design freeze. Not runtime tests."""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = ROOT / "docs" / "step01-02"


class _Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tabs = []
        self.actions = []
    def handle_starttag(self, tag, attrs):
        if tag != "button":
            return
        attributes = dict(attrs)
        if "data-tab" in attributes:
            self.tabs.append(attributes["data-tab"])
        if "data-action" in attributes:
            self.actions.append(attributes["data-action"])


class DesignIntegrityTests(unittest.TestCase):
    def test_five_design_documents_exist(self):
        for name in [
            "01_PRODUCT_SPEC.md", "02_SYSTEM_ARCHITECTURE.md",
            "03_VISUAL_PRODUCTION_SPEC.md", "04_DATA_CONTRACTS_AND_GATES.md",
            "05_IMPLEMENTATION_PLAN.md",
        ]:
            self.assertTrue((DOCUMENTS / name).exists(), name)
            self.assertGreater((DOCUMENTS / name).stat().st_size, 5000, name)

    def test_ten_template_ids_documented(self):
        content = (DOCUMENTS / "03_VISUAL_PRODUCTION_SPEC.md").read_text(encoding="utf-8")
        content += (DOCUMENTS / "TEMPLATE_DESIGN_SHEETS_T05_T10.md").read_text(encoding="utf-8")
        for i in range(1, 11):
            self.assertRegex(content, r"\bT" + f"{i:02}" + r"\b")

    def test_ui_mockup_has_six_workspaces_and_gate_controls(self):
        html = (ROOT / "ui" / "mockups" / "index.html").read_text(encoding="utf-8")
        parser = _Controls()
        parser.feed(html)
        self.assertEqual(set(parser.tabs), {"project", "story", "voice", "assets", "storyboard", "delivery"})
        for action in ["g1", "g2", "g3", "g4", "g5", "resolution", "candidateApprove", "sceneEdit", "render"]:
            self.assertIn(action, parser.actions)
        self.assertIn("MANAGED", html.upper())
        self.assertIn("simul", html.lower())

    def test_openapi_yaml_parses_with_local_schema_refs(self):
        api = ROOT / "contracts" / "openapi.yaml"
        data = yaml.safe_load(api.read_text(encoding="utf-8"))
        self.assertEqual(data["openapi"], "3.1.0")
        self.assertIn("/projects/{project_id}/gates/{gate_id}/decision", data["paths"])
        self.assertIn("/projects/{project_id}/assets/{requirement_id}/resolve", data["paths"])
        self.assertIn("/jobs/{job_id}/cancel", data["paths"])
        ref_matches = re.findall(r"\$ref:\s*([^\n]+)", api.read_text(encoding="utf-8"))
        for ref in ref_matches:
            ref = ref.strip().strip("'").strip('"')
            if not ref.startswith("#/"):
                self.assertTrue((api.parent / ref).resolve().exists(), ref)

    def test_no_extra_human_gate_in_spec(self):
        a = (DOCUMENTS / "01_PRODUCT_SPEC.md").read_text(encoding="utf-8")
        for gate in ("G1", "G2", "G3", "G4", "G5"):
            self.assertIn(gate, a)
        self.assertIn("alignment", a.lower())
        self.assertIn("G2-aligned + G3-approved", (DOCUMENTS / "02_SYSTEM_ARCHITECTURE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
