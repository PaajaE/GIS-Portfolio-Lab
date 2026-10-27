# Masked evaluation intervals: rule (pre-declared)

> Written 2026-10-25, **before** reading the ICS-209 narratives of any pool fire, and before any
> calibration or validation run. Implements PLAN §2.3 ("days whose growth the ICS-209 / InciWeb record
> attributes mainly to firing (burnout) operations or long-range spotting are masked").

## Unit
A scan interval (t_{k−1}, t_k] between consecutive IR perimeters. Masked intervals are excluded from
O2/O3 scoring. The fire is not dropped and propagation still runs through them.

## Evidence
Situation reports (ICS-209; ICS-209-PLUS for 1999–2020; InciWeb/agency updates for later fires) whose
report period overlaps the interval. Only statements about what **happened** in the period count:
`SIGNIF_EVENTS_SUMMARY`, `OBS_FIRE_BEHAVE`, `REMARKS`, `CURRENT_THREAT_NARR`. Planned actions and
forecasts (`PLANNED_ACTIONS`, `PROJECTED_ACTIVITY_NARR`, `WEATHER_CONCERNS_NARR`) are ignored.

## Decision
1. Candidates: reports containing firing terms (firing, burnout, burn out, burning operation(s),
   backfire, back fire, aerial ignition, PSD, plastic sphere, strategic/tactical firing) or spotting
   terms (spot fire(s), spotting) with a distance or "long-range". The search is case-insensitive.
2. An interval is **masked** only if a report states, or plainly implies, that **most of the period's
   growth** came from firing operations or long-range spotting. Examples: "growth was from burnout
   operations"; "acres increase due to firing"; "fire spotted 1 mile across X and grew N acres".
3. Mentions of firing as one activity among others, of firing being completed, of short-range
   spotting, or of planned firing are **not** enough.
4. Every masked interval is listed with the quoted evidence and the report date. Every candidate that
   was not masked is listed with a one-line reason.
5. The list is frozen (committed) before calibration (M3), and never changed after model results on
   the fire are seen.
