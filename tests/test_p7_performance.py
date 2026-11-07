import json
import sys
import tempfile
import unittest
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "p7"
sys.path.insert(0, str(EXAMPLES))
from performance import ContractError, load_contract, validate_contract


def sample():
    return json.loads((EXAMPLES / "second-light.performance.json").read_text())


class PerformanceContractTests(unittest.TestCase):
    def test_approved_second_light_contract_passes(self):
        self.assertEqual(validate_contract(sample())["frame_count"], 144)

    def test_arbitrary_root_instruction_is_rejected(self):
        contract = sample()
        contract["shell"] = "touch /tmp/unsafe"
        with self.assertRaises(ContractError):
            validate_contract(contract)

    def test_unknown_rig_and_action_are_rejected(self):
        for change in (lambda c: c["character"].update(preset="other"),
                       lambda c: c["actions"][0].update(type="run_python")):
            contract = sample()
            change(contract)
            with self.assertRaises(ContractError):
                validate_contract(contract)

    def test_external_assets_wrong_frame_range_and_camera_are_rejected(self):
        mutations = (
            lambda c: c.update(assets=["/private/reference.png"]),
            lambda c: c["actions"][2].update(end_frame=145),
            lambda c: c["camera"].update(lens_mm=120),
        )
        for mutate in mutations:
            contract = sample()
            mutate(contract)
            with self.assertRaises(ContractError):
                validate_contract(contract)

    def test_contact_must_precede_lamp_response(self):
        contract = sample()
        contract["actions"][5]["start_frame"] = 110
        with self.assertRaises(ContractError):
            validate_contract(contract)

    def test_paths_reject_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / "approved"
            root.mkdir()
            good = root / "good.json"
            good.write_text(json.dumps(sample()))
            self.assertEqual(load_contract(good, root)["performance_id"], "the_second_light_v1")
            link = root / "link.json"
            link.symlink_to(good)
            with self.assertRaises(ContractError):
                load_contract(link, root)
            with self.assertRaises(ContractError):
                load_contract(root / ".." / "approved" / "good.json", root)


if __name__ == "__main__":
    unittest.main()
