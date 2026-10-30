#!/usr/bin/env python3
"""CPU-only review of local results or a pinned Azure backup. Original artifacts are read-only."""
import argparse
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent
POLICIES = dict(xvla="X-VLA", lingbot_va="LingBot-VA", lingbot_vla="LingBot-VLA",
                vlact="VLAct", dm05="DM05", hy_vla="Hy-VLA")
TASKS = ("press_lift_stapler", "pick_diverse_object", "attribute_select", "arm_select",
         "stack_sequence", "place_relative", "bottle_verb", "grasp_cube_approach")
LABELS = ("success", "failure", "uncertain", "unreviewed")
ASSETS = {"result": "_result.json", "summary": "_summary.json", "oracle": "_oracle.json",
          "diagnostics": "_diagnostics.json", "status": "_status.json",
          "provenance": "_provenance.json", "log": ".log", "image": "_step0000.png"}


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inside(path, root):
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Artifact points outside the selected run")
    return resolved


def verdict(row, review):
    if not review or review["label"] == "unreviewed":
        return "unreviewed"
    if review["source_signature"] != row["source_signature"]:
        return "stale"
    if review["label"] == "uncertain":
        return "uncertain"
    if row["automatic"] not in ("success", "failure"):
        return "unscored"
    if row["automatic"] == review["label"]:
        return "agree"
    return "false_positive" if row["automatic"] == "success" else "false_negative"


def score_overview(rows):
    """Automatic labels only; Overall equally weights tasks, never episodes."""
    rows = [r for r in rows if not r["archived"]]
    tasks = sorted({r["task"] for r in rows}, key=lambda t: (TASKS.index(t) if t in TASKS else len(TASKS), t))
    def counts(group):
        n = len(group)
        success = sum(r["automatic"] == "success" for r in group)
        errors = sum(r["automatic"] == "error" for r in group)
        rate = success / n if n and not errors else None
        return dict(success=success, total=n, errors=errors, rate=rate,
                    percent=round(100 * rate, 1) if rate is not None else None)
    policies = {}
    for policy in POLICIES:
        own = [r for r in rows if r["policy"] == policy]
        if not own:
            continue
        scores = {}
        for task in tasks:
            group = [r for r in own if r["task"] == task]
            scores[task] = dict(**counts(group), modes={mode: counts([r for r in group if r["mode"] == mode])
                                for mode in sorted({r["mode"] for r in group if r["mode"]})})
        rates = [s["rate"] for s in scores.values()]
        overall = sum(rates) / len(rates) if rates and all(r is not None for r in rates) else None
        policies[policy] = dict(tasks=scores, overall=overall,
                               overall_percent=round(100 * overall, 1) if overall is not None else None)
    return dict(tasks=tasks, policies=policies)


