"""RoboTwin wrap32 action layout and aspect-ratio image buckets from VLAct."""

import cv2
import numpy as np

ACTION_ORDER = [0, 1, 2, 3, 4, 5, 12, 6, 7, 8, 9, 10, 11, 13]
IMAGE_BUCKETS = [[320, 180], [280, 210]]  # width, height


def decode_model_actions(values, mask):
    """Match official ModelClient.unnormalize_actions(..., 'wrap') + reordering.

    robotwin_wrap_32 trains joint angles in radians, NOT percentile-scaled units.
    Its mask selects 12 angular joints; two grippers retain clipped predictions.
    """
    values = np.asarray(values, dtype=np.float32)
    if values.shape != (32, 14) or not np.isfinite(values).all():
        raise ValueError(f"Expected finite (32, 14) model predictions, got {values.shape}")
    mask = np.asarray(mask, dtype=bool)
    if mask.shape != (14,) or not np.array_equal(mask, [True] * 12 + [False] * 2):
        raise ValueError("Expected 12 angular joints followed by two grippers")
    actions = np.clip(values, -1, 1)
    actions[:, mask] = (values[:, mask] + np.pi) % (2 * np.pi) - np.pi
    return actions[:, ACTION_ORDER].copy()


def resize_image(image, buckets=IMAGE_BUCKETS):
    image = np.asarray(image)
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8 or min(image.shape[:2]) < 1:
        raise ValueError("Expected nonempty HWC uint8 RGB")
    height, width = image.shape[:2]
    size = min(buckets, key=lambda size: abs(size[0] / float(size[1]) - width / float(height)))
    return cv2.resize(image, tuple(size), interpolation=cv2.INTER_AREA)
