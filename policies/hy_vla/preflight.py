"""Probe real-observation inference, seven-step caching and reset isolation on a live server."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from policies.hy_vla.client import CAMERAS, HyVLAClient, packb, unpackb  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--seed", type=int, default=2000)
    parser.add_argument("--server-url", default="ws://127.0.0.1:8015")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with np.load(args.observation) as data:
        state = data["proprio"]
        if state.shape != (16,):
            raise ValueError("Preflight needs native 16D wxyz EE proprio from a saved observation")
        obs = {"observation": {name: {"rgb": data[name]} for name in CAMERAS},
               "endpose": {"left_endpose": state[:7], "left_gripper": state[7],
                           "right_endpose": state[8:15], "right_gripper": state[15]}}
    client = HyVLAClient(args.server_url)
    output, model, decoded, events = [], [], [], []
    try:
        client.connection.send(packb({"type": "step", "step": 0}))
        assert "Reset" in unpackb(client.connection.recv())["error"]
        second_rejected = False
        with connect(args.server_url, compression=None, ping_interval=None) as second:
            try:
                second.recv(timeout=5)
            except ConnectionClosed as exc:
                second_rejected = exc.rcvd.code == 1013
        assert second_rejected, "Second client was not rejected"
        for _ in range(2):
            client.reset(args.instruction, args.seed)
            actions, model_chunks, decoded_chunks = [], [], []
            for step in range(8):
                action, prediction = client.predict(obs)
                actions.append(action)
                if prediction["new_chunk"]:
                    model_chunks.append(prediction["model_actions"])
                    decoded_chunks.append(prediction["raw_actions"])
            output.append(np.stack(actions))
            model.append(np.stack(model_chunks))
            decoded.append(np.stack(decoded_chunks))
            events.append(client.requests)
        client.connection.send(packb({"type": "reset", "seed": -1, "instruction": "invalid"}))
        assert "error" in unpackb(client.connection.recv())
        client.connection.send(packb({"type": "step", "step": 8}))
        assert "Reset" in unpackb(client.connection.recv())["error"]
    finally:
        client.close()
    np.savez_compressed(args.output_dir / "predictions.npz", executed_actions=output, model_actions=model, decoded_actions=decoded)
    report = {"observation": str(args.observation.resolve()), "instruction": args.instruction, "seed": args.seed,
              "steps_per_repeat": 8, "model_shape": list(model[0].shape), "decoded_shape": list(decoded[0].shape),
              "finite": bool(np.isfinite(output).all() and np.isfinite(model).all()),
              "repeat_model_max_abs_diff": float(np.max(np.abs(model[0] - model[1]))),
              "repeat_action_max_abs_diff": float(np.max(np.abs(output[0] - output[1]))),
              "reset_required": True, "second_client_rejected": second_rejected,
              "invalid_reset_invalidates_episode": True, "events": events, "server_metadata": client.server_metadata}
    (args.output_dir / "preflight.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("events", "server_metadata")}), flush=True)


if __name__ == "__main__":
    main()
