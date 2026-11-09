#!/usr/bin/env python3
"""Serve the pinned official Motus RoboTwin joint video/action policy."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class MotusBackend:
    metadata = {"checkpoint_format": "official_deepspeed_module", "dtype": "bfloat16",
                "num_inference_steps": 10, "solver": "Euler", "action_horizon": 16,
                "image_layout": "head 240x320 above two 120x160 wrists; padded resize to 384x320",
                "normalization": "official inference passes raw joint state and returns raw qpos",
                "action_inference": "upstream joint video/action prediction, all 16 actions executed",
                "stage1_backbone": "downloaded for reproducibility; Stage 3 checkpoint contains backbone weights"}

    def __init__(self, source, assets, output):
        policy_dir = source / "inference/robotwin/Motus"
        sys.path.insert(0, str(policy_dir))
        from deploy_policy import MotusPolicy, reset_model
        self.reset_model = reset_model
        self.policy = MotusPolicy(
            checkpoint_path=str(assets / "motus-robotics/Motus_robotwin2"),
            config_path=str(policy_dir / "utils/robotwin.yml"),
            wan_path=str(assets / "Wan-AI/Wan2.2-TI2V-5B"),
            vlm_path=str(assets / "Qwen/Qwen3-VL-2B-Instruct"), device="cuda",
            log_dir=str(output), task_name="predictions")
        from policies.wam.runtime import checkpoint_schema, require_complete_state
        schema = checkpoint_schema(assets / "motus-robotics/Motus_robotwin2/mp_rank_00_model_states.pt")
        require_complete_state(self.policy.model, schema.get("module"), "Motus")
        # Predicted-frame grids are diagnostics; retain upstream video generation itself.
        self.policy.save_images = False

    def reset(self):
        self.reset_model(self.policy)
        self.policy.current_state_norm = None
        self.policy.current_instruction = None

    def predict(self, observation, instruction):
        if observation["observation"]["head_camera"]["rgb"].shape != (240, 320, 3):
            raise ValueError("The official Motus RoboTwin adapter requires a 240x320 head RGB view")
        self.policy.set_instruction(instruction)
        self.policy.update_obs(observation)
        actions = self.policy.get_action()
        # Upstream appends returned chunks to a queue but never consumes it in eval().
        # We execute the returned chunk in the simulator, so discard that redundant queue.
        self.policy.action_cache.clear()
        return actions


if __name__ == "__main__":
    from policies.wam.serve import main
    main("motus", MotusBackend)
