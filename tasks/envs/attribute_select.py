from ._base_task import Base_Task
from ._if_eval import apply_if_eval_step_limit
from .utils import *
from ._GLOBAL_CONFIGS import *
import sapien
import sapien.render as R
import numpy as np
from PIL import Image, ImageDraw


class attribute_select(Base_Task):
    """IF-Attribute-Select: ground a target object by a SINGLE visual feature.

    Four feature axes, one env, all built from primitives (self-contained, no
    external assets -- decals are drawn + built in memory, see _attach_decal):
      - color : two same-shape/size cubes, different body color   (red vs blue)
      - decal : two same-color/size cubes, different TOP image     (cat vs dog)
      - shape : two graspable boxes, different shape               (block vs bar)
      - size  : two same-color cubes, different scale              (big vs small)

    IF wiring (the diagnostic contrast lives WITHIN an axis, not across axes --
    color and decal scenes can't be pixel-identical, but "same scene, different
    named target" can):
        axis  = MODES[(seed // 2) % 4]     # which feature axis
        value = seed % 2                   # which feature-value is the target
        scene_seed = seed // 2             # object layout (fixed across the pair)
    So the pair (2k, 2k+1) is the SAME scene + axis, and only the commanded
    target flips -> the policy can only get it right by reading the instruction,
    not by a fixed prior. Report per-axis success + the value-0/value-1 gap.

    AXIS / VALUE / ORACLE_TARGET are harness overrides (spike/Layer-B); leave
    None for real collection so the seed drives everything.
    """

    TABLE_TOP = 0.741
    LIFT_THRESH = 0.05
    MODES = ["color", "decal", "shape", "size"]

    # two table slots; scene_seed decides which feature-value sits in which slot
    SLOTS = [(-0.13, -0.05), (0.13, -0.05)]
    # scene diversity: per-object xy + yaw jitter, drawn from the SCENE_SEED RNG
    # so the (2k,2k+1) pair still gets identical placement (same-scene preserved),
    # but different scene_seeds vary the layout (guards against a fixed-position
    # shortcut / overfitting). Kept small so both arms + the slim-bar grip stay
    # inside the reachable/graspable envelope.
    JIT_X = 0.025
    JIT_Y = 0.035
    JIT_YAW = np.pi / 7

    CUBE_HALF = 0.03
    BIG_HALF = 0.04
    SMALL_HALF = 0.02
    BAR_HALF = (0.06, 0.014, 0.025)    # slim, clearly-long bar (long axis 0.12)
    # The bar's long axis exceeds the gripper span, so it must be grasped across
    # its SHORT axis. grasp_actor picks the best-reachable of the given contact
    # ids; restricting the bar to the short-axis pair forces the 90-degree grip.
    BAR_GRASP_IDS = [1, 3]
    DECAL_BODY = (0.42, 0.44, 0.5)     # neutral body for decal cubes (no color cue)
    COLORS = {"red": (0.85, 0.1, 0.1), "blue": (0.1, 0.3, 0.85)}

    PRE_GRASP_DIS = 0.08
    LIFT_Z = 0.12
    TOP_IDS = [0, 1, 2, 3]             # default box top-down grasps

    # per-axis (value0, value1) feature labels; value = seed % 2 picks the target
    AXIS_VALUES = {
        "color": ("red", "blue"),
        "decal": ("cat", "dog"),
        "shape": ("block", "bar"),
        "size": ("big", "small"),
    }

    # Full referring phrase the instruction names for each value. One {ADJ} slot
    # carries the whole phrase so a single template pool works across all axes
    # (the shape axis has no separate adjective -- its feature IS the noun -- so
    # baking attribute+noun into {ADJ} is what keeps the pool uniform).
    AXIS_PHRASES = {
        "color": {"red": "red block", "blue": "blue block"},
        "decal": {"cat": "block with a cat on it", "dog": "block with a dog on it"},
        "shape": {"block": "cube", "bar": "long bar"},
        "size": {"big": "big block", "small": "small block"},
    }

    AXIS = None            # override: force one axis
    VALUE = None           # override: force which value is target (0/1)
    ORACLE_TARGET = None   # override: "target" (default) or "distractor" (Layer B)

    # ---- lifecycle -------------------------------------------------------
    def setup_demo(self, is_test=False, **kwags):
        self._seed = kwags.get("seed", 0)
        self._demo_kwargs = dict(kwags)
        super()._init_task_env_(**kwags)
        apply_if_eval_step_limit(self)

    def load_actors(self):
        scene_seed = self._seed // 2
        np.random.seed(scene_seed)
        self.axis = self.AXIS or self.MODES[(self._seed // 2) % len(self.MODES)]
        self.value = self.VALUE if self.VALUE is not None else self._seed % 2

        v0, v1 = self.AXIS_VALUES[self.axis]
        # scene_seed fixes the PHYSICAL scene: which feature-value sits in which
        # slot -- IDENTICAL across the (2k, 2k+1) pair. Only `value` (which value
        # is NAMED as the target) flips, so the policy can win only by reading the
        # instruction, never by object position (laptop_verb same-scene contrast).
        # (Placing the target at a value-independent slot would let a policy score
        # 100% by grabbing a fixed position without reading anything -- the bug
        # this structure avoids.)
        flip = int(np.random.rand() < 0.5)

        def jit(base):
            return (base[0] + np.random.uniform(-self.JIT_X, self.JIT_X),
                    base[1] + np.random.uniform(-self.JIT_Y, self.JIT_Y),
                    np.random.uniform(-self.JIT_YAW, self.JIT_YAW))

        obj0 = self._make_object(self.axis, v0, jit(self.SLOTS[flip]), "obj0")
        obj1 = self._make_object(self.axis, v1, jit(self.SLOTS[1 - flip]), "obj1")
        self.target, self.distractor = (obj0, obj1) if self.value == 0 else (obj1, obj0)
        # the slim bar (shape value1) needs the short-axis grip; remember it
        self._bar_actor = obj1 if self.axis == "shape" else None

        for a in (self.target, self.distractor):
            self.add_prohibit_area(a, padding=0.05)
        self._init_z = {}

    # ---- object construction --------------------------------------------
    def _make_object(self, axis, val, pose3, name):
        x, y, yaw = pose3
        if axis == "color":
            obj = self._box(x, y, yaw, self.CUBE_HALF, color=self.COLORS[val], name=name)
        elif axis == "size":
            half = self.BIG_HALF if val == "big" else self.SMALL_HALF
            obj = self._box(x, y, yaw, half, color=self.DECAL_BODY, name=name)
        elif axis == "shape":
            half = self.CUBE_HALF if val == "block" else self.BAR_HALF
            obj = self._box(x, y, yaw, half, color=self.DECAL_BODY, name=name)
        elif axis == "decal":
            obj = self._decal_cube(x, y, yaw, self.CUBE_HALF,
                                   _cat_arr() if val == "cat" else _dog_arr(), name)
        else:
            raise ValueError(axis)
        return obj

    @staticmethod
    def _yaw_q(yaw):
        return [np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)]

    def _box(self, x, y, yaw, half, color, name):
        h = half if isinstance(half, tuple) else (half, half, half)
        z = self.TABLE_TOP + h[2]
        obj = create_box(scene=self, pose=sapien.Pose([x, y, z], self._yaw_q(yaw)),
                         half_size=h, color=color, name=name)
        obj.set_mass(0.01)
        return obj

    def _decal_cube(self, x, y, yaw, half, arr, name):
        """Build a gray cube with an in-memory decal welded on its top face, as
        ONE rigid entity. Built manually (not create_box) because the decal mesh
        must be attached to the render body BEFORE the entity joins the scene --
        SAPIEN forbids attaching shapes to an already-parented render body. The
        returned Actor carries the default box top-down contact points so
        grasp_actor works exactly like a create_box cube.
        """
        ent = sapien.Entity(); ent.set_name(name)
        rc = sapien.physx.PhysxRigidDynamicComponent()
        rc.attach(sapien.physx.PhysxCollisionShapeBox(
            half_size=[half] * 3, material=self.scene.default_physical_material))
        rb = R.RenderBodyComponent()
        rb.attach(R.RenderShapeBox([half] * 3, R.RenderMaterial(base_color=[*self.DECAL_BODY, 1])))
        # decal: texture from array + quad mesh with explicit [0,1] UV (no files)
        tex = R.RenderTexture2D(arr, "R8G8B8A8Unorm", srgb=True)
        mat = R.RenderMaterial(); mat.set_base_color_texture(tex)
        mat.base_color = [1, 1, 1, 1]; mat.roughness = 0.7
        q = half * 0.9
        verts = np.array([[-q, -q, 0], [q, -q, 0], [q, q, 0], [-q, q, 0]], dtype=np.float32)
        tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)
        norms = np.tile([0, 0, 1], (4, 1)).astype(np.float32)
        uvs = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], dtype=np.float32)
        mesh = R.RenderShapeTriangleMesh(verts, tris, norms, uvs, mat)
        mesh.set_local_pose(sapien.Pose([0, 0, half + 0.002]))
        rb.attach(mesh)
        ent.add_component(rc); ent.add_component(rb)
        z = self.TABLE_TOP + half + self.table_z_bias
        ent.set_pose(sapien.Pose([x, y, z], self._yaw_q(yaw)))
        self.scene.add_entity(ent)
        obj = Actor(ent, self._box_data(half))
        obj.set_mass(0.01)
        return obj

    @staticmethod
    def _box_data(half):
        """Minimal actor-data dict = default create_box top-down contact set."""
        return {
            "center": [0, 0, 0],
            "extents": [half, half, half],
            "scale": [half, half, half],
            "target_pose": [[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 1], [0, 0, 0, 1]]],
            "contact_points_pose": [
                [[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0.0], [0, 0, 0, 1]],
                [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0.0], [0, 0, 0, 1]],
                [[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0.0], [0, 0, 0, 1]],
                [[0, 0, -1, 0], [-1, 0, 0, 0], [0, 1, 0, 0.0], [0, 0, 0, 1]],
            ],
            "transform_matrix": np.eye(4).tolist(),
            "functional_matrix": [
                [[1.0, 0.0, 0.0, 0.0], [0.0, -1.0, 0, 0.0], [0.0, 0, -1.0, -1], [0.0, 0.0, 0.0, 1.0]],
                [[1.0, 0.0, 0.0, 0.0], [0.0, -1.0, 0, 0.0], [0.0, 0, -1.0, 1], [0.0, 0.0, 0.0, 1.0]],
            ],
            "contact_points_description": [],
            "contact_points_group": [[0, 1, 2, 3]],
            "contact_points_mask": [True],
            "target_point_description": ["The center point on the bottom of the box."],
        }

    # ---- oracle ----------------------------------------------------------
    def play_once(self):
        for nm, a in (("target", self.target), ("distractor", self.distractor)):
            self._init_z[nm] = float(a.get_pose().p[2])

        which = self.ORACLE_TARGET or "target"
        obj = self.target if which == "target" else self.distractor
        arm_tag = ArmTag("left" if obj.get_pose().p[0] < 0 else "right")
        self.arm_tag = arm_tag

        ids = self.BAR_GRASP_IDS if (self._bar_actor is not None and obj is self._bar_actor) else self.TOP_IDS
        self.move(self.grasp_actor(obj, arm_tag=arm_tag,
                                   pre_grasp_dis=self.PRE_GRASP_DIS, grasp_dis=0.0,
                                   contact_point_id=ids))
        self.move(self.move_by_displacement(arm_tag, z=self.LIFT_Z))

        sig = self.eval_signals()
        self.info["mode"] = self.axis
        self.info["info"] = {"{ADJ}": self._adj_phrase()}
        self.info["signals"] = sig
        return self.info

    def _adj_phrase(self):
        v = self.AXIS_VALUES[self.axis][self.value]
        return self.AXIS_PHRASES[self.axis][v]

    # ---- success ---------------------------------------------------------
    def _lifted(self):
        for nm, a in (("target", self.target), ("distractor", self.distractor)):
            if nm in self._init_z and float(a.get_pose().p[2]) - self._init_z[nm] > self.LIFT_THRESH:
                return nm
        return None

    def eval_signals(self):
        lifted = self._lifted()
        return {
            "axis": self.axis,
            "value": self.value,
            "grasped_target": bool(lifted == "target"),
            "lifted": lifted,
        }

    def _raw_success(self):
        """Single-episode success: the object lifted off the table is the
        commanded target. Used by play_once's signals, the pair-gate trial-run,
        and eval -- NEVER call check_success from a trial-run (recursion)."""
        if not self._init_z:
            return False
        return self._lifted() == "target"

    # Pair-gate cache (class-level, survives across episodes in one process):
    # scene_seed -> "is the OTHER value of this scene also oracle-doable?".
    _pair_ok = {}

    def check_success(self):
        """Pair-gated success (mirrors laptop_verb / makes native collect_data
        emit only COMPLETE contrastive pairs): this episode must raw-succeed AND
        the SAME scene must be doable in the OTHER value. If the partner value
        fails, the scene has no complete pair, so BOTH episodes are dropped (each
        returns False). The partner is trial-run once per scene_seed on a throwaway
        instance and cached on the class; the trial calls only _raw_success, so no
        recursion. This is the collection/eval gate; per-episode oracle rate uses
        _raw_success directly (see spike_wiring / tests)."""
        if not self._raw_success():
            return False
        scene_seed = self._seed // 2
        if scene_seed not in attribute_select._pair_ok:
            partner_seed = scene_seed * 2 + (1 - self._seed % 2)
            buddy = attribute_select()
            ok = False
            try:
                kw = dict(self._demo_kwargs)
                kw["seed"] = partner_seed   # same scene_seed -> same scene, other value
                buddy.setup_demo(**kw)
                buddy.play_once()
                ok = bool(buddy._raw_success())
            except Exception:
                ok = False
            finally:
                try:
                    buddy.close_env()
                except Exception:
                    pass
            attribute_select._pair_ok[scene_seed] = ok
        return self._raw_success() and attribute_select._pair_ok[scene_seed]


