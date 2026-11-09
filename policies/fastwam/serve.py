#!/usr/bin/env python3
"""Serve the pinned official Fast-WAM RoboTwin policy in its model environment."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class FastWAMBackend:
    metadata = {"checkpoint_format": "official_pytorch", "dtype": "bfloat16",
                "num_inference_steps": 10, "sigma_shift": 5.0, "text_cfg_scale": 1.0,
                "image_layout": "head 256x320 above two 128x160 wrists; final 384x320",
                "normalization": "official RoboTwin z-score dataset statistics",
                "action_inference": "upstream action-only infer_action; 32 predicted, first 24 executed",
                "compile": False}

    def __init__(self, source, assets, output):
        sys.path.insert(0, str(source))
        sys.path.insert(0, str(source / "src"))
        import torch
        from experiments.robotwin.fastwam_policy.deploy_policy import WorldActionRobotWinPolicy, _compose_sim_cfg
        from omegaconf import OmegaConf
        cfg = _compose_sim_cfg(None, "sim_robotwin.yaml", "robotwin_uncond_3cam_384_1e-4")
        # Both published Wan repositories contain the same UMT5 tokenizer objects.
        # Use the pinned local Wan2.2 assets, and disable implicit ModelScope downloads.
        cfg.model.model_id = str(assets / "Wan-AI/Wan2.2-TI2V-5B")
        cfg.model.tokenizer_model_id = cfg.model.model_id
        cfg.model.redirect_common_files = False
        model_dir = assets / "yuanty/fastwam"
        self.policy = WorldActionRobotWinPolicy(
            model_cfg=cfg.model, processor_cfg=cfg.data.train.processor,
            checkpoint_path=str(model_dir / "robotwin_uncond_3cam_384.pt"),
            dataset_stats_path=model_dir / "robotwin_uncond_3cam_384_dataset_stats.json",
            device="cuda", model_dtype=torch.bfloat16, action_horizon=32, replan_steps=24,
            num_inference_steps=10, sigma_shift=5.0, seed=None, text_cfg_scale=1.0,
            negative_prompt="", rand_device="cpu", tiled=False, timing_enabled=False, num_video_frames=9)
        from policies.wam.runtime import checkpoint_schema, require_complete_state
        schema = checkpoint_schema(model_dir / "robotwin_uncond_3cam_384.pt")
        require_complete_state(self.policy.model.mot, schema.get("mot"), "Fast-WAM MoT")
        require_complete_state(self.policy.model.proprio_encoder, schema.get("proprio_encoder"), "Fast-WAM proprio encoder")
        OmegaConf.save(cfg, output / "resolved_model.yaml")

    def reset(self):
        self.policy.reset()

    def predict(self, observation, instruction):
        # Reuse official camera composition, state normalization and action denormalization.
        return self.policy._infer_action_chunk(observation, instruction)


if __name__ == "__main__":
    from policies.wam.serve import main
    main("fastwam", FastWAMBackend)
