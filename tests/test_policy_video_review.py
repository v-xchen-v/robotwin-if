"""Exercise review persistence and the actual HTTP/media boundary without a GPU."""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("policy_video_review", ROOT / "tools/policy-video-review/server.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class VideoReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / "archive"
        self.first = self.episode("hy_vla", "pick_diverse_object", 100052, True)
        self.second = self.episode("dm05", "pick_diverse_object", 100052, False)
        self.archived = self.episode("xvla", "grasp_cube_approach", 200000, False)
        # A failed retry lives outside the canonical tree and must not duplicate a row.
        duplicate = self.run / "batches/session/hy_vla/pick_diverse_object"
        duplicate.mkdir(parents=True)
        (duplicate / "pick_diverse_object_ep100052_result.json").write_text('{}')
        self.catalog = app.Catalog(self.run)
        self.reviews = app.Reviews(self.root / "annotations/reviews.sqlite3", self.run)
        self.server = app.ReviewServer(("127.0.0.1", 0), self.catalog, self.reviews)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def episode(self, policy, task, seed, success):
        directory = self.run / policy / task
        directory.mkdir(parents=True, exist_ok=True)
        pre = directory / f"{task}_ep{seed}"
        Path(str(pre) + "_result.json").write_text(json.dumps(dict(
            task=task, seed=seed, success=success, status="success" if success else "failure",
            instruction="Pick up the coffee box", mode="seen", action_calls=3)))
        Path(str(pre) + f"_{int(success)}.mp4").write_bytes(b"0123456789abcdefghijklmnopqrstuvwxyz")
        Path(str(pre) + "_status.json").write_text(json.dumps(dict(block=15)))
        return f"{policy}/{task}/{seed}"

    def request(self, path, payload=None, headers=None, method=None):
        body = json.dumps(payload).encode() if payload is not None else None
        h = {"Content-Type": "application/json", "X-Review-Token": self.server.token}
        h.update(headers or {})
        req = Request(self.base + path, data=body, headers=h, method=method)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.headers, response.read()

    def save(self, identifier=None, label="failure", revision=0, notes="松爪后滑落"):
        identifier = identifier or self.first
        return self.request("/api/review", dict(id=identifier, label=label, notes=notes,
                            revision=revision, source_signature=self.catalog.rows[identifier]["source_signature"]))

    def test_index_uses_canonical_runs_and_has_original_verdict_and_block(self):
        status, _, body = self.request("/api/episodes")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["episodes"]), 3)
        row = next(r for r in data["episodes"] if r["id"] == self.first)
        self.assertEqual((row["automatic"], row["block"], row["verdict"]), ("success", 15, "unreviewed"))
        self.assertEqual(sum(r["archived"] for r in data["episodes"]), 1)

    def test_manual_disagreement_persists_without_modifying_archive(self):
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.rglob('*') if p.is_file()}
        status, _, body = self.save()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["verdict"], "false_positive")
        restored = app.Reviews(self.reviews.path, self.run)
        self.assertEqual(restored.all()[self.first]["label"], "failure")
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(self.save(self.second, "success")[0], 200)
        _, _, export = self.request("/api/export.json?only=disagreements")
        self.assertEqual({r["verdict"] for r in json.loads(export)}, {"false_positive", "false_negative"})

    def test_uncertain_reset_and_history_do_not_become_false_disagreements(self):
        self.save(label="uncertain")
        _, _, exported = self.request("/api/export.json?only=disagreements")
        self.assertEqual(json.loads(exported), [])
        self.assertEqual(self.save(label="unreviewed", revision=1)[0], 200)
        history = self.reviews.history(self.first)
        self.assertEqual([r["label"] for r in history], ["unreviewed", "uncertain"])

    def test_concurrent_revision_is_rejected_and_notes_survive(self):
        self.save(notes="first review")
        self.assertEqual(self.save(notes="overwrite", revision=0)[0], 409)
        self.assertEqual(self.reviews.all()[self.first]["notes"], "first review")
        self.assertEqual(self.save(revision=1, notes="revised")[0], 200)
        self.assertEqual(len(self.reviews.history(self.first)), 2)

    def test_replaced_result_requires_new_review_and_excludes_old_disagreement(self):
        self.save()
        path = self.catalog.paths[self.first]["result"]
        data = json.loads(path.read_text()); data["instruction"] = "new checkpoint result"
        path.write_text(json.dumps(data))
        self.assertEqual(self.save(revision=1)[0], 409)
        # Export independently rechecks sources even without clicking Refresh.
        self.assertEqual(json.loads(self.request("/api/export.json?only=disagreements")[2]), [])
        self.assertEqual(self.request("/api/refresh", {})[0], 200)
        _, _, response = self.request("/api/episodes")
        row = next(r for r in json.loads(response)["episodes"] if r["id"] == self.first)
        self.assertEqual(row["verdict"], "stale")
        self.assertEqual(json.loads(self.request("/api/export.json?only=disagreements")[2]), [])
        self.assertEqual(self.save(revision=1)[0], 200)

    def test_video_supports_full_open_ended_suffix_ranges_and_head(self):
        path = self.catalog.rows[self.first]["video_url"]
        for header, expected, content_range in (("bytes=2-5", b"2345", "bytes 2-5/36"),
                                               ("bytes=32-", b"wxyz", "bytes 32-35/36"),
                                               ("bytes=-3", b"xyz", "bytes 33-35/36")):
            status, headers, body = self.request(path, headers={"Range": header})
            self.assertEqual((status, body), (206, expected))
            self.assertEqual(headers["Content-Range"], content_range)
        status, headers, body = self.request(path, method="HEAD")
        self.assertEqual((status, headers["Content-Length"], body), (200, "36", b""))
        self.assertEqual(self.request(path)[2], b"0123456789abcdefghijklmnopqrstuvwxyz")
        for invalid in ("bytes=999-", "bytes=3-1", "bytes=-0", "bytes=0-1,3-4"):
            self.assertEqual(self.request(path, headers={"Range": invalid})[0], 416)

    def test_exports_keep_scope_notes_identity_and_spreadsheet_text(self):
        self.save(notes="=1+1")
        self.save(self.archived, "success")
        rows = list(csv.DictReader(io.StringIO(self.request("/api/export.csv")[2].decode('utf-8-sig'))))
        self.assertEqual(len(rows), 2)
        row = next(r for r in rows if r["id"] == self.first)
        self.assertEqual(row["notes"], "'=1+1")
        self.assertEqual(row["source_signature"], row["review_signature"])
        self.assertEqual(len(json.loads(self.request("/api/export.json?archived=1")[2])), 3)

    def test_retired_spatial_modes_remain_reviewable_and_labels_survive_scope_filter(self):
        identifiers=[]
        for seed,mode in ((100005,"left"),(100006,"right"),(100007,"front"),(100008,"back"),(100009,"on_top")):
            identifier=self.episode("vlact","place_relative",seed,False)
            path=self.run/"vlact/place_relative"/f"place_relative_ep{seed}_result.json"
            record=json.loads(path.read_text());record["mode"]=mode;path.write_text(json.dumps(record))
            identifiers.append(identifier)
        self.catalog.refresh()
        front=identifiers[2]
        signature=self.catalog.rows[front]["source_signature"]
        self.assertEqual(self.save(front,"uncertain")[0],200)
        rows=json.loads(self.request("/api/episodes")[2])["episodes"]
        self.assertEqual({r["mode"] for r in rows if r["task"]=="place_relative" and not r["archived"]}, {"left","right","on_top"})
        current=json.loads(self.request("/api/export.json")[2])
        self.assertNotIn(front,{r["id"] for r in current})
        full=json.loads(self.request("/api/export.json?archived=1")[2])
        saved=next(r for r in full if r["id"]==front)
        self.assertEqual(saved["human"],"uncertain")
        self.assertEqual(self.catalog.rows[front]["source_signature"],signature)

    def test_unknown_files_traversal_and_outside_symlinks_are_not_served(self):
        self.assertEqual(self.request("/media/../../etc/passwd")[0], 404)
        self.assertEqual(self.request("/.git/config")[0], 404)
        self.assertEqual(self.request("/media/" + self.first + "/unknown")[0], 404)
        path = self.catalog.paths[self.first]["video"]
        path.unlink(); path.symlink_to('/etc/passwd')
        self.assertEqual(self.request(self.catalog.rows[self.first]["video_url"])[0], 400)

    def test_writes_require_token_same_origin_and_valid_label(self):
        self.assertEqual(self.request("/api/refresh", {}, headers={"X-Review-Token":"wrong"})[0], 403)
        self.assertEqual(self.request("/api/refresh", {}, headers={"Origin":"https://example.org"})[0], 403)
        self.assertEqual(self.save(label="maybe")[0], 400)
        self.assertEqual(self.save(notes="x" * 10001)[0], 400)
        self.assertFalse(self.reviews.all())

    def test_missing_video_remains_reviewable_and_database_cannot_mix_runs(self):
        self.catalog.paths[self.first]["video"].unlink(); self.catalog.refresh()
        self.assertIsNone(self.catalog.rows[self.first]["video_url"])
        self.assertEqual(self.save(label="uncertain")[0], 200)
        with self.assertRaisesRegex(ValueError, "another run"):
            app.Reviews(self.reviews.path, self.root / 'different-run')


if __name__ == '__main__':
    unittest.main()
