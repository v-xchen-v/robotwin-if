"""Pure seed-to-contrast contracts for the maintained IF tasks."""

from dataclasses import dataclass


CONTRACT_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class SeedContract:
    """Describe one repeating, balanced block of episode seeds."""

    task: str
    modes: tuple[str, ...]
    scene_span: int
    seed_offsets: tuple[int, ...] = ()
    seed_stride: int = 0

    @property
    def offsets(self):
        return self.seed_offsets or tuple(range(self.block_size))

    @property
    def stride(self):
        return self.seed_stride or self.block_size

    @property
    def block_size(self):
        return len(self.modes)


@dataclass(frozen=True)
class SeedDescription:
    task: str
    seed: int
    block_index: int
    block_offset: int
    mode: str
    scene_index: int
    scene_offset: int


IF_SEED_CONTRACTS = {
    "bottle_verb": SeedContract(
        task="bottle_verb",
        modes=("pick", "shake"),
        scene_span=2,
    ),
    "pick_diverse_object": SeedContract(
        task="pick_diverse_object",
        modes=("seen", "unseen"),
        scene_span=1,
    ),
    "attribute_select": SeedContract(
        task="attribute_select",
        modes=(
            "color:red",
            "color:blue",
            "decal:cat",
            "decal:dog",
            "shape:block",
            "shape:bar",
            "size:big",
            "size:small",
        ),
        scene_span=2,
    ),
    "arm_select": SeedContract(
        task="arm_select",
        modes=("left", "right"),
        scene_span=2,
    ),
    "stack_sequence": SeedContract(
        task="stack_sequence",
        modes=(
            "red>green>blue",
            "red>blue>green",
            "green>red>blue",
            "green>blue>red",
            "blue>red>green",
            "blue>green>red",
        ),
        scene_span=6,
    ),
    "place_relative": SeedContract(
        task="place_relative",
        modes=("left", "right", "on_top"),
        scene_span=5,
        seed_offsets=(0, 1, 4),
        seed_stride=5,
    ),
}

# Read-only metadata for validating archived manifests/results. Not an active task.
ARCHIVED_SEED_CONTRACTS = {
    "grasp_cube_approach": SeedContract(
        task="grasp_cube_approach",
        modes=("top", "side"),
        scene_span=2,
    ),
}


def _seed(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"seed must be a non-negative integer, got {value!r}")
    return value


LEGACY_SPATIAL_CONTRACT = SeedContract(
    "place_relative", ("left", "right", "front", "back", "on_top"), 5)


def contract_for(task, *, legacy=False):
    """Describe active or archived data; use IF_SEED_CONTRACTS for runnable tasks."""
    if task == "place_relative" and legacy:
        return LEGACY_SPATIAL_CONTRACT
    try:
        return (IF_SEED_CONTRACTS | ARCHIVED_SEED_CONTRACTS)[task]
    except KeyError as exc:
        raise ValueError(f"unknown maintained IF task: {task!r}") from exc


def observed_mode(task_name, task):
    """Read the actual scene mode using the same labels as the seed contract."""
    if task_name not in IF_SEED_CONTRACTS:
        raise ValueError(f"Task is not active: {task_name}")
    if task_name in ("bottle_verb", "arm_select"):
        return str(task.mode)
    if task_name == "pick_diverse_object":
        return str(task.target_familiarity)
    if task_name == "attribute_select":
        return f"{task.axis}:{task.AXIS_VALUES[task.axis][int(task.value)]}"
    if task_name == "stack_sequence":
        return ">".join(task.COLOR_NAMES[int(index)] for index in task.perm)
    return str(task.direction)


def describe_seed(task, seed):
    """Stable physical seed identity, including retired modes for archive readers.

    block_offset is the original seed slot; active on_top retains slot 4.
    Use validate_active_seeds before running a task.
    """
    contract = contract_for(task, legacy=True)
    seed = _seed(seed)
    offset = seed % contract.block_size
    return SeedDescription(
        task=task,
        seed=seed,
        block_index=seed // contract.block_size,
        block_offset=offset,
        mode=contract.modes[offset],
        scene_index=seed // contract.scene_span,
        scene_offset=seed % contract.scene_span,
    )


def expand_block(task, block_index, *, legacy=False):
    contract = contract_for(task, legacy=legacy)
    if isinstance(block_index, bool) or not isinstance(block_index, int) or block_index < 0:
        raise ValueError(
            f"block index must be a non-negative integer, got {block_index!r}"
        )
    start = block_index * contract.stride
    return tuple(start + offset for offset in contract.offsets)


def first_block_at_or_above(task, candidate_floor):
    contract = contract_for(task)
    candidate_floor = _seed(candidate_floor)
    return (candidate_floor + contract.stride - 1) // contract.stride


def validate_complete_blocks(task, seeds, *, legacy=False):
    """Return retained block ids, rejecting any reordered or partial block."""
    contract = contract_for(task, legacy=legacy)
    values = tuple(_seed(seed) for seed in seeds)
    if not values:
        raise ValueError("seed list must not be empty")
    if tuple(sorted(values)) != values:
        raise ValueError("seeds must be in strictly ascending block order")
    if len(set(values)) != len(values):
        raise ValueError("seeds must be unique")

    block_ids = []
    cursor = 0
    while cursor < len(values):
        block_index = values[cursor] // contract.stride
        expected = expand_block(task, block_index, legacy=legacy)
        actual = values[cursor:cursor + contract.block_size]
        if actual != expected:
            raise ValueError(
                f"task {task} has incomplete block {block_index}: "
                f"expected {list(expected)}, got {list(actual)}"
            )
        block_ids.append(block_index)
        cursor += contract.block_size
    return tuple(block_ids)


def mode_denominators(task, seeds, *, legacy=False):
    contract = contract_for(task, legacy=legacy)
    validate_complete_blocks(task, seeds, legacy=legacy)
    counts = {mode: 0 for mode in contract.modes}
    for seed in seeds:
        counts[describe_seed(task, seed).mode] += 1
    return counts


def contract_for_seeds(task, seeds):
    """Read balanced historical plans whose schema predates sparse spatial blocks."""
    legacy = task == "place_relative" and any(seed % 5 in (2, 3) for seed in seeds)
    validate_complete_blocks(task, seeds, legacy=legacy)
    return contract_for(task, legacy=legacy)


def validate_active_seeds(task, seeds):
    if task not in IF_SEED_CONTRACTS:
        raise ValueError(f"Task is retired: {task}")
    for seed in seeds:
        if describe_seed(task, seed).mode not in IF_SEED_CONTRACTS[task].modes:
            raise ValueError(f"Retired mode for {task} seed {seed}; use the spatial3 manifest")
    return validate_complete_blocks(task, seeds)
