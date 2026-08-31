from ._base_task import Base_Task
from .utils import *
import sapien
import math


class open_laptop_mid(Base_Task):
    """IF-Verb-Select open direction from the shared mid-state (spike).

    Same asset / init / variant subset as ``close_laptop`` (50% open, variants
    {1,9,10}); reuses native ``open_laptop``'s open motion (grasp screen
    contact_point 0, then servo toward contact_point 1 so the hinge opens),
    but keeps driving until a HIGH threshold instead of native's ~50% break,
    to confirm the open variant can reach a band clearly above the 50% start.
    """

    INIT_OPEN = 0.5
    # Target the open band. Calibrated to what the guarded servo reliably
    # reaches from the 50% mid-state before the steep-angle planning wall;
    # 70% is well above the 50% start yet below the ~77-81% wall most variants
    # hit. The spike reports the final-fraction distribution to re-calibrate.
    OPEN_TARGET = 0.70
    # Shared reliable subset for both verb directions (same as close_laptop):
    # {1,9} open reliably to ~77-81% (100% past 70% with the crash guard).
    # mid=10 is excluded: it walls at ~63% open ~60% of the time.
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
        self.laptop.set_qpos([limit[0] + (limit[1] - limit[0]) * self.INIT_OPEN])
        self.laptop.set_mass(0.01)
        self.laptop.set_properties(1, 0)
        self.add_prohibit_area(self.laptop, padding=0.1)

    def play_once(self):
        face_prod = get_face_prod(self.laptop.get_pose().q, [1, 0, 0], [1, 0, 0])
        arm_tag = ArmTag("left" if face_prod > 0 else "right")
        self.arm_tag = arm_tag

        # Grasp the screen (same contact point as native open_laptop).
        self.move(self.grasp_actor(self.laptop, arm_tag=arm_tag, pre_grasp_dis=0.08, contact_point_id=0))

        # Open by servoing the held screen point toward the higher contact
        # point 1; the hinge rotates open. Guard on qpos progress so we stop
        # once the lid stalls (opening increases qpos).
        start_qpos = self.laptop.get_qpos()[0]
        for _ in range(30):
            try:
                self.move(
                    self.grasp_actor(
                        self.laptop,
                        arm_tag=arm_tag,
                        pre_grasp_dis=0.0,
                        grasp_dis=0.0,
                        contact_point_id=1,
                    ))
            except AssertionError:
                # At steep open angles the point-1 grasp becomes unplannable
                # (choose_grasp_pose -> None). Stop gracefully at the last
                # reached angle instead of crashing.
                break
            new_qpos = self.laptop.get_qpos()[0]
            if new_qpos - start_qpos <= 0.001:  # opening increases qpos
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
        target = self.OPEN_TARGET if target is None else target
        limit = self.laptop.get_qlimits()[0]
        qpos = self.laptop.get_qpos()
        return qpos[0] >= limit[0] + (limit[1] - limit[0]) * target
