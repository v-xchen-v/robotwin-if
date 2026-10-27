"""Pinned source setup and safe reuse, using disposable Git repositories."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts import _task_bridge as bridge

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/_runtime_setup.sh"


class RuntimeSetupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="runtime setup ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "upstream"
        self.git(self.root, "init", "-q", str(self.upstream))
        (self.upstream / "source.txt").write_text("original\n")
        self.git(self.upstream, "add", ".")
        self.git(self.upstream, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "base")
        self.revision = self.git(self.upstream, "rev-parse", "HEAD").stdout.strip()

    def git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              text=True, capture_output=True)

    def helper(self, function, *args, conditional=False):
        command = 'set -euo pipefail; source "$1"; shift; "$@"'
        if conditional:
            command = 'set -euo pipefail; source "$1"; shift; if "$@"; then exit 99; else exit 0; fi'
        return subprocess.run(["bash", "-c", command, "runtime-test", str(HELPER), function,
                               *map(str, args)], text=True, capture_output=True,
                              env=dict(os.environ, GIT_ALLOW_PROTOCOL="file"))

    def project(self):
        project = self.root / "project"
        self.git(self.root, "init", "-q", str(project))
        self.git(project, "update-index", "--add", "--cacheinfo",
                 f"160000,{self.revision},third_party/robotwin")
        self.git(project, "config", "-f", ".gitmodules", "submodule.third_party/robotwin.path",
                 "third_party/robotwin")
        self.git(project, "config", "-f", ".gitmodules", "submodule.third_party/robotwin.url",
                 self.upstream.as_uri())
        return project

    def test_gitlink_installer_and_bridge_share_the_same_pins(self):
        pins = json.loads((ROOT / "scripts/runtime_pins.json").read_text())
        self.assertEqual(bridge.LOCKED_ROBOTWIN_COMMIT, pins["robotwin"])
        gitlink = self.git(ROOT, "ls-files", "--stage", "--", "third_party/robotwin").stdout.split()
        self.assertEqual(gitlink[:3], ["160000", pins["robotwin"], "0"])
        result = subprocess.run(["bash", "-c", 'source "$1"; load_runtime_pins "$2"; '
                                  'printf "%s\\n" "$ROBOTWIN_REVISION" "$CUROBO_REVISION"',
                                  "pins", str(HELPER), str(ROOT)], check=True, text=True, capture_output=True)
        self.assertEqual(result.stdout.splitlines(), [pins["robotwin"], pins["curobo"]])

    def test_missing_submodule_initializes_and_existing_local_changes_survive(self):
        project = self.project()
        target = project / "third_party/robotwin"
        first = self.helper("ensure_robotwin_source", project, self.revision)
        self.assertEqual(first.returncode, 0, first.stderr)
        (target / "source.txt").write_text("local UTF-8 patch\n")
        second = self.helper("ensure_robotwin_source", project, self.revision)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((target / "source.txt").read_text(), "local UTF-8 patch\n")

    def test_mismatched_gitlink_stops_before_clone(self):
        project = self.project()
        result = self.helper("ensure_robotwin_source", project, "0" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gitlink", result.stderr)
        self.assertFalse((project / "third_party/robotwin").exists())

    def test_existing_wrong_robotwin_revision_is_not_switched(self):
        project = self.project()
        result = self.helper("ensure_robotwin_source", project, self.revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        target = project / "third_party/robotwin"
        (target / "source.txt").write_text("other revision\n")
        self.git(target, "add", ".")
        self.git(target, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "other")
        actual = self.git(target, "rev-parse", "HEAD").stdout
        result = self.helper("ensure_robotwin_source", project, self.revision)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(target, "rev-parse", "HEAD").stdout, actual)

    def test_curobo_fetches_exact_pin_then_reuses_offline_and_preserves_local_files(self):
        target = self.root / "runtime/envs/curobo"
        first = self.helper("ensure_curobo_source", target, self.upstream.as_uri(), self.revision)
        self.assertEqual(first.returncode, 0, first.stderr)
        (target / "local-cache.bin").write_bytes(b"keep")
        second = self.helper("ensure_curobo_source", target, "file:///does-not-exist", self.revision)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((target / "local-cache.bin").read_bytes(), b"keep")
        self.assertEqual(self.git(target, "rev-parse", "HEAD").stdout.strip(), self.revision)

    def test_curobo_wrong_revision_and_dirty_source_are_preserved(self):
        target = self.root / "curobo"
        self.assertEqual(self.helper("ensure_curobo_source", target, self.upstream.as_uri(), self.revision).returncode, 0)
        wrong = self.helper("ensure_curobo_source", target, self.upstream.as_uri(), "0" * 40)
        self.assertNotEqual(wrong.returncode, 0)
        (target / "source.txt").write_text("local patch\n")
        dirty = self.helper("ensure_curobo_source", target, self.upstream.as_uri(), self.revision)
        self.assertNotEqual(dirty.returncode, 0)
        self.assertIn("uncommitted source changes", dirty.stderr)
        self.assertEqual((target / "source.txt").read_text(), "local patch\n")

    def test_curobo_non_repository_is_not_removed(self):
        target = self.root / "curobo"
        target.mkdir()
        (target / "local.txt").write_text("keep")
        result = self.helper("ensure_curobo_source", target, self.upstream.as_uri(), self.revision)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((target / "local.txt").read_text(), "keep")

    def test_failed_curobo_fetch_leaves_no_partial_checkout_even_in_conditional(self):
        target = self.root / "curobo"
        result = self.helper("ensure_curobo_source", target, self.upstream.as_uri(), "0" * 40,
                             conditional=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob("curobo.install-*")), [])

    def test_sources_only_exercises_installer_without_package_commands(self):
        project = self.project()
        scripts = project / "scripts"
        scripts.mkdir()
        shutil.copy2(ROOT / "setup_robotwin.sh", project)
        shutil.copy2(HELPER, scripts)
        (scripts / "runtime_pins.json").write_text(json.dumps(
            {"robotwin": self.revision, "curobo": self.revision}))
        self.assertEqual(self.helper("ensure_robotwin_source", project, self.revision).returncode, 0)
        self.assertEqual(self.helper("ensure_curobo_source", project / "third_party/robotwin/envs/curobo",
                                     self.upstream.as_uri(), self.revision).returncode, 0)
        bins = self.root / "bin"
        bins.mkdir()
        for name in ("sudo", "conda", "pip"):
            executable = bins / name
            executable.write_text('#!/bin/sh\necho unexpected-package-command >&2\nexit 77\n')
            executable.chmod(0o755)
        result = subprocess.run(["bash", str(project / "setup_robotwin.sh"), "--sources-only"],
                                env=dict(os.environ, PATH=str(bins) + os.pathsep + os.environ["PATH"]),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Pinned source checkouts are ready", result.stdout)


if __name__ == "__main__":
    unittest.main()
