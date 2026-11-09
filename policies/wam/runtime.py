"""Check that an official permissive loader covered every inference parameter."""


def checkpoint_schema(path):
    import torch
    from torch._subclasses.fake_tensor import FakeTensorMode
    # Inspect tensor metadata without allocating a second copy of multi-GB weights.
    with FakeTensorMode():
        return torch.load(path, map_location="cpu", weights_only=True)


def require_complete_state(module, state, label):
    if not isinstance(state, dict):
        raise ValueError(f"Checkpoint is missing {label}")
    expected = module.state_dict()
    missing, extra = sorted(expected.keys() - state.keys()), sorted(state.keys() - expected.keys())
    mismatched = [name for name in expected.keys() & state.keys()
                  if tuple(expected[name].shape) != tuple(state[name].shape)]
    if missing or extra or mismatched:
        raise ValueError(f"{label} checkpoint coverage mismatch: missing={missing}, extra={extra}, shapes={mismatched}")
