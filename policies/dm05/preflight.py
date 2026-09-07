"""Probe the live DM05 server with a saved real RoboTwin observation."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from policies.dm05.client import CAMERAS, DM05Client  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--seed", type=int, default=2000)
    parser.add_argument("--server-url", default="http://127.0.0.1:8014")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with np.load(args.observation) as data:
        obs = {"observation": {name: {"rgb": data[name]} for name in CAMERAS},
               "joint_action": {"vector": data["joint_state"]}}
    client = DM05Client(args.server_url)
    results, events = [], []
    try:
        # Exercise eager first use, automatic graph capture and replay with the
        # same input/seed; record differences instead of assuming determinism.
        for _ in range(3):
            client.reset(args.instruction, args.seed)
            actions, prediction = client.predict(obs)
            results.append(actions)
            events.append({"latency_seconds": prediction["latency_seconds"], "requests": client.requests})
    finally:
        client.close()
    np.savez_compressed(args.output_dir / "predictions.npz", actions=np.stack(results))
    report = {"observation": str(args.observation.resolve()), "instruction": args.instruction,
              "seed": args.seed, "shape": list(results[0].shape),
              "finite": bool(np.isfinite(results).all()),
              "repeat_max_abs_diff": [float(np.max(np.abs(results[0] - r))) for r in results[1:]],
              "events": events, "server_metadata": client.server_metadata}
    (args.output_dir / "preflight.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("server_metadata", "events")}), flush=True)


if __name__ == "__main__":
    main()
