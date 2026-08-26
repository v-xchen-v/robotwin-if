"""Operate-Microphone-Drawer IF task (regime i: side microphone, strict arm+step grading).

Scene every episode: a cabinet with a functional drawer (center-back) plus one
microphone spawned clearly to one side (native put_object_cabinet geometry, |x|>0.2).
The bimanual sequence is native-proven: the arm OPPOSITE the microphone opens and
HOLDS the drawer while the microphone-side arm grasps the mic and places it inside.

Why regime i (not a central microphone): a central mic forces both arms into the
midline at once (grasp clash) and, even sequenced, the placing arm must seat the mic
into a center-back drawer at the edge of its workspace — both fail RoboTwin's planner.
Placing is only feasible from the mic's own side, so the placing arm is geometry-locked
to the mic side and the opening arm to the opposite. The instruction names that opening
arm; the task tests whether the policy follows the named arm assignment AND completes
both steps. (Full probe write-up: docs/features/06.)

check_success is a strict AND — drawer opened, mic in the drawer, the NAMED arm opened,
the other arm placed — any single miss is a failure, and info["fail_reason"] reports
whether the miss was an unfinished step (incomplete:*) or a swapped arm (wrong_arm:*).
Arm attribution reads live scene contacts: aloha-agilex gripper fingers are named
fl_link7/8 (left) and fr_link7/8 (right), so the arm touching the drawer handle at the
moment it first opens is the opener, and the arm on the mic when it lands is the placer.
"""
from ._base_task import Base_Task
from .utils import *
import numpy as np


class operate_mic_drawer(Base_Task):

    # Grasp contact points validated for 018_microphone by native handover_mic.
    MIC_CONTACT = [1, 9, 10, 11, 12, 13, 14, 15]
    # Drawer prismatic joint (qpos[0]) reads ~0.15 fully open, 0 closed; well separated.
    OPEN_THRESH = 0.06

    def setup_demo(self, **kwags):
        self._seed = kwags.get("seed", 0)
        super()._init_task_env_(**kwags, table_static=False)

    def load_actors(self):
        self.cabinet = rand_create_sapien_urdf_obj(
            scene=self,
            modelname="036_cabinet",
            modelid=46653,
            xlim=[-0.05, 0.05],
            ylim=[0.155, 0.155],
            rotate_rand=False,
            rotate_lim=[0, 0, np.pi / 16],
            qpos=[1, 0, 0, 1],
            fix_root_link=True,
        )

        # Microphone clearly to one side (native put_object_cabinet geometry): the side
        # decides the roles — mic-side arm places, opposite arm opens+holds the drawer.
        rand_pos = rand_pose(
            xlim=[-0.25, 0.25],
            ylim=[-0.2, -0.1],
            qpos=[0.707, 0.707, 0.0, 0.0],
            rotate_rand=True,
            rotate_lim=[0, np.pi / 3, 0],
        )
        while abs(rand_pos.p[0]) < 0.2:
            rand_pos = rand_pose(
                xlim=[-0.32, 0.32],
                ylim=[-0.2, -0.1],
                qpos=[0.707, 0.707, 0.0, 0.0],
                rotate_rand=True,
                rotate_lim=[0, np.pi / 3, 0],
            )
        self.mic_id = int(np.random.choice([0, 4, 5]))
        self.microphone = create_actor(
            scene=self,
            pose=rand_pos,
            modelname="018_microphone",
            convex=True,
            model_id=self.mic_id,
        )
        self.microphone.set_mass(0.01)
        self.add_prohibit_area(self.microphone, padding=0.01)
        self.add_prohibit_area(self.cabinet, padding=0.01)
        self.prohibited_area.append([-0.15, -0.3, 0.15, 0.3])

        # Roles from the microphone side (native rule). The instruction names open_arm.
        self.place_arm = ArmTag("right" if self.microphone.get_pose().p[0] > 0 else "left")
        self.open_arm = self.place_arm.opposite

        # Arm-attribution latches (updated across the repeated check_success calls of a
        # policy rollout, which never runs play_once): which arm first opened the drawer,
        # which arm held the mic when it landed in the drawer.
        self._opened_by = None
        self._placed_by = None
        self.fail_reason = None

        self.delay(2)
        self.origin_z = float(self.microphone.get_pose().p[2])

    def _arm_on(self, actor_name):
        """Set of arms ('left'/'right') whose gripper fingers currently touch actor_name.
        aloha-agilex fingers are fl_link7/8 (left) and fr_link7/8 (right)."""
        arms = set()
        for c in self.scene.get_contacts():
            n0, n1 = c.bodies[0].entity.name, c.bodies[1].entity.name
            if actor_name not in (n0, n1):
                continue
            other = n1 if n0 == actor_name else n0
            if other.startswith("fl_"):
                arms.add("left")
            elif other.startswith("fr_"):
                arms.add("right")
        return arms

    def play_once(self):
        place_arm, open_arm = self.place_arm, self.open_arm

        # Native put_object_cabinet mechanic: grasp mic, grasp drawer bar, pull the drawer
        # while holding it, lift the mic, place it into the drawer's functional point.
        self.move(self.grasp_actor(self.microphone, arm_tag=place_arm,
                                   contact_point_id=self.MIC_CONTACT, pre_grasp_dis=0.1))
        self.move(self.grasp_actor(self.cabinet, arm_tag=open_arm, pre_grasp_dis=0.05))
        for _ in range(4):
            self.move(self.move_by_displacement(arm_tag=open_arm, y=-0.04))
        self.move(self.move_by_displacement(arm_tag=place_arm, z=0.15))
        target_pose = self.cabinet.get_functional_point(0)
        self.move(self.place_actor(self.microphone, arm_tag=place_arm,
                                   target_pose=target_pose, pre_dis=0.13, dis=0.1))

        # {a} = arm that opens the drawer; {b}/"the other arm" = arm that places the mic.
        self.info["info"] = {
            "{A}": f"018_microphone/base{self.mic_id}",
            "{B}": "036_cabinet/base0",
            "{a}": str(open_arm),
            "{b}": str(place_arm),
        }
        return self.info

    def check_success(self):
        q = np.atleast_1d(self.cabinet.get_qpos())
        drawer_open = float(q[0]) > self.OPEN_THRESH

        mic_p = self.microphone.get_pose().p
        fp = self.cabinet.get_functional_point(0)
        xy_ok = bool(np.all(np.abs(mic_p[:2] - fp[:2]) < np.array([0.05, 0.05])))
        rise = float(mic_p[2] - self.origin_z)
        place_open = (self.robot.is_left_gripper_open() if self.place_arm == "left"
                      else self.robot.is_right_gripper_open())
        mic_in = bool(xy_ok and 0.007 < rise < 0.12 and place_open)

        # Latch arm attribution at the first moment each sub-event holds.
        if drawer_open and self._opened_by is None:
            a = self._arm_on("036_cabinet")
            if len(a) == 1:
                self._opened_by = a.pop()
        if mic_in and self._placed_by is None:
            a = self._arm_on("018_microphone")
            if len(a) == 1:
                self._placed_by = a.pop()

        # Strict AND, most-specific failure first.
        if not drawer_open:
            self.fail_reason = "incomplete:drawer"
            return False
        if not mic_in:
            self.fail_reason = "incomplete:mic"
            return False
        if self._opened_by is not None and self._opened_by != str(self.open_arm):
            self.fail_reason = "wrong_arm:open"
            return False
        if self._placed_by is not None and self._placed_by != str(self.place_arm):
            self.fail_reason = "wrong_arm:place"
            return False
        self.fail_reason = None
        return True