# --- procedural decals (drawn to RGBA arrays, never written to disk) -------
def _cat_arr(S=256):
    img = Image.new("RGBA", (S, S), (248, 240, 229, 255)); d = ImageDraw.Draw(img)
    cx, cy = S * 0.5, S * 0.52; fur = (238, 150, 60, 255)
    d.polygon([(cx - 0.34 * S, cy - 0.06 * S), (cx - 0.46 * S, cy - 0.48 * S),
               (cx - 0.02 * S, cy - 0.24 * S)], fill=fur)
    d.polygon([(cx + 0.34 * S, cy - 0.06 * S), (cx + 0.46 * S, cy - 0.48 * S),
               (cx + 0.02 * S, cy - 0.24 * S)], fill=fur)
    d.ellipse([cx - 0.40 * S, cy - 0.28 * S, cx + 0.40 * S, cy + 0.44 * S], fill=fur)
    for sx in (-1, 1):
        d.ellipse([cx + sx * 0.18 * S - 0.07 * S, cy - 0.02 * S,
                   cx + sx * 0.18 * S + 0.07 * S, cy + 0.12 * S], fill=(30, 30, 30, 255))
    return np.asarray(img, dtype=np.uint8)


def _dog_arr(S=256):
    img = Image.new("RGBA", (S, S), (247, 240, 230, 255)); d = ImageDraw.Draw(img)
    cx, cy = S * 0.5, S * 0.5; fur = (150, 100, 60, 255); ear = (105, 68, 40, 255)
    d.ellipse([cx - 0.50 * S, cy - 0.22 * S, cx - 0.14 * S, cy + 0.42 * S], fill=ear)
    d.ellipse([cx + 0.14 * S, cy - 0.22 * S, cx + 0.50 * S, cy + 0.42 * S], fill=ear)
    d.ellipse([cx - 0.36 * S, cy - 0.34 * S, cx + 0.36 * S, cy + 0.38 * S], fill=fur)
    d.ellipse([cx - 0.18 * S, cy + 0.06 * S, cx + 0.18 * S, cy + 0.38 * S], fill=(210, 180, 145, 255))
    for sx in (-1, 1):
        d.ellipse([cx + sx * 0.15 * S - 0.06 * S, cy - 0.10 * S,
                   cx + sx * 0.15 * S + 0.06 * S, cy + 0.03 * S], fill=(30, 30, 30, 255))
    return np.asarray(img, dtype=np.uint8)