class Catalog:
    def __init__(self, run):
        self.run = run.resolve(strict=True)
        self.lock = threading.RLock()
        self.rows, self.paths, self.warnings = {}, {}, []
        self.probes = {}
        self.refresh()

    def ensure_file(self, path):
        return inside(path, self.run)

    def signature(self, files):
        evidence = {}
        for kind in ("result", "provenance", "video"):
            if kind in files:
                p = inside(files[kind], self.run)
                s = p.stat()
                evidence[kind] = (p.name, s.st_size, s.st_mtime_ns,
                                  digest(p.read_bytes()) if kind != "video" else None)
        return digest(json.dumps(evidence, sort_keys=True).encode())

    def refresh(self):
        rows, paths, warnings = {}, {}, []
        plan = read_json(self.run / "plan.json", {})
        block_indices = {}
        for spec in plan.get("tasks", []):
            size = len(spec.get("modes", {}))
            if size:
                block_indices.update({(spec["task"], seed): i // size
                                      for i, seed in enumerate(spec.get("seeds", []))})
        # Only canonical policy/task directories: never batches, incoming or old reruns.
        for policy in POLICIES:
            for directory in sorted((self.run / policy).glob("*")):
                if not directory.is_dir():
                    continue
                task = directory.name
                for result_path in sorted(directory.glob(f"{task}_ep*_result.json")):
                    try:
                        record = read_json(inside(result_path, self.run))
                        seed = record["seed"]
                        if type(seed) is not int or seed < 0 or record["task"] != task:
                            raise ValueError("Result identity does not match task directory")
                        prefix = f"{task}_ep{seed}"
                        if result_path.name != prefix + "_result.json":
                            raise ValueError("Result filename does not match seed")
                        files = {key: inside(directory / (prefix + suffix), self.run)
                                 for key, suffix in ASSETS.items() if (directory / (prefix + suffix)).is_file()}
                        videos = list(directory.glob(prefix + "_[01].mp4"))
                        status = record.get("status")
                        success = record.get("success")
                        automatic = status if status in ("success", "failure") and type(success) is bool and success == (status == "success") else "error"
                        preferred = directory / (prefix + f"_{int(success is True)}.mp4")
                        if preferred in videos:
                            files["video"] = inside(preferred, self.run)
                        elif len(videos) == 1:
                            files["video"] = inside(videos[0], self.run)
                        provenance = read_json(files["provenance"], {}) if "provenance" in files else {}
                        status_info = read_json(files["status"], {}) if "status" in files else {}
                        identifier = f"{policy}/{task}/{seed}"
                        row = dict(id=identifier, policy=policy, task=task, seed=seed,
                                   mode=record.get("mode"), instruction=record.get("instruction") or "",
                                   automatic=automatic, archived=(task == "grasp_cube_approach" or
                                       (task == "place_relative" and record.get("mode") in ("front", "back"))),
                                   block=block_indices.get((task, seed), provenance.get("formal_block", status_info.get("block"))),
                                   steps=record.get("action_calls"), step_limit=record.get("step_limit"),
                                   termination=record.get("termination"),
                                   video_url=self.url(identifier, "video") if "video" in files else None,
                                   image_url=self.url(identifier, "image") if "image" in files else None,
                                   source_signature=self.signature(files), result_sha256=digest(result_path.read_bytes()))
                        rows[identifier], paths[identifier] = row, files
                    except (OSError, ValueError, KeyError, TypeError) as exc:
                        warnings.append(f"{result_path.relative_to(self.run)}: {exc}")
        if not rows:
            raise ValueError("No <policy>/<task>/<task>_ep<seed>_result.json episodes found")
        with self.lock:
            self.rows, self.paths, self.warnings = rows, paths, warnings

    @staticmethod
    def url(identifier, asset):
        return "/media/" + quote(identifier, safe="/") + "/" + asset

    def probe(self, path):
        if not path:
            return {}
        key = (str(path), path.stat().st_mtime_ns)
        with self.lock:
            if key in self.probes:
                return self.probes[key]
        try:
            proc = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                   "-show_entries", "stream=width,height,avg_frame_rate,nb_frames:format=duration",
                                   "-of", "json", str(path)], capture_output=True, text=True, timeout=8, check=True)
            data = json.loads(proc.stdout)
            stream = data["streams"][0]
            result = dict(width=stream["width"], height=stream["height"],
                          fps=float(Fraction(stream["avg_frame_rate"])),
                          duration=float(data.get("format", {}).get("duration", 0)))
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, ZeroDivisionError):
            result = {}  # Playback still works; never use rollout throughput as video FPS.
        with self.lock:
            self.probes[key] = result
        return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OSError("Azure blob redirects are not accepted")


