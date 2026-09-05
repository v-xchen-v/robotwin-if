"""Pure seed-to-contrast contracts for the maintained IF tasks."""

from dataclasses import dataclass


CONTRACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SeedContract:
    """Describe one repeating, balanced block of episode seeds."""

    task: str
    modes: tuple[str, ...]
    scene_span: int

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
        modes=("left", "right", "front", "back", "on_top"),
        scene_span=5,
    ),
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


def contract_for(task):
    try:
        return IF_SEED_CONTRACTS[task]
    except KeyError as exc:
        raise ValueError(f"unknown maintained IF task: {task!r}") from exc


def describe_seed(task, seed):
    contract = contract_for(task)
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


def expand_block(task, block_index):
    contract = contract_for(task)
    if isinstance(block_index, bool) or not isinstance(block_index, int) or block_index < 0:
        raise ValueError(
            f"block index must be a non-negative integer, got {block_index!r}"
        )
    start = block_index * contract.block_size
    return tuple(range(start, start + contract.block_size))


def first_block_at_or_above(task, candidate_floor):
    contract = contract_for(task)
    candidate_floor = _seed(candidate_floor)
    return (candidate_floor + contract.block_size - 1) // contract.block_size


def validate_complete_blocks(task, seeds):
    """Return retained block ids, rejecting any reordered or partial block."""
    contract = contract_for(task)
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
        block_index = values[cursor] // contract.block_size
        expected = expand_block(task, block_index)
        actual = values[cursor:cursor + contract.block_size]
        if actual != expected:
            raise ValueError(
                f"task {task} has incomplete block {block_index}: "
                f"expected {list(expected)}, got {list(actual)}"
            )
        block_ids.append(block_index)
        cursor += contract.block_size
    return tuple(block_ids)


def mode_denominators(task, seeds):
    contract = contract_for(task)
    validate_complete_blocks(task, seeds)
    counts = {mode: 0 for mode in contract.modes}
    for seed in seeds:
        counts[describe_seed(task, seed).mode] += 1
    return counts
