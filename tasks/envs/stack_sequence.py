from ._base_task import Base_Task
from .utils import *
import sapien
import numpy as np
from copy import deepcopy


class stack_sequence(Base_Task):
    """IF-Sequence (stack): stack 3 colored blocks in the INSTRUCTED bottom->top order.

    Reuse of native ``stack_blocks_three`` (same create_box blocks, same
    pick_and_place_block motion, same stack target). The ONLY IF change: the
    commanded stacking ORDER varies per episode while the scene (3 fixed-color
    blocks at fixed positions) stays identical, so the policy must READ the
    instruction rather than fall back on the native red-bottom prior.

    Scene and order are DECOUPLED through the seed (mirrors laptop_verb):

        scene_seed = seed // 6      # identical for the 6-seed group
        mode       = seed % 6       # which of the 6 permutations

    So eval seeds (0..5),(6..11),... give scene #0,#1,... each stacked in all 6
    bottom->top orders, with pixel-identical initial frames -- only the
    instruction differs. The spike harness overrides MODE (fix order, vary scene)
    to measure per-permutation oracle reliability, and ORACLE_MODE (stack a
    DIFFERENT order than commanded) for the Layer-B counter-example.

    Success is static end-state (vertical stack order), split for eval into:
      - L1 execution : a 3-high stack formed at all (ANY order).
      - L2 following : the stack order matches the commanded permutation.
    check_success (the collect/oracle gate) requires L2 (+ grippers open).
    """

    BLOCK_HALF = 0.025
    # Fixed referring colors: index 0=red, 1=green, 2=blue. Never randomized --
    # they are the instruction's referring names; grounding RGB is assumed trivial
    # (pure noun grounding is IF-Noun-Grounding's job), this task isolates ORDER.
    COLORS = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    COLOR_NAMES = ["red", "green", "blue"]
    # 6 permutations of (bottom, mid, top) as color indices. mode -> PERMS[mode].
    PERMS = [
        (0, 1, 2), (0, 2, 1), (1, 0, 2),
        (1, 2, 0), (2, 0, 1), (2, 1, 0),
    ]
    DEFAULT_MODE = 0            # (red, green, blue) bottom->top = native prior
    # Native stack_blocks_three check tolerances; 0.05 gap = 2*BLOCK_HALF.
    STACK_EPS = [0.025, 0.025, 0.012]
    STACK_GAP = 0.05

    # Spike/eval overrides (None -> derive from seed). MODE fixes the commanded
    # order; ORACLE_MODE (if set) makes the oracle STACK a different order than
    # commanded -> used only to build the Layer-B counter-example.
    MODE = None
    ORACLE_MODE = None

    def setup_demo(self, **kwags):
        self._seed = kwags.get("seed", 0)
        super()._init_task_env_(**kwags)

    def load_actors(self):
        # Decouple scene from order. When MODE is forced (spike), vary the scene
        # by the raw seed and hold the order fixed; otherwise the shipped pairing
        # is scene=seed//6, order=seed%6.
        if self.MODE is not None:
            scene_seed = self._seed
            self.mode = int(self.MODE)
        else:
            scene_seed = self._seed // 6
            self.mode = self._seed % 6
        np.random.seed(scene_seed)
        self.perm = self.PERMS[self.mode]

        block_half_size = self.BLOCK_HALF
        block_pose_lst = []
        for i in range(3):
            block_pose = rand_pose(
                xlim=[-0.28, 0.28],
                ylim=[-0.08, 0.05],
                zlim=[0.741 + block_half_size],
                qpos=[1, 0, 0, 0],
                ylim_prop=True,
                rotate_rand=True,
                rotate_lim=[0, 0, 0.75],
            )

            def check_block_pose(block_pose):
                for j in range(len(block_pose_lst)):
                    if np.sum(pow(block_pose.p[:2] - block_pose_lst[j].p[:2], 2)) < 0.01:
                        return False
                return True

            while (abs(block_pose.p[0]) < 0.05 or np.sum(pow(block_pose.p[:2] - np.array([0, -0.1]), 2)) < 0.0225
                   or not check_block_pose(block_pose)):
                block_pose = rand_pose(
                    xlim=[-0.28, 0.28],
                    ylim=[-0.08, 0.05],
                    zlim=[0.741 + block_half_size],
                    qpos=[1, 0, 0, 0],
                    ylim_prop=True,
                    rotate_rand=True,
                    rotate_lim=[0, 0, 0.75],
                )
            block_pose_lst.append(deepcopy(block_pose))

        def create_block(block_pose, color):
            return create_box(
                scene=self,
                pose=block_pose,
                half_size=(block_half_size, block_half_size, block_half_size),
                color=color,
                name="box",
            )

        # Fixed color->position assignment (pose i -> color i), deterministic per
        # scene_seed and independent of the commanded order.
        self.blocks = [create_block(block_pose_lst[i], self.COLORS[i]) for i in range(3)]
        for blk in self.blocks:
            self.add_prohibit_area(blk, padding=0.05)
        target_pose = [-0.04, -0.13, 0.04, -0.05]
        self.prohibited_area.append(target_pose)

    def play_once(self):
        self.last_gripper = None
        self.last_actor = None

        # The oracle stacks in ORACLE_MODE if given (counter-example), else the
        # commanded order. Bottom is placed first, then mid on it, then top.
        exec_perm = self.PERMS[int(self.ORACLE_MODE)] if self.ORACLE_MODE is not None else self.perm
        arms = []
        for c in exec_perm:
            arms.append(self.pick_and_place_block(self.blocks[c]))

        self.info["mode"] = self.mode
        self.info["info"] = {
            "{A}": f"{self.COLOR_NAMES[self.perm[0]]} block",
            "{B}": f"{self.COLOR_NAMES[self.perm[1]]} block",
            "{C}": f"{self.COLOR_NAMES[self.perm[2]]} block",
            "{a}": arms[0],
            "{b}": arms[1],
            "{c}": arms[2],
        }
        return self.info

    def pick_and_place_block(self, block):
        block_pose = block.get_pose().p
        arm_tag = ArmTag("left" if block_pose[0] < 0 else "right")

        if self.last_gripper is not None and (self.last_gripper != arm_tag):
            self.move(
                self.grasp_actor(block, arm_tag=arm_tag, pre_grasp_dis=0.09),
                self.back_to_origin(arm_tag=arm_tag.opposite),
            )
        else:
            self.move(self.grasp_actor(block, arm_tag=arm_tag, pre_grasp_dis=0.09))

        self.move(self.move_by_displacement(arm_tag=arm_tag, z=0.07))

        if self.last_actor is None:
            target_pose = [0, -0.13, 0.75 + self.table_z_bias, 0, 1, 0, 0]
        else:
            target_pose = self.last_actor.get_functional_point(1)

        self.move(
            self.place_actor(
                block,
                target_pose=target_pose,
                arm_tag=arm_tag,
                functional_point_id=0,
                pre_dis=0.05,
                dis=0.,
                pre_dis_axis="fp",
            ))
        self.move(self.move_by_displacement(arm_tag=arm_tag, z=0.07))

        self.last_gripper = arm_tag
        self.last_actor = block
        return str(arm_tag)

    def _stacked(self, lower_p, upper_p):
        return (abs(upper_p[0] - lower_p[0]) < self.STACK_EPS[0]
                and abs(upper_p[1] - lower_p[1]) < self.STACK_EPS[1]
                and abs(upper_p[2] - (lower_p[2] + self.STACK_GAP)) < self.STACK_EPS[2])

    def _l2_ordered(self):
        """Following signal: the stack is in the COMMANDED bottom->top order."""
        b, m, t = [self.blocks[c].get_pose().p for c in self.perm]
        return self._stacked(b, m) and self._stacked(m, t)

    def _l1_any_stack(self):
        """Execution signal: a 3-high vertical stack formed in ANY order."""
        ps = sorted([blk.get_pose().p for blk in self.blocks], key=lambda p: p[2])
        return self._stacked(ps[0], ps[1]) and self._stacked(ps[1], ps[2])

    def eval_signals(self):
        """Split/directional metric for policy eval: report L1 (execution) and L2
        (following) separately + whether this is the default (prior-aligned) order,
        so the diagnostic is the default-vs-non-default gap, NOT the bare L2 rate.
        See notes/2026-09-01-sequence-container/design-discussion.md."""
        return {
            "mode": self.mode,
            "is_default": self.mode == self.DEFAULT_MODE,
            "l1_stacked": bool(self._l1_any_stack()),
            "l2_ordered": bool(self._l2_ordered()),
        }

    def check_success(self):
        # Collect/oracle gate: strict correct-order stack + grippers released.
        return bool(self._l2_ordered() and self.is_left_gripper_open() and self.is_right_gripper_open())
