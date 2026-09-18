"""Shared process ownership, frozen-source checks and scene guards for remote evaluation."""
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import run_formal_policy_suite as formal

# Rounded historical model peaks, in MiB; four GiB remain unreserved.
MODEL_MIB = dict(xvla=4608, lingbot_va=34816, lingbot_vla=9728,
                 vlact=10240, dm05=12800, hy_vla=10240)
MODEL_ADMISSION_MIB = 44 * 1024


def proc_identity(pid):
    try:
        value = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if value[0] == 'Z':
            return None
        return dict(pid=pid, start_ticks=value[19],
                    argv=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1])
    except FileNotFoundError:
        return None


class AdoptedProcess:
    """A verified live child retained when only its serial supervisors exit."""
    def __init__(self, pid, start_ticks):
        identity = proc_identity(pid)
        assert identity and identity['start_ticks'] == start_ticks, ('PID identity changed', pid)
        assert os.getpgid(pid) == pid, ('Not an isolated job process group', pid)
        self.pid, self.start_ticks = pid, start_ticks

    def poll(self):
        identity = proc_identity(self.pid)
        return None if identity and identity['start_ticks'] == self.start_ticks else 0

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(str(self.pid), timeout)
            time.sleep(.1)
        return 0


def stop_process(process):
    if isinstance(process, AdoptedProcess) and process.poll() is not None:
        return  # Never signal a PID that has exited or been reused.
    formal.stop(process)


def check_sources(base):
    formal.check_sources(base)
    for name, sha in formal.read(base / 'support/parallel-source-hashes.json').items():
        assert formal.digest(ROOT / name) == sha, ('Scheduler source changed', name)


def check_parent_scene(base, policy, spec, seed, instruction, obs, env, path):
    """Parent RGB/state are already shared by all policies; verdicts are not reused."""
    import numpy as np
    from policies.xvla.client import encode_proprio
    parent = Path(formal.read(base / 'plan.json')['old_run'])
    # X-VLA stores the 20-D rot6d encoding used by encode_proprio here. Other
    # adapters store 16-D quaternion EE or 14-D joint states in their NPZs.
    task = spec['task']
    directory = parent / 'xvla' / task
    stem = formal.prefix(task, seed)
    marker = formal.read(directory / (stem + '_provenance.json'))
    result_path = directory / (stem + '_result.json')
    initial_path = directory / (stem + '_initial_observation.npz')
    for p in (result_path, initial_path):
        assert formal.digest(p) == marker['files_sha256'][p.name], ('Parent artifact changed', p)
    record = formal.read(result_path)
    assert instruction == record['instruction'] and env.step_lim == record['step_limit'] == 400
    with np.load(initial_path) as expected:
        for camera in ('head_camera', 'left_camera', 'right_camera'):
            np.testing.assert_array_equal(obs['observation'][camera]['rgb'], expected[camera])
        np.testing.assert_allclose(encode_proprio(obs), expected['proprio'], rtol=0, atol=1e-6)
    formal.write(path('_same_host_scene.json'), dict(reference=str(directory / stem), reference_policy='xvla',
        reference_verdict_reused=False, initial_sha256=formal.digest(initial_path),
        exact_rgb=True, instruction=True, state_atol=1e-6,
        checker_version=spec['success_checker_version']))