class AzureCatalog(Catalog):
    """Pinned Azure backup, downloaded per asset into a separate SHA-verified cache.

    Only the CLI backend sees Azure tokens. The browser uses the normal local
    media endpoints, including Range requests after the requested video is cached.
    """
    def __init__(self, base_url, checksums_sha256, cache):
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not re.fullmatch(r"[a-z0-9]+\.blob\.core\.windows\.net", parsed.netloc)
                or parsed.query or parsed.fragment or not parsed.path.strip("/")):
            raise ValueError("Expected an Azure Blob HTTPS bundle URL without credentials")
        self.source_url = base_url.rstrip("/")
        self.pinned_sha256 = checksums_sha256
        self.run = cache.resolve()
        self.run.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.auth_lock = threading.Lock()
        self.download_locks = {}
        self.token, self.expires = None, 0
        self.verified, self.probes = {}, {}
        self.hashes = {"SHA256SUMS": checksums_sha256}
        self.rows, self.paths, self.warnings = {}, {}, []
        self.refresh()

    def access_token(self):
        with self.auth_lock:
            if self.expires < time.time() + 120:
                try:
                    proc = subprocess.run(["az", "account", "get-access-token", "--resource", "https://storage.azure.com/", "-o", "json"],
                                          capture_output=True, text=True, timeout=45)
                except subprocess.TimeoutExpired:
                    raise OSError("Azure token request timed out; check az login on the server") from None
                if proc.returncode:
                    raise OSError("Azure authentication failed. Run az login using a browser on the server.")
                data = json.loads(proc.stdout)
                self.token, self.expires = data["accessToken"], float(data["expires_on"])
            return self.token

    def ensure_file(self, path):
        path = inside(path, self.run)
        relative = path.relative_to(self.run).as_posix()
        expected = self.hashes[relative]  # Whitelisted, frozen archive assets only.
        with self.lock:
            lock = self.download_locks.setdefault(relative, threading.Lock())
        with lock:
            if path.is_file():
                stat = path.stat()
                fingerprint = (stat.st_size, stat.st_mtime_ns)
                if self.verified.get(relative) == fingerprint or digest(path.read_bytes()) == expected:
                    self.verified[relative] = fingerprint
                    return path
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".download-" + secrets.token_hex(6))
            try:
                request = Request(self.source_url + "/" + quote(relative, safe="/"), headers={
                    "Authorization": "Bearer " + self.access_token(), "x-ms-version": "2023-11-03"})
                checksum = hashlib.sha256()
                with build_opener(NoRedirect).open(request, timeout=60) as response, temp.open("wb") as stream:
                    # Azure blobs do not redirect; never accept an unexpected response origin.
                    if urlsplit(response.url).netloc != urlsplit(self.source_url).netloc:
                        raise OSError("Unexpected Azure response origin")
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
                        checksum.update(chunk)
                if checksum.hexdigest() != expected:
                    raise ValueError(f"Azure checksum mismatch: {relative}")
                temp.replace(path)
                stat = path.stat()
                self.verified[relative] = (stat.st_size, stat.st_mtime_ns)
            except HTTPError as exc:
                raise OSError(f"Azure HTTP {exc.code} for {relative}; check Blob read access / az login") from None
            finally:
                temp.unlink(missing_ok=True)
            return path

    def signature(self, files):
        return digest(json.dumps({key: self.hashes[p.relative_to(self.run).as_posix()]
                                  for key, p in files.items() if key in ("result", "provenance", "video")},
                                 sort_keys=True).encode())

    def refresh(self):
        inventory = self.ensure_file(self.run / "SHA256SUMS").read_text()
        for line in inventory.splitlines():
            checksum, relative = line.split("  ", 1)
            if (not re.fullmatch(r"[0-9a-f]{64}", checksum) or relative.startswith("/")
                    or ".." in Path(relative).parts or "\\" in relative or relative == "SHA256SUMS"):
                raise ValueError("Invalid Azure checksum inventory")
            inside(self.run / relative, self.run)
            self.hashes[relative] = checksum
        index = self.ensure_file(self.run / "episode-index.csv")
        plan = read_json(self.ensure_file(self.run / "evaluation/plan.json"))
        blocks = {(spec["task"], seed): i // len(spec["modes"])
                  for spec in plan["tasks"] for i, seed in enumerate(spec["seeds"])}
        rows, paths = {}, {}
        with index.open(newline="") as stream:
            for record in csv.DictReader(stream):
                policy, task, seed = record["policy"], record["task"], int(record["seed"])
                prefix = f"evaluation/{policy}/{task}/{task}_ep{seed}"
                # v1 exported verbose *_path columns; v2 uses record/video.
                record_file = record.get("record", record.get("record_path"))
                video_file = record.get("video", record.get("video_path"))
                if (policy not in POLICIES or not re.fullmatch(r"[a-z_0-9]+", task) or seed < 0
                        or record_file != prefix + "_result.json" or record["success"] not in ("0", "1")
                        or video_file != prefix + "_" + record["success"] + ".mp4"):
                    raise ValueError("Invalid Azure episode index")
                files = {key: self.run / (prefix + suffix) for key, suffix in ASSETS.items()
                         if prefix + suffix in self.hashes}
                if video_file in self.hashes:
                    files["video"] = self.run / video_file
                identifier = f"{policy}/{task}/{seed}"
                if identifier in rows:
                    raise ValueError("Duplicate Azure episode")
                rows[identifier] = dict(id=identifier, policy=policy, task=task, seed=seed, mode=record["mode"],
                    instruction=record["instruction"], automatic="success" if record["success"] == "1" else "failure",
                    archived=(task == "grasp_cube_approach" or (task == "place_relative" and record["mode"] in ("front", "back"))),
                    block=blocks.get((task, seed)), steps=int(record["action_calls"]) if record.get("action_calls") else None,
                    step_limit=int(record["step_limit"]) if record.get("step_limit") else None,
                    termination=record.get("termination"),
                    video_url=self.url(identifier, "video") if "video" in files else None,
                    image_url=self.url(identifier, "image") if "image" in files else None,
                    source_signature=self.signature(files), result_sha256=self.hashes[record_file])
                paths[identifier] = files
        if not rows:
            raise ValueError("Empty Azure episode index")
        with self.lock:
            self.rows, self.paths = rows, paths


