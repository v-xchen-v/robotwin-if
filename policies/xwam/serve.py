#!/usr/bin/env python3
"""Serve the pinned official X-WAM RoboTwin SFT model without a broker."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from policies.wam.serve import EpisodePolicy, main
from policies.xwam.client import CAMERAS, CONTRACT, prediction_seed, validate_deltas, validate_wire_observation


class XWAMEpisodePolicy(EpisodePolicy):
    def __init__(self, backend, policy, seed_everywhere):
        super().__init__(backend, policy, seed_everywhere, horizon=32)

    def predict(self, obs):
        return self.backend.predict(validate_wire_observation(obs), self.instruction,
                                    prediction_seed(self.seed, self.chunk * 32))

    def validate_actions(self, actions):
        return validate_deltas(actions)


class XWAMBackend:
    metadata = {"checkpoint_format": "official_deepspeed_module", "dtype": "bfloat16",
                "video_schedule_steps": 50, "action_denoise_steps": 10,
                "early_stop": True, "run_depth": False, "cfg": 0.0, "compile": False,
                "image_layout": "head/left/right separate views; resize 256x320 then center crop 0.95 and resize",
                "normalization": "official RoboTwin SFT q01/q99 statistics; no clipping",
                "action_inference": "32 sequential dual-arm EE xyz/axis-angle/gripper deltas",
                "noise_seed": "official MD5 hash of 0_<manifest episode seed>_<executed action count>"}

    def __init__(self, source, assets, output):
        sys.path.insert(0, str(source))
        import logging
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        import torch
        from omegaconf import OmegaConf
        from evaluation.policy_server import build_statistics, resize_and_center_crop_tensor
        from runners.xwam_runner import XWAMRunner
        self.resize = resize_and_center_crop_tensor
        model_dir = assets / "sharinka0715/X-WAM-checkpoints/robotwin_sft"
        config = OmegaConf.load(model_dir / "config.yaml")
        config.wan_checkpoint_dir = str(assets / "Wan-AI/Wan2.2-TI2V-5B")
        config.sample_steps, config.action_denoise_steps = 50, 10
        config.use_decoupled_inference = True
        config.action_num = config.dataset.frame_skip // config.dataset.action_skip
        if (config.frame_num - 1) * config.action_num != 32 or config.action_dim != 14 or config.proprio_dim != 16:
            raise ValueError("Checkpoint config does not match the published RoboTwin contract")
        self.state_low, self.state_high, self.action_low, self.action_high, dual_arm = build_statistics(config)
        if not dual_arm:
            raise ValueError("Expected RoboTwin dual-arm checkpoint")
        torch.manual_seed(config.seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        # Cast on CPU before transfer: the official constructor initially builds
        # the DiT in FP32, which needlessly raises startup VRAM on 48 GB GPUs.
        # The resulting inference dtype and strict SFT parameter loading match
        # the upstream .cuda().bfloat16() sequence.
        self.model = XWAMRunner(config=config).bfloat16().cuda()
        logging.info("Loading pinned RoboTwin SFT checkpoint with strict parameter coverage")
        # The published state is ~39 GB. Memory mapping avoids holding a second
        # resident copy while preserving strict loading into the official model.
        path = model_dir / "checkpoints/last.ckpt/checkpoint/mp_rank_00_model_states.pt"
        checkpoint = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
        self.model.load_state_dict(checkpoint["module"], strict=True)
        del checkpoint
        self.model.eval()
        self.config = config
        OmegaConf.save(config, output / "resolved_model.yaml")

    def reset(self):
        pass  # Official X-WAM inference has no cross-chunk or cross-episode cache.

    def predict(self, observation, instruction, seed):
        import numpy as np
        import torch
        video = np.stack([observation["images"][name] for name in CAMERAS]).astype(np.float32) / 127.5 - 1.
        rgb = torch.from_numpy(video).bfloat16().unsqueeze(0).cuda().permute(0, 1, 4, 2, 3)
        rgb = self.resize(rgb, self.config.dataset.video_size, 0.95)
        state = 2 * (observation["state"] - self.state_low) / (self.state_high - self.state_low) - 1
        proprio = torch.from_numpy(state).bfloat16().unsqueeze(0).cuda()
        with torch.inference_mode():
            _, actions, _, _ = self.model.generate(rgb, proprio, [instruction], seeds=[seed],
                                                  early_stop=True, cfg=0., run_depth=False)
        values = actions[0].float().cpu().numpy()
        return (values[:, :14] + 1) / 2 * (self.action_high - self.action_low) + self.action_low


if __name__ == "__main__":
    main("xwam", XWAMBackend, episode_policy_class=XWAMEpisodePolicy, contract=CONTRACT)
