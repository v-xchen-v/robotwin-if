from ._base_task import Base_Task
from .utils import *
import sapien
import math


class close_laptop(Base_Task):
    """IF-Verb-Select 合盖 oracle (spike).

    Fork of native ``open_laptop`` reversed into a close motion. Shares the
    IF-Verb-Select mid-state design: the laptop starts ~50% open (identical
    initial frame to the open variant) and the oracle folds the screen down
    onto the base along the hinge arc.

    Mechanism: grasp the screen at contact_point 0, then iteratively servo the
    gripper toward contact_point 3 (on the keyboard base ``link_0``). Because
    the screen is hinge-constrained, dragging the held screen point toward the
    base point rotates the hinge closed; the arc is produced by the constraint,
    not hand-scripted (same idiom as ``open_laptop`` 0->1 and ``open_microwave``).
    """

    # Shared IF-Verb-Select initial opening: fraction of the hinge range.
    INIT_OPEN = 0.5
    # Success band: hinge folded back down to at/below this fraction of range.
    CLOSE_TARGET = 0.15
    # Shared reliable subset for BOTH verb directions. {1,9} are non-INV
    # (point 0=screen, 3=base) so "grasp screen -> servo toward base" folds
    # correctly (~92% close). mid=10 closes fine but is unreliable for the OPEN
    # direction (walls ~63% open), so it's excluded to keep one shared subset.
    # Excluded also: INV {0,2,5} (swapped screen/base contacts) and {3,4,6,8}
    # (degenerate point-3 grasp -> None crash).
    ALLOWED_MODEL_IDS = [1, 9]

    def setup_demo(self, is_test=False, **kwags):
        super()._init_task_env_(**kwags)

    def load_actors(self):
        self.model_name = "015_laptop"
        if self.ALLOWED_MODEL_IDS:
            self.model_id = int(np.random.choice(self.ALLOWED_MODEL_IDS))
        else:
            self.model_id = np.random.randint(0, 11)
        self.laptop: ArticulationActor = rand_create_sapien_urdf_obj(
            scene=self,
            modelname=self.model_name,
            modelid=self.model_id,
            xlim=[-0.05, 0.05],
            ylim=[-0.1, 0.05],
            rotate_rand=True,
            rotate_lim=[0, 0, np.pi / 3],
            qpos=[0.7, 0, 0, 0.7],
            fix_root_link=True,
        )
        limit = self.laptop.get_qlimits()[0]
        # Shared mid-state: ~50% open (vs open_laptop's ~20%).
        self.laptop.set_qpos([limit[0] + (limit[1] - limit[0]) * self.INIT_OPEN])
        self.laptop.set_mass(0.01)
        self.laptop.set_properties(1, 0)
        self.add_prohibit_area(self.laptop, padding=0.1)

    def play_once(self):
        face_prod = get_face_prod(self.laptop.get_pose().q, [1, 0, 0], [1, 0, 0])
        arm_tag = ArmTag("left" if face_prod > 0 else "right")
        self.arm_tag = arm_tag

        # Grasp the screen near its top edge (same contact point as open).
        self.move(self.grasp_actor(self.laptop, arm_tag=arm_tag, pre_grasp_dis=0.08, contact_point_id=0))

        # Fold the screen down: servo the held screen point toward the base
        # contact point; the hinge closes and qpos decreases. Guard on qpos
        # progress so we stop once the lid stalls (mirrors open_microwave loop).
        start_qpos = self.laptop.get_qpos()[0]
        for _ in range(30):
            self.move(
                self.grasp_actor(
                    self.laptop,
                    arm_tag=arm_tag,
                    pre_grasp_dis=0.0,
                    grasp_dis=0.0,
                    contact_point_id=3,
                ))
            new_qpos = self.laptop.get_qpos()[0]
            if start_qpos - new_qpos <= 0.001:  # closing decreases qpos
                break
            start_qpos = new_qpos
            if not self.plan_success:
                break
            if self.check_success():
                break

        self.info["info"] = {
            "{A}": f"{self.model_name}/base{self.model_id}",
            "{a}": str(arm_tag),
        }
        return self.info

    def check_success(self, target=None):
        target = self.CLOSE_TARGET if target is None else target
        limit = self.laptop.get_qlimits()[0]
        qpos = self.laptop.get_qpos()
        return qpos[0] <= limit[0] + (limit[1] - limit[0]) * target
