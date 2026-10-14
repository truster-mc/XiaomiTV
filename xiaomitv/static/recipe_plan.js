"use strict";

// Decide which checkboxes a recipe (or one of its steps) should tick for the scanned TV.
// recipe: {steps: [{manual, packages}]}; rows: scan rows; step: index of one step, or null/undefined for all.
function planTick(recipe, rows, step) {
  const byName = new Map(rows.map((r) => [r.package, r]));
  const steps = step === null || step === undefined ? recipe.steps : [recipe.steps[step]];
  const auto = new Set();
  const manual = new Set();
  for (const s of steps) {
    for (const pkg of s.packages) (s.manual ? manual : auto).add(pkg);
  }
  const plan = { tick: [], skipped: { not_on_tv: [], disabled: [], locked: [], manual: [] } };
  for (const pkg of auto) {
    const row = byName.get(pkg);
    if (!row) plan.skipped.not_on_tv.push(pkg);
    else if (!row.enabled) plan.skipped.disabled.push(pkg);
    else if (!row.selectable) plan.skipped.locked.push(pkg);
    else plan.tick.push(pkg);
  }
  for (const pkg of manual) if (!auto.has(pkg)) plan.skipped.manual.push(pkg);
  return plan;
}

if (typeof module !== "undefined") module.exports = { planTick };
