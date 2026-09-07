"""Add prediction evidence to the official Hy-VLA wrapper without changing decoding."""
import numpy as np

from robotwin_eval.policy_wrapper import HyVLAPolicyWrapper


class RecordedWrapper(HyVLAPolicyWrapper):
    def reset(self):
        self.last_prediction = None
        return super().reset()

    def get_action(self, batch):
        self.last_prediction = None
        return super().get_action(batch)

    def _decode_actions(self, actions, initial_ee_pose_xyzw):
        decoded = super()._decode_actions(actions, initial_ee_pose_xyzw)
        if self.umi_coord_frame or self.umi_gripper_space:
            raise ValueError("This integration requires the official RoboTwin coordinate/gripper settings")
        wxyz = decoded.copy()
        wxyz[:, 3:7] = decoded[:, [6, 3, 4, 5]]
        wxyz[:, 11:15] = decoded[:, [14, 11, 12, 13]]
        if actions.shape != (40, 20) or wxyz.shape != (20, 16):
            raise ValueError("Expected 40 rel+abs tokens and 20 decoded EE targets")
        if not np.isfinite(actions).all() or not np.isfinite(wxyz).all():
            raise ValueError("Model returned nonfinite actions")
        self.last_prediction = {"model_actions": actions.copy(), "decoded_actions": wxyz}
        return decoded