class Reviews:
    def __init__(self, path, run):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                  id TEXT PRIMARY KEY, label TEXT NOT NULL, notes TEXT NOT NULL,
                  source_signature TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history (
                  event INTEGER PRIMARY KEY, id TEXT NOT NULL, label TEXT NOT NULL, notes TEXT NOT NULL,
                  source_signature TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('run', ?)", (str(run),))
            if db.execute("SELECT value FROM metadata WHERE key='run'").fetchone()[0] != str(run):
                raise ValueError("Review database belongs to another run")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def all(self):
        with self.connect() as db:
            return {r["id"]: dict(r) for r in db.execute("SELECT * FROM reviews")}

    def history(self, identifier):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM history WHERE id=? ORDER BY event DESC", (identifier,))]

    def save(self, identifier, label, notes, signature, revision):
        if label not in LABELS or not isinstance(notes, str) or len(notes) > 10000:
            raise ValueError("Invalid label or note (maximum 10000 characters)")
        if type(revision) is not int or revision < 0:
            raise ValueError("Invalid review revision")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT revision FROM reviews WHERE id=?", (identifier,)).fetchone()
            if revision != (old[0] if old else 0):
                raise Conflict("This review changed in another tab. Refresh before saving.")
            row = dict(id=identifier, label=label, notes=notes, source_signature=signature,
                       revision=revision + 1, updated_at=datetime.now(timezone.utc).isoformat())
            values = tuple(row.values())
            db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?)", values)
            db.execute("INSERT INTO history(id,label,notes,source_signature,revision,updated_at) VALUES (?,?,?,?,?,?)", values)
            return row


class Conflict(Exception):
    pass


