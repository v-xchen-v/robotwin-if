"""Evaluation budgets shared by the maintained RoboTwin-IF tasks."""

IF_EVAL_STEP_LIMITS = {
    "bottle_verb": 700,
    "pick_diverse_object": 400,
    "attribute_select": 400,
    "arm_select": 400,
    "stack_sequence": 1200,
    "place_relative": 400,
    "grasp_cube_approach": 400,
}


def apply_if_eval_step_limit(task):
    """Apply the task's fixed policy-action budget only during evaluation."""
    if task.eval_mode:
        task.step_lim = IF_EVAL_STEP_LIMITS[task.task_name]
