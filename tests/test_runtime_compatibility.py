import subprocess
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.compatibility import (
    CompatibilityError,
    check_platform,
    check_requirements,
    check_tools,
    load_manifest,
    resolve_python,
)


class CompatibilityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest()

    def test_manifest_dependency_groups_match_requirements_file(self):
        check_requirements(self.manifest)

    def test_preferred_supported_python_is_selected(self):
        paths = {"python3.11": "/py311", "python3.12": "/py312"}
        versions = {"/py311": "Python 3.11.9", "/py312": "Python 3.12.4"}

        def runner(args, **_kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=versions[args[0]], stderr="")

        executable, version = resolve_python(
            self.manifest, candidates=["python3.12", "python3.11"],
            which=lambda name: paths.get(name), runner=runner,
        )
        self.assertEqual((executable, version), ("/py311", "3.11"))

    def test_unsupported_python_explains_supported_install_route(self):
        def runner(args, **_kwargs):
            return subprocess.CompletedProcess(args, 0, stdout="Python 3.13.1", stderr="")

        with self.assertRaisesRegex(CompatibilityError, "brew install python@3.11"):
            resolve_python(self.manifest, candidates=["python3"],
                           which=lambda _name: "/python", runner=runner)

    def test_macos_platform_minimum_and_architecture(self):
        check_platform(self.manifest, "macos", "14.0", "aarch64")
        with self.assertRaisesRegex(CompatibilityError, "macOS 14.0 or later"):
            check_platform(self.manifest, "macos", "13.6", "arm64")
        with self.assertRaisesRegex(CompatibilityError, "Unsupported macos architecture"):
            check_platform(self.manifest, "macos", "14.0", "ppc64")

    def test_tool_minimum_version_includes_patch_component(self):
        tools = {"node": "/node", "npm": "/npm", "rustc": "/rustc"}
        versions = {"/node": "v20.12.1", "/npm": "10.4.0", "/rustc": "rustc 1.77.1 (abc)"}

        def runner(args, **_kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=versions[args[0]], stderr="")

        with self.assertRaisesRegex(CompatibilityError, "rust 1.77.1 is below"):
            check_tools(self.manifest, which=lambda name: tools.get(name), runner=runner)


if __name__ == "__main__":
    unittest.main()