def byte_range(header, size):
    if not header:
        return 0, size - 1
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError("Unsupported byte range")
    start, end = match.groups()
    if not start:
        if int(end) <= 0:
            raise ValueError("Invalid suffix range")
        return max(0, size - int(end)), size - 1
    start, end = int(start), min(int(end), size - 1) if end else size - 1
    if start > end or start >= size:
        raise ValueError("Range outside file")
    return start, end


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, catalog, reviews):
        self.catalog, self.reviews = catalog, reviews
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if args and str(args[1]) not in ("200", "206", "304"):
            super().log_message(fmt, *args)

    def respond(self, body, kind="application/json; charset=utf-8", status=200, extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self.get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except KeyError:
            self.respond({"error": "Episode or asset not found"}, status=404)
        except (OSError, ValueError) as exc:
            self.respond({"error": str(exc)}, status=400)

    def get(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        catalog, reviews = self.server.catalog, self.server.reviews
        if url.path == "/favicon.ico":
            return self.respond(b"", "image/x-icon", status=204)
        if url.path in ("/", "/index.html", "/app.js", "/style.css"):
            name = url.path.lstrip("/") or "index.html"
            kind = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[Path(name).suffix]
            return self.respond((STATIC / name).read_bytes(), kind + "; charset=utf-8")
        if url.path == "/api/episodes":
            saved = reviews.all()
            with catalog.lock:
                rows = [dict(row, review=saved.get(row["id"]), verdict=verdict(row, saved.get(row["id"])))
                        for row in catalog.rows.values()]
                return self.respond(dict(run=catalog.run.name, run_path=str(catalog.run),
                                         review_path=str(reviews.path), policies=POLICIES, tasks=TASKS,
                                         source=getattr(catalog, "source_url", "local"),
                                         scores=score_overview(rows), episodes=rows,
                                         warnings=catalog.warnings, token=self.server.token))
        if url.path == "/api/episode":
            identifier = query.get("id", [""])[0]
            with catalog.lock:
                row, files = catalog.rows[identifier].copy(), catalog.paths[identifier].copy()
            data = {key: read_json(catalog.ensure_file(files[key])) for key in
                    ("result", "summary", "oracle", "diagnostics", "provenance") if key in files}
            record = data.get("result", {})
            row.update(steps=record.get("action_calls"), step_limit=record.get("step_limit"), termination=record.get("termination"))
            video = catalog.ensure_file(files["video"]) if "video" in files else None
            return self.respond(dict(episode=row, data=data, video=catalog.probe(video),
                                     history=reviews.history(identifier),
                                     artifacts={key: catalog.url(identifier, key) for key in files}))
        if url.path.startswith("/media/"):
            identifier, asset = unquote(url.path[len("/media/"):]).rsplit("/", 1)
            with catalog.lock:
                path = catalog.paths[identifier][asset]
            return self.send_file(catalog.ensure_file(path))
        if url.path in ("/api/export.csv", "/api/export.json"):
            # Exports must not classify a replaced checkpoint/video using old labels.
            catalog.refresh()
            saved = reviews.all()
            mismatches = query.get("only", [""])[0] == "disagreements"
            include_archived = query.get("archived", ["0"])[0] == "1"
            rows = []
            with catalog.lock:
                for row in catalog.rows.values():
                    if row["archived"] and not include_archived:
                        continue
                    review = saved.get(row["id"], {})
                    state = verdict(row, review)
                    if mismatches and state not in ("false_positive", "false_negative"):
                        continue
                    rows.append(dict(run=str(catalog.run), id=row["id"], policy=row["policy"], task=row["task"],
                                     seed=row["seed"], block=row["block"], mode=row["mode"], instruction=row["instruction"],
                                     automatic=row["automatic"], human=review.get("label", "unreviewed"), verdict=state,
                                     notes=review.get("notes", ""), updated_at=review.get("updated_at", ""),
                                     source_signature=row["source_signature"], review_signature=review.get("source_signature", ""),
                                     result_sha256=row["result_sha256"], video=str(catalog.paths[row["id"]].get("video", ""))))
            if url.path.endswith(".json"):
                return self.respond(rows, extra={"Content-Disposition": 'attachment; filename="video-reviews.json"'})
            stream = io.StringIO(newline="")
            fields = list(rows[0]) if rows else ["id", "automatic", "human", "verdict", "notes"]
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            for row in rows:
                # Prevent user notes/instructions from becoming spreadsheet formulas.
                writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v
                                 for k, v in row.items()})
            return self.respond(("\ufeff" + stream.getvalue()).encode(), "text/csv; charset=utf-8",
                                extra={"Content-Disposition": 'attachment; filename="video-reviews.csv"'})
        self.respond({"error": "Not found"}, status=404)

    def send_file(self, path):
        with path.open("rb") as stream:
            size = path.stat().st_size
            try:
                start, end = byte_range(self.headers.get("Range"), size)
            except ValueError:
                return self.respond({"error": "Range not satisfiable"}, status=416,
                                    extra={"Content-Range": f"bytes */{size}"})
            partial = self.headers.get("Range") is not None
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", {".mp4": "video/mp4", ".png": "image/png", ".json": "application/json"}.get(path.suffix, "text/plain; charset=utf-8"))
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-cache")
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            stream.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = stream.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_POST(self):
        try:
            if not secrets.compare_digest(self.headers.get("X-Review-Token", ""), self.server.token):
                return self.respond({"error": "Invalid review token"}, status=403)
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return self.respond({"error": "Cross-origin write rejected"}, status=403)
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 65536:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            catalog, reviews = self.server.catalog, self.server.reviews
            if self.path == "/api/refresh":
                catalog.refresh()
                return self.respond({"ok": True})
            if self.path != "/api/review":
                return self.respond({"error": "Not found"}, status=404)
            identifier = payload["id"]
            with catalog.lock:
                row, files = catalog.rows[identifier], catalog.paths[identifier]
                if payload["source_signature"] != row["source_signature"] or catalog.signature(files) != row["source_signature"]:
                    raise Conflict("Source artifacts changed. Refresh and review the new video before saving.")
                review = reviews.save(identifier, payload["label"], payload.get("notes", ""),
                                      row["source_signature"], payload["revision"])
                return self.respond(dict(review=review, verdict=verdict(row, review)))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Conflict as exc:
            self.respond({"error": str(exc)}, status=409)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            self.respond({"error": str(exc)}, status=400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-dir", type=Path)
    source.add_argument("--azure-backup", type=Path, help="Azure verification receipt JSON with destination and root_sha256sums_sha256; requires az login")
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/robotwin-if/video-review",
                        help="Azure asset cache root (each release gets its own directory)")
    parser.add_argument("--review-dir", type=Path, help="Separate annotation directory; defaults under outputs/policy-eval/video-reviews")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8893)
    args = parser.parse_args()
    if args.azure_backup:
        backup = read_json(args.azure_backup)
        if not backup or backup.get("complete") is not True:
            parser.error("--azure-backup must point to a completed Azure verification receipt")
        url, checksum = backup["destination"], backup["root_sha256sums_sha256"]
        catalog = AzureCatalog(url, checksum, args.cache_dir / (urlsplit(url).path.rstrip("/").split("/")[-1] + "-" + checksum[:12]))
    else:
        catalog = Catalog(args.run_dir)
    directory = args.review_dir or ROOT / "outputs/policy-eval/video-reviews" / (catalog.run.name + "-" + digest(str(catalog.run).encode())[:10])
    if directory.resolve().is_relative_to(catalog.run):
        parser.error("--review-dir must be outside the evaluation archive")
    reviews = Reviews(directory / "reviews.sqlite3", catalog.run)
    server = ReviewServer((args.host, args.port), catalog, reviews)
    print(f"Video review: http://{args.host}:{server.server_port}\nEpisodes: {len(catalog.rows)}\nAnnotations: {reviews.path}\nNo model, simulator or GPU is loaded.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
