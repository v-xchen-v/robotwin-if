---
description: Critically review a RoboTwin IF task DESIGN for benchmark validity — single-axis isolation, decoy neutrality, oracle feasibility, ACTION-OOD confound, metric resolution, prior strength, and eval-protocol dependency. Not a code review.
argument-hint: <task_name | design-doc section> [eval-protocol: zeroshot | native-ft | ifext-ft]
---

Arguments (space-separated): **$ARGUMENTS**

Parse: **1st token = the task** (a `tasks/envs/<name>.py`, or a design-doc feature/section under `docs/`). **2nd token (optional) = the intended eval protocol**: `zeroshot` (native-pretrained, no finetune), `native-ft` (finetuned only on raw RoboTwin), or `ifext-ft` (finetuned on the IF-Ext data this task generates). If the protocol is absent, **review under all three and flag where the verdict changes** — it usually does (dimension 7).

You are reviewing whether this task is a **valid single-axis instruction-following diagnostic**, not whether the code is clean. A task can run perfectly and still measure the wrong thing. Be critical: name confounds, not compliments.

## Inputs to read first
- The task env (`tasks/envs/<name>.py`): what varies per episode, what `check_success` actually measures, how the oracle acts.
- Any design note under `docs/features/` and `notes/<...>/` for this task.
- If it's a verb/action task, check the native task set for precedent: `ls third_party/robotwin/envs/*.py` and grep for the action verb — is the commanded action seen in native or new? (This feeds dimension 5.)

## Review dimensions

For each: give a **verdict — `OK` / `RISK` / `BLOCKER`** — a one-line reason, and if not OK a concrete mitigation. Don't rubber-stamp.

1. **Axis isolation** — Is the named axis the ONLY thing that varies across the compared conditions? List everything else that changes; each is a confound. (e.g. if "verb" is the axis but the initial scene also differs, geometry leaks the answer.)
2. **Decoy / neutrality** — Is the named axis the *unique* distinguishing signal for choosing the right behavior? Are object identity / geometry / position neutral so the policy can't shortcut past reading the instruction?
3. **Oracle feasibility** — Can the oracle hit EVERY target value of the axis at ~90% from the shared setup? (Not just the easy value.) Cite the mic-drawer lesson: a value the oracle can't reach makes the task unmeasurable. → see [[mic-drawer-oracle-infeasible]].
4. **Visual distinguishability** — Are the different target outcomes distinguishable on the eval cameras? If two values render near-identically, the policy (and the metric) can't separate them.
5. **ACTION-OOD (the centerpiece)** — Is any commanded action out-of-distribution relative to the eval model's training? Work through, in order:
   - **Severity**: is it a genuinely *novel skill* (like threading a needle), or just a *new direction / composition of seen sub-skills* (grasp-then-move-the-other-way)? Decompose the motion into sub-skills and check each against native. New-composition ≪ new-skill in difficulty.
   - **Executability**: is it *oracle-proven* achievable (physically possible, high oracle success)? "Hard for the policy" ≠ "impossible."
   - **In-distribution for the protocol?**: OOD only bites the model that never trained on it. If the eval protocol is `ifext-ft` (finetuned on the data THIS task generates), the action is in-distribution and the OOD concern largely dissolves. For `zeroshot` / `native-ft` it stands.
   - **THE CONFOUND (the thing that kills the diagnostic)**: if the action is OOD *and* the metric is binary success, a **0 is ambiguous** — you cannot separate "ignored the instruction" from "read it but couldn't execute the OOD action." That collapses the axis. State whether this task has that confound under the given protocol.
   - **Mitigation**: (a) primary metric = **direction / graded progress toward the commanded value**, not binary success — a policy that moves the right way but under-executes is then distinguishable from one that goes the wrong way; (b) report each value separately + the **gap**; (c) or switch the task to actions the eval model can already execute (seen-vs-seen).
6. **Metric resolution** — Does `check_success` avoid floor/ceiling effects and *disambiguate the failure modes* dimension 5 cares about? Binary band → prone to floors; directional/graded → keeps resolution even when strict success is low. Does the reversal case fail (Layer-B: wrong value → False)?
7. **Prior strength** — How strong is the "habitual" prior the instruction fights, and is it **data-grounded** (native training only ever does X to this object) or merely **semantic** (X is the stereotypical action)? A data-grounded prior is a harder, more realistic test; a weak prior tests a milder failure. Note which this is — it's the flip side of the OOD tradeoff: the strongest priors often come from the value native never demonstrates (= the OOD one).
8. **Eval-protocol dependency** — State plainly whether the task's validity *changes with the eval protocol*. The common pattern: an asymmetric task (one seen value + one OOD value) is **clean under `ifext-ft`** (both in-distribution, strong prior retained) but **confounded under `zeroshot` / `native-ft`** (OOD value's 0 is ambiguous). If validity is protocol-dependent, that is a `RISK` the task must document, not hide.

## Output
- A per-dimension verdict table (dimension · OK/RISK/BLOCKER · reason).
- A short **synthesis**: is this a valid single-axis diagnostic *as-is*, for *which eval protocol*, and what is the single highest-leverage change.
- If action-OOD creates a confound: state the recommended metric (directional/graded + report gap) and whether a seen-vs-seen control task is worth adding.
- Be honest about the tradeoff — don't recommend "use only seen actions" if that throws away a valuable data-grounded prior; surface both and let the reader choose.
