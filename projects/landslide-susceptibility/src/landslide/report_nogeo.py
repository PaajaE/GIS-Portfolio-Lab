"""validation/NOGEO_TEST.md from validation/nogeo_test.json (every number comes from the JSON)."""

from __future__ import annotations

import json

from . import config as C


def f(x, nd=3):
    return "–" if x is None else f"{x:.{nd}f}"


def ci(d):
    return f"{f(d['value'])} ({f(d['ci95'][0])}–{f(d['ci95'][1])})"


def dl(d):
    return f"{d['value']:+.3f} ({d['ci95'][0]:+.3f} to {d['ci95'][1]:+.3f})"


def table(block, title) -> list[str]:
    L = [f"### {title}", "", "| Model | AUC rainfall-stratified | AUC within watershed |", "|---|---|---|"]
    for m, lab in (("current", "Current (with geology)"), ("no_geology", "Without geology"), ("slope", "Slope alone")):
        L.append(f"| {lab} | {ci(block[m]['auc_rain_stratified'])} | {ci(block[m]['auc_within_huc'])} |")
    d = block["delta_no_geology_minus_current"]
    L += ["", f"- Without − current: stratified {dl(d['auc_rain_stratified'])}; within {dl(d['auc_within_huc'])}"]
    for m in ("current", "no_geology"):
        d = block[f"delta_{m}_minus_slope"]
        L.append(f"- {m.replace('_', ' ')} − slope: stratified {dl(d['auc_rain_stratified'])}; within "
                 f"{dl(d['auc_within_huc'])}")
    return L + [""]


def write() -> str:
    r = json.loads((C.VALIDATION / "nogeo_test.json").read_text())
    D, W, R = r["decision"], r["watauga"], r["ranking_and_stability"]
    yn = lambda b: "**pass**" if b else "**fail**"  # noqa: E731
    L = ["# Test: 5 m logistic regression without geology predictors", "",
         "Generated from `validation/nogeo_test.json`. Design and decision rule fixed before computation "
         "(METHOD §Validation, commit 0ae693d). Paired comparisons on the same bootstrap resamples; 95 % intervals. "
         "Scores are relative ranks, not probabilities.", "",
         "## Decision", "",
         f"- R1 AOI non-inferiority (both lower bounds ≥ −0.01): {yn(D['R1_aoi_non_inferior'])}",
         f"- R2a leave-one-county-out improvement (lower bound > 0): {yn(D['R2a_leave_one_county_out'])}",
         f"- R2b Watauga transfer improvement (lower bound > 0): {yn(D['R2b_watauga'])}",
         f"- **Replace the current model: {'yes' if D['replace_current_model'] else 'no'}**", "",
         "## Results", ""]
    L += table(r["aoi_loho"], "Inside the AOI (leave-one-HUC-12-out, 500 m buffer)")
    L += table(r["leave_one_county_out"], "Leave-one-county-out")
    L += ["### Watauga County (indicative)", "",
          f"{W['test_outlines']} test outlines, {W['test_cells']:,} proxy cells; bootstrap over outlines and negative cells. "
          "Test labels come from Nearmap imagery (a different method). The 1940 outlines are almost all location "
          "confidence \"Low\" and affect only the temporal model.", "",
          "| Score | AUC | AUC rainfall-stratified |", "|---|---|---|"]
    for k, lab in (("transfer_current", "AOI model with geology, transferred"),
                   ("transfer_no_geology", "AOI model without geology, transferred"), ("slope_alone", "Slope alone"),
                   ("temporal_1940_current", "1940-trained, with geology (descriptive)"),
                   ("temporal_1940_no_geology", "1940-trained, without geology (descriptive)")):
        L.append(f"| {lab} | {f(W[k]['auc'])} ({f(W[k]['ci95'][0])}–{f(W[k]['ci95'][1])}) | {f(W[k]['auc_rain_stratified'])} |")
    L += ["", f"- Without − with geology (transfer): {dl(W['delta_transfer_no_geology_minus_current'])}",
          f"- Without geology − slope (transfer): {dl(W['delta_transfer_no_geology_minus_slope'])}", "",
          "### Ranking and stability (hillslope part of the uniform domain sample)", "",
          f"- Spearman between the final scores: {f(R['spearman_final_scores'])}; share of the current top-10 % that "
          f"stays in the no-geology top-10 %: {100 * R['top10_overlap_share']:.1f} %.",
          "- Top-10 % share by geology group (hillslope share in brackets): " + "; ".join(
              f"group {g}: current {100 * R['top10_share_by_geology']['current'].get(g, 0):.1f} %, no-geology "
              f"{100 * R['top10_share_by_geology']['no_geology'].get(g, 0):.1f} % "
              f"({100 * v:.1f} %)" for g, v in R["hillslope_share_by_geology"].items()) + ".",
          "- Stability (30 HUC-12 bootstrap refits; top-10 % cells staying in the top 10 % in ≥ 90 % of refits / falling "
          "below the top 20 %): " + "; ".join(
              f"{m.replace('_', ' ')} {100 * v['top10_stays_in_top10_in_90pct_of_refits']:.1f} % / "
              f"{100 * v['top10_p90_class_beyond_20']:.1f} %" for m, v in R["stability"].items()) + ".", ""]
    text = "\n".join(L)
    (C.VALIDATION / "NOGEO_TEST.md").write_text(text)
    return text


if __name__ == "__main__":
    write()
