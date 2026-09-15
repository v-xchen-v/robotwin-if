#!/usr/bin/env python3
"""One bounded real-robot oracle probe; run externally under timeout on one idle GPU.

Unlike CPU regression tests, this loads SAPIEN rendering/assets. It evaluates the
raw predicate only, so the paired scene must be separately qualified before reuse.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--pick-lift',type=float,default=.2)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    from tools.sim_device import pin_renderer
    pin_renderer()
    from policies.xvla.eval import load_task
    task,config=load_task(ROOT/'third_party/robotwin','bottle_verb','demo_clean')
    result=dict(seed=args.seed,pick_lift=args.pick_lift,started_at=datetime.now(timezone.utc).isoformat(),
                raw_predicate_only=True,paired_oracle_qualified=False)
    trace=[]
    try:
        random.seed(args.seed)
        task.PICK_LIFT=args.pick_lift
        task.setup_demo(now_ep_num=0,seed=args.seed,is_test=True,**config)
        observe=task._pick_monitor.observe
        def record(t,p,q):
            before=task._pick_monitor.sample_time
            observe(t,p,q)
            if task._pick_monitor.sample_time!=before:
                trace.append(dict(t=t,p=[float(v) for v in p],q=[float(v) for v in q],
                    state=task._pick_monitor.state,stable_seconds=task._pick_monitor.stable_seconds))
        task._pick_monitor.observe=record
        info=task.play_once()
        result.update(mode=task.mode,bottle_id=task.bottle_id,plan_success=bool(task.plan_success),
            raw_success=bool(task._raw_success(task.mode)),signals=task.eval_signals(),info=info,
            pick_ever_succeeded=any(sample['state']=='success' for sample in trace))
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}'
        traceback.print_exc()
    finally:
        (output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        (output/'trajectory.json').write_text(json.dumps(trace,allow_nan=False)+'\n')
        task.close_env()
    print(json.dumps(result,allow_nan=False))
    passed=(result.get('plan_success') and result.get('raw_success')
            and (result.get('mode')=='pick' or not result.get('pick_ever_succeeded')))
    return 0 if passed else 1


if __name__=='__main__':sys.exit(main())
