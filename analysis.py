#!/usr/bin/env python3
"""Reproducible, descriptive unemployment analysis of two distinct supplied datasets."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RATE = "unemployment_rate_pct"
LPR = "labour_participation_rate_pct"
NUMERIC = [RATE, "estimated_employed", LPR]
RENAME = {
    "Region": "state", "Date": "date", "Frequency": "frequency",
    "Estimated Unemployment Rate (%)": RATE,
    "Estimated Employed": "estimated_employed",
    "Estimated Labour Participation Rate (%)": LPR,
    "Area": "area", "Region.1": "macro_region",
    "longitude": "source_longitude_label", "latitude": "source_latitude_label",
}
PERIODS = {
    "pre_covid": ["2020-01", "2020-02", "2020-03"],
    "first_wave": ["2020-04", "2020-05"],
    "later_recovery": ["2020-08", "2020-09", "2020-10"],
}


def require(condition: bool, message: str) -> None:
    """Raise an actionable error even when Python is run with optimization."""
    if not condition:
        raise ValueError(message)


def clean_csv(path: Path, area_level: bool) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv(path)
    blank = int(raw.isna().all(axis=1).sum())
    df = raw.dropna(how="all").copy()
    df.columns = df.columns.str.strip()
    require(not df.columns.duplicated().any(), f"Duplicate headers in {path.name}")
    df = df.rename(columns=RENAME)
    for column in df.select_dtypes(include="object"):
        df[column] = df[column].str.strip()
    required = ["state", "date", "frequency", *NUMERIC, "area" if area_level else "macro_region"]
    require(set(required).issubset(df), f"Missing required columns in {path.name}")
    require(not df[required].isna().any().any(), f"Partial missing rows in {path.name}")
    for column in ["state", "frequency", "area" if area_level else "macro_region"]:
        require(df[column].ne("").all(), f"Blank {column} in {path.name}")
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="raise")
    require(df["date"].dt.is_month_end.all(), f"Non-month-end date in {path.name}")
    require(df["frequency"].isin(["Monthly", "M"]).all(), f"Unexpected frequency in {path.name}")
    df["frequency"] = "Monthly"
    for column in NUMERIC:
        df[column] = pd.to_numeric(df[column], errors="raise")
        require(np.isfinite(df[column]).all(), f"Non-finite {column} in {path.name}")
    for column in [RATE, LPR]:
        require(df[column].between(0, 100).all(), f"Out-of-range percentage in {path.name}")
    require(df["estimated_employed"].ge(0).all(), f"Negative employment count in {path.name}")
    require(df["estimated_employed"].mod(1).eq(0).all(), f"Fractional employment count in {path.name}")
    df["estimated_employed"] = df["estimated_employed"].astype("int64")
    keys = ["state", "area", "date"] if area_level else ["state", "date"]
    require(not df.duplicated(keys).any(), f"Duplicate observation keys in {path.name}; investigate rather than silently aggregate")
    if area_level:
        require(set(df["area"]) == {"Rural", "Urban"}, "Expected Rural and Urban areas")
    else:
        require(df.groupby("state")["macro_region"].nunique().eq(1).all(), "Inconsistent macro-region assignments")
    df["month"] = df["date"].dt.strftime("%Y-%m")
    df = df.sort_values(keys).reset_index(drop=True)
    info = {
        "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "raw_rows": len(raw), "fully_blank_rows_removed": blank, "clean_rows": len(df),
        "states_or_territories": int(df["state"].nunique()),
        "first_month": df["month"].min(), "last_month": df["month"].max(),
        "months": int(df["month"].nunique()), "duplicate_keys": 0,
        "partial_missing_required_values": 0,
    }
    if area_level:
        info["observed_state_area_pairs"] = len(df[["state", "area"]].drop_duplicates())
    else:
        info["source_coordinate_label_warning"] = (
            "Source latitude reaches >90 degrees and the two ranges appear swapped. "
            "Labels are retained as source_*_label fields, not verified or used for mapping."
        )
    return df, info


def coverage(df: pd.DataFrame, entities: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.period_range(df["date"].min(), df["date"].max(), freq="M").astype(str)
    pairs = df[entities].drop_duplicates().sort_values(entities)
    expected = pairs.merge(pd.DataFrame({"month": months}), how="cross")
    missing = expected.merge(df[entities + ["month"]], how="left", indicator=True)
    missing = missing.loc[missing["_merge"].eq("left_only"), entities + ["month"]]
    counts = df.groupby(entities).agg(observed_months=("month", "nunique")).reset_index()
    counts["expected_months"] = len(months)
    counts["missing_months"] = counts["expected_months"] - counts["observed_months"]
    return counts, missing


def complete_entities(df: pd.DataFrame, entities: list[str], months: list[str]) -> pd.DataFrame:
    """Select entities with every requested month; never impute missing rate observations."""
    counts = df.loc[df["month"].isin(months)].groupby(entities)["month"].nunique()
    return counts[counts.eq(len(months))].reset_index()[entities]


def period_table(df: pd.DataFrame, entities: list[str], periods: dict[str, list[str]]) -> pd.DataFrame:
    months = [month for values in periods.values() for month in values]
    require(len(months) == len(set(months)), "Periods must be disjoint")
    panel = complete_entities(df, entities, months)
    require(len(panel) > 0, "No entities cover the requested periods")
    selected = df.merge(panel, on=entities, validate="many_to_one")
    result = panel.copy()
    for label, selected_months in periods.items():
        means = selected.loc[selected["month"].isin(selected_months)].groupby(entities)[[RATE, LPR]].mean()
        result = result.merge(means.rename(columns={RATE: f"{label}_rate_pct", LPR: f"{label}_lpr_pct"}), on=entities, validate="one_to_one")
    result["first_wave_change_pp"] = result["first_wave_rate_pct"] - result["pre_covid_rate_pct"]
    recovery = "later_recovery" if "later_recovery" in periods else "june"
    result[f"{recovery}_change_from_pre_pp"] = result[f"{recovery}_rate_pct"] - result["pre_covid_rate_pct"]
    result["first_wave_lpr_change_pp"] = result["first_wave_lpr_pct"] - result["pre_covid_lpr_pct"]
    result[f"{recovery}_lpr_change_from_pre_pp"] = result[f"{recovery}_lpr_pct"] - result["pre_covid_lpr_pct"]
    return result


def save_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, date_format="%Y-%m-%d", float_format="%.6f")


def markdown_table(df: pd.DataFrame) -> str:
    headers = [str(x) for x in df.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in df.itertuples(index=False, name=None):
        values = [f"{v:.2f}" if isinstance(v, (float, np.floating)) else str(v) for v in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def finish(fig: plt.Figure, path: Path, caption: str) -> None:
    fig.text(0.01, 0.01, caption, ha="left", va="bottom", fontsize=8, color="#455568", wrap=True)
    fig.tight_layout(rect=(0, 0.065, 1, 1))
    fig.savefig(path, dpi=170, facecolor="white")
    plt.close(fig)


def make_charts(state: pd.DataFrame, historical: pd.DataFrame, paired: pd.DataFrame,
                monthly: pd.DataFrame, region: pd.DataFrame,
                area_monthly: pd.DataFrame, area_periods: pd.DataFrame, out: Path) -> None:
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "font.size": 10, "axes.grid": True,
                         "grid.alpha": 0.2, "axes.axisbelow": True})
    colors = {"Rural": "#147d92", "Urban": "#ce6d32"}
    x = np.arange(len(monthly))
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for ax, column, title in zip(axes, [RATE, LPR], ["Unemployment rate", "Labour participation rate"]):
        ax.plot(x, monthly[f"available_{column}"], "o--", color="#7c8593", label="All available states")
        ax.plot(x, monthly[f"balanced_{column}"], "o-", color="#2858a5", label=f"Same {len(paired)} states every month")
        ax.axvspan(2.5, 4.5, color="#e8b57b", alpha=0.25, label="Apr–May 2020")
        ax.set(ylabel="Unweighted state mean (%)", title=title)
        ax.legend(loc="upper right", fontsize=8)
    axes[-1].set_xticks(x, monthly["month"], rotation=45, ha="right")
    axes[-1].set_xlabel("Actual file ends October 2020; available n=" + ",".join(monthly["available_states"].astype(str)))
    fig.suptitle("2020 unemployment spike and participation decline", fontsize=14, fontweight="bold")
    finish(fig, out / "state_monthly_trends.png", "Means give equal weight to states/territories; they are not official national population-weighted estimates.")

    ranked = paired.sort_values("first_wave_change_pp")
    fig, ax = plt.subplots(figsize=(10, 9))
    y = np.arange(len(ranked))
    ax.hlines(y, ranked["pre_covid_rate_pct"], ranked["first_wave_rate_pct"], color="#a8b3c2", linewidth=2)
    for col, label, color, marker in [
        ("pre_covid_rate_pct", "Jan–Mar", "#2858a5", "o"),
        ("first_wave_rate_pct", "Apr–May", "#ce6d32", "o"),
        ("later_recovery_rate_pct", "Aug–Oct", "#147d92", "D")]:
        ax.scatter(ranked[col], y, label=label, color=color, marker=marker, s=38, zorder=3)
    ax.set_yticks(y, ranked["state"])
    ax.set(xlabel="Monthly unemployment rate averaged within period (%)", title=f"Paired state comparisons ({len(paired)} complete states/territories)")
    ax.legend(loc="lower right")
    finish(fig, out / "paired_state_changes.png", "States ranked by Apr–May minus Jan–Mar change. These descriptive differences do not identify a causal Covid effect.")

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(region))
    for i, (period, label, color) in enumerate([
        ("pre_covid", "Jan–Mar", "#2858a5"), ("first_wave", "Apr–May", "#ce6d32"),
        ("later_recovery", "Aug–Oct", "#147d92")]):
        ax.bar(x + (i - 1) * .25, region[f"{period}_rate_pct"], width=.25, label=label, color=color)
    ax.set_xticks(x, [f"{row.macro_region}\n(n={row.states})" for row in region.itertuples()])
    ax.set(ylabel="Unweighted state mean unemployment (%)", title="Macro-region comparisons on the same complete state panel")
    ax.legend()
    finish(fig, out / "macro_region_comparison.png", "Region labels come from the source. Small regional samples and different state populations limit direct comparisons.")

    fig, ax = plt.subplots(figsize=(11, 5.5))
    months = sorted(area_monthly["month"].unique())
    for area in ["Rural", "Urban"]:
        subset = area_monthly.loc[area_monthly["area"].eq(area)].set_index("month").loc[months]
        ax.plot(np.arange(len(months)), subset[RATE], "o-", label=f"{area}: same {int(subset['states'].iloc[0])} states", color=colors[area])
    covid_idx = months.index("2020-04")
    ax.axvspan(covid_idx - .5, covid_idx + 1.5, color="#e8b57b", alpha=.25)
    ax.set_xticks(np.arange(len(months)), months, rotation=45, ha="right")
    ax.set(ylabel="Unweighted state mean unemployment (%)", title="Historical rural and urban trends: May 2019–June 2020")
    ax.legend()
    finish(fig, out / "rural_urban_trends.png", "Only states with both areas present in all 14 months enter this balanced panel. Short history cannot establish recurring seasonality.")

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for ax, column, title in zip(axes, ["rate_pct", "lpr_pct"], ["Unemployment", "Labour participation"]):
        for area in ["Rural", "Urban"]:
            row = area_periods.loc[area_periods["area"].eq(area)].iloc[0]
            ax.plot([0, 1, 2], [row[f"{p}_{column}"] for p in ["pre_covid", "first_wave", "june"]], "o-", label=area, color=colors[area])
        ax.set_xticks([0, 1, 2], ["Jan–Mar", "Apr–May", "June"])
        ax.set(title=title, ylabel="Unweighted state/area mean (%)")
        ax.legend()
    fig.suptitle("Rural–urban period comparisons on the same matched states", fontweight="bold")
    finish(fig, out / "rural_urban_period_comparison.png", f"Both areas and all January–June months required: {int(area_periods['states'].iloc[0])} matched states. June is one month, not sustained recovery.")

    heat = state.pivot(index="state", columns="month", values=RATE).sort_index()
    fig, ax = plt.subplots(figsize=(10, 10))
    cmap = plt.get_cmap("YlOrRd").copy()
    cmap.set_bad("#d5d9df")
    img = ax.imshow(heat.to_numpy(), aspect="auto", cmap=cmap, vmin=0, vmax=max(50, heat.max().max()))
    ax.grid(False)
    ax.set_xticks(range(len(heat.columns)), heat.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(heat)), heat.index)
    ax.set_title("State unemployment rates: heterogeneity and missing observations")
    fig.colorbar(img, ax=ax, label="Unemployment rate (%)", fraction=.04)
    finish(fig, out / "state_month_heatmap.png", "Grey cells are missing, not zero. Rates are individual state observations; no geographic coordinates were used.")


def run(data_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = output_dir / "tables"
    charts = output_dir / "charts"
    tables.mkdir(exist_ok=True)
    charts.mkdir(exist_ok=True)
    historical, hist_info = clean_csv(data_dir / "Unemployment in India.csv", area_level=True)
    state, state_info = clean_csv(data_dir / "Unemployment_Rate_upto_11_2020.csv", area_level=False)
    save_csv(historical, output_dir / "cleaned_historical_state_area.csv")
    save_csv(state, output_dir / "cleaned_2020_state.csv")
    for df, entities, label, info in [
        (historical, ["state", "area"], "historical", hist_info),
        (state, ["state"], "2020_state", state_info)]:
        entity_coverage, missing = coverage(df, entities)
        save_csv(entity_coverage, tables / f"{label}_entity_coverage.csv")
        save_csv(missing, tables / f"{label}_missing_observations.csv")
        info["missing_entity_month_cells"] = len(missing)
        monthly_count = df.groupby(["month"] + (["area"] if label == "historical" else [])).size().reset_index(name="observations")
        save_csv(monthly_count, tables / f"{label}_monthly_coverage.csv")
        save_csv(df[NUMERIC].describe().reset_index(names="statistic"), tables / f"{label}_descriptive_statistics.csv")

    paired = period_table(state, ["state"], PERIODS)
    paired = paired.merge(state[["state", "macro_region"]].drop_duplicates(), on="state", validate="one_to_one")
    save_csv(paired.sort_values("first_wave_change_pp", ascending=False), tables / "paired_state_periods.csv")
    # Requiring all ten months ensures chart membership stays fixed throughout the line.
    balanced_states = complete_entities(state, ["state"], sorted(state["month"].unique()))
    require(set(balanced_states["state"]) == set(paired["state"]), "Comparison and trend panels differ; labels need updating")
    balanced = state.merge(balanced_states, on="state", validate="many_to_one")
    monthly = state.groupby("month").agg(
        available_unemployment_rate_pct=(RATE, "mean"),
        available_labour_participation_rate_pct=(LPR, "mean"), available_states=("state", "nunique"))
    means = balanced.groupby("month").agg(
        balanced_unemployment_rate_pct=(RATE, "mean"),
        balanced_labour_participation_rate_pct=(LPR, "mean"), balanced_states=("state", "nunique"))
    monthly = monthly.join(means).reset_index()
    save_csv(monthly, tables / "state_monthly_unweighted_means.csv")
    period_numeric = [col for col in paired if col not in ["state", "macro_region"]]
    region = paired.groupby("macro_region")[period_numeric].mean().join(paired.groupby("macro_region").size().rename("states")).reset_index()
    save_csv(region, tables / "macro_region_paired_periods.csv")

    # The historical file is a different state/area panel. Never append it to state totals.
    all_hist_months = sorted(historical["month"].unique())
    complete_areas = complete_entities(historical, ["state", "area"], all_hist_months)
    both_areas = complete_areas.groupby("state")["area"].nunique()
    hist_balanced_states = both_areas[both_areas.eq(2)].index
    hist_balanced = historical.loc[historical["state"].isin(hist_balanced_states)]
    area_monthly = hist_balanced.groupby(["month", "area"]).agg(
        unemployment_rate_pct=(RATE, "mean"), labour_participation_rate_pct=(LPR, "mean"),
        states=("state", "nunique")).reset_index()
    save_csv(area_monthly, tables / "historical_balanced_area_monthly.csv")
    # A second matched panel maximizes January–June coverage without changing membership by period or area.
    area_windows = {"pre_covid": PERIODS["pre_covid"], "first_wave": PERIODS["first_wave"], "june": ["2020-06"]}
    area_entity_periods = period_table(historical, ["state", "area"], area_windows)
    area_both = area_entity_periods.groupby("state")["area"].nunique()
    area_entity_periods = area_entity_periods.loc[area_entity_periods["state"].isin(area_both[area_both.eq(2)].index)]
    save_csv(area_entity_periods, tables / "historical_paired_state_area_periods.csv")
    area_num = [col for col in area_entity_periods if col not in ["state", "area"]]
    area_periods = area_entity_periods.groupby("area")[area_num].mean().join(area_entity_periods.groupby("area").size().rename("states")).reset_index()
    save_csv(area_periods, tables / "historical_matched_area_periods.csv")
    gaps = area_entity_periods.pivot(index="state", columns="area", values=["pre_covid_rate_pct", "first_wave_rate_pct", "june_rate_pct"])
    gap_table = pd.DataFrame({"state": gaps.index, **{
        f"{period}_urban_minus_rural_pp": (gaps[f"{period}_rate_pct"]["Urban"] - gaps[f"{period}_rate_pct"]["Rural"]).to_numpy()
        for period in area_windows}})
    save_csv(gap_table, tables / "historical_matched_urban_rural_gaps.csv")

    panel_stats = {col: float(paired[col].mean()) for col in period_numeric}
    peak = monthly.loc[monthly[f"balanced_{RATE}"].idxmax()]
    top_shock = paired.nlargest(5, "first_wave_change_pp")
    exclusions = sorted(set(state["state"]) - set(paired["state"]))
    region_records = region.to_dict(orient="records")
    area_records = area_periods.to_dict(orient="records")
    mean_gaps = {col: float(gap_table[col].mean()) for col in gap_table if col != "state"}
    # Summarize 2019 month observations without treating them as repeated seasonal measurements.
    historical_2019 = area_monthly.loc[area_monthly["month"].str.startswith("2019")]
    pattern_2019 = {}
    for area in ["Rural", "Urban"]:
        values = historical_2019.loc[historical_2019["area"].eq(area)]
        high, low = values.loc[values[RATE].idxmax()], values.loc[values[RATE].idxmin()]
        pattern_2019[area] = {"highest_month": high["month"], "highest_rate_pct": float(high[RATE]),
                              "lowest_month": low["month"], "lowest_rate_pct": float(low[RATE])}
    metrics = {
        "task": "CodeAlpha Task 2: Unemployment Analysis with Python",
        "analysis_type": "descriptive; no causal effect, predictive model, or seasonal decomposition claimed",
        "aggregation": "unweighted means across states/territories or matched state-area observations; not official nationwide population-weighted rates",
        "data_quality": {"historical_state_area": hist_info, "2020_state": state_info},
        "state_paired_panel": {
            "n_states": len(paired), "included_states": sorted(paired["state"].tolist()),
            "excluded_incomplete_states": exclusions, "periods": PERIODS,
            "means": panel_stats,
            "states_above_pre_covid_in_later_recovery": int(paired["later_recovery_change_from_pre_pp"].gt(0).sum()),
            "peak_balanced_month": peak["month"], "peak_balanced_rate_pct": float(peak[f"balanced_{RATE}"]),
            "largest_first_wave_increases": top_shock[["state", "first_wave_change_pp"]].to_dict(orient="records"),
        },
        "macro_region_paired_means": region_records,
        "historical_balanced_full_period": {"n_matched_states": len(hist_balanced_states), "months": all_hist_months},
        "historical_january_june_matched_comparison": {
            "n_states_per_area": int(area_periods["states"].iloc[0]), "periods": area_windows,
            "area_means": area_records, "mean_urban_minus_rural_gaps_pp": mean_gaps,
        },
        "observed_2019_within_year_pattern": pattern_2019,
        "validation": {"required_schema": "passed", "date_parsing_and_month_ends": "passed",
                       "unique_observation_keys": "passed", "numeric_ranges_and_finiteness": "passed",
                       "complete_matched_comparison_panels": "passed", "datasets_not_concatenated": True},
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    make_charts(state, historical, paired, monthly, region, area_monthly, area_periods, charts)

    pre, wave, recovery = [panel_stats[f"{p}_rate_pct"] for p in PERIODS]
    summaries = [
        "# Unemployment analysis — design report", "",
        "## Objective", "",
        "Clean the supplied unemployment datasets, explore time and regional patterns, describe Covid-period changes, and identify cautious policy implications.", "",
        "## Data and scope", "",
        f"- `Unemployment in India.csv`: {hist_info['raw_rows']} raw rows; {hist_info['fully_blank_rows_removed']} fully blank rows removed; {len(historical)} valid observations covering {hist_info['states_or_territories']} states/territories and {hist_info['observed_state_area_pairs']} observed state-area pairs, May 2019–June 2020.",
        f"- `Unemployment_Rate_upto_11_2020.csv`: {len(state)} observations across {state_info['states_or_territories']} states/territories, January–October 2020. The filename does **not** establish November coverage.",
        f"- Missing cells within each observed entity's full date span: {hist_info['missing_entity_month_cells']} historical state-area-months and {state_info['missing_entity_month_cells']} 2020 state-months. Chandigarh has only Urban records in the historical file; no Rural observations are invented.",
        "- Files are analyzed separately: the historical data are Rural/Urban state-area observations; the 2020 file supplies state observations with macro-region labels. Combining them would double count overlapping months and mix granularities.",
        "- Actual inputs are the two user-uploaded CSV files. The task PDF links to [Unemployment in India on Kaggle](https://www.kaggle.com/datasets/gokulrajkmv/unemployment-in-india). That task-document attribution does not independently verify the uploaded files' publisher, extraction date, survey methodology, or redistribution license; none is invented.", "",
        "## Method and validation", "",
        "Headers and string values are stripped; fully blank rows are removed; dates and numbers are parsed strictly. The second `Region` column, read as `Region.1`, becomes `macro_region`, while `Region` becomes `state`. Monthly frequency labels are standardized. No rates are imputed, and duplicate observation keys raise an error rather than being averaged.", "",
        "All reported aggregates are **unweighted means across states/territories or matched state-area observations**, not official national population-weighted unemployment rates. Rate changes use percentage points (pp), not percentage growth. Unemployment uses the labour force as its denominator; falling participation can accompany a falling unemployment rate.", "",
        f"State comparisons average Jan–Mar 2020 as the pre-Covid reference, Apr–May as the initial disruption window, and Aug–Oct as later recovery. The same {len(paired)} complete states/territories appear in every window and monthly balanced trend. Incomplete states excluded: {', '.join(exclusions)}. Means are calculated within each state first and then across states; equal state weights are maintained.", "",
        f"For the historical plot, both areas and all 14 months are required, leaving {len(hist_balanced_states)} common states per area. A separate Jan–June panel keeps {int(area_periods['states'].iloc[0])} states with both areas observed in all six months, allowing matched rural–urban period comparisons. The different panel sizes are intentional and documented.", "",
        "Both files pass required-field, finite-numeric, [0,100] percentage, nonnegative integral employment-count, monthly-date, unique-key, and panel-completeness checks. Source coordinate labels appear reversed: the column named `latitude` exceeds 90 degrees. They remain under explicit `source_*_label` names and are not used for maps.", "",
        "## Results", "",
        f"For the same {len(paired)} states, mean unemployment rises from **{pre:.2f}%** in Jan–Mar to **{wave:.2f}%** in Apr–May (**+{wave-pre:.2f} pp**), then falls to **{recovery:.2f}%** in Aug–Oct (**{recovery-pre:+.2f} pp** relative to the reference). The monthly peak is **{peak['month']} ({peak[f'balanced_{RATE}']:.2f}%)**. {metrics['state_paired_panel']['states_above_pre_covid_in_later_recovery']} of {len(paired)} states remain above their own pre-Covid period average in Aug–Oct.", "",
        f"Unweighted labour participation for these same states changes from **{panel_stats['pre_covid_lpr_pct']:.2f}%** to **{panel_stats['first_wave_lpr_pct']:.2f}%** and later **{panel_stats['later_recovery_lpr_pct']:.2f}%**. This joint movement cautions against treating a lower unemployment rate alone as complete labour-market recovery.", "",
        "Largest descriptive first-wave increases:", "",
        markdown_table(top_shock[["state", "pre_covid_rate_pct", "first_wave_rate_pct", "first_wave_change_pp"]]), "",
        "Macro-region results on the same complete panel:", "",
        markdown_table(region[["macro_region", "states", "pre_covid_rate_pct", "first_wave_rate_pct", "later_recovery_rate_pct"]]), "",
        "Matched rural/urban results (a distinct dataset and January–June comparison):", "",
        markdown_table(area_periods[["area", "states", "pre_covid_rate_pct", "first_wave_rate_pct", "june_rate_pct", "first_wave_change_pp"]]), "",
        f"The mean Urban-minus-Rural unemployment gap is **{mean_gaps['pre_covid_urban_minus_rural_pp']:.2f} pp** before Covid, **{mean_gaps['first_wave_urban_minus_rural_pp']:.2f} pp** in Apr–May, and **{mean_gaps['june_urban_minus_rural_pp']:.2f} pp** in June. These are same-state, equal-weight comparisons; they do not represent every rural or urban resident.", "",
        "## Within-year patterns and limits on seasonality", "",
    ]
    for area, info in pattern_2019.items():
        summaries.append(f"- In the balanced historical {area.lower()} panel's May–December 2019 observations, the highest monthly mean is {info['highest_month']} ({info['highest_rate_pct']:.2f}%) and the lowest is {info['lowest_month']} ({info['lowest_rate_pct']:.2f}%).")
    summaries.extend([
        "", "These are observed within-year fluctuations, not evidence of a repeatable seasonal cycle. The historical series spans only 14 months, has missing entities, and includes an exceptional disruption. Several comparable years and sector, agricultural-calendar, and survey-design information would be needed to distinguish seasonality from trend and sampling variation.", "",
        "## Policy implications", "",
        "1. The broad Apr–May rate increase, alongside reduced participation, supports prioritizing rapid income support and access to employment services during abrupt disruptions. The analysis establishes timing and association; it cannot estimate the effect of a particular restriction or program.",
        "2. State and macro-region variation argues for local monitoring and allocation based on both the size of the affected labour force and the severity/persistence of change. A high unweighted rate or a small region's mean should not by itself determine a national funding allocation.",
        "3. Matched rural–urban differences motivate checking access to suitable work and income protection in both areas, including mobile and migrant workers. The data do not identify occupations or migration, so sector-specific explanations require additional evidence.",
        "4. Track participation and employment levels alongside unemployment. A return of the unemployment percentage toward baseline can coexist with workers leaving the labour force; June observations alone do not establish durable rural/urban recovery.",
        "5. Extend the series and obtain documented survey weights, sample sizes and uncertainty before drawing national estimates, causal claims, recurring-seasonality conclusions, or evaluating policy effectiveness.", "",
        "## Limitations", "",
        "No control group, policy exposure measure, sample sizes, survey weights, standard errors, or identification strategy is available. Jan–Mar is a descriptive reference rather than a proven untreated counterfactual, and March may already contain pandemic-related disruption. Missing states are excluded from paired panels, so panel results do not cover every state. No confidence intervals are fabricated. The two source datasets can differ in methodology and are never used interchangeably.", "",
        "## Reproducibility", "",
        "Run `python analysis.py` from any working directory. Source paths and output defaults are resolved relative to this script. Optional `--data-dir` and `--output-dir` arguments allow reruns without modifying the originals. `metrics.json` records source SHA-256 hashes and validation outcomes; CSVs retain full analysis values to six decimals. No network access is needed for analysis.", "",
        "## Figures", "",
        "![State trends](charts/state_monthly_trends.png)", "",
        "![State period changes](charts/paired_state_changes.png)", "",
        "![Macro-region comparison](charts/macro_region_comparison.png)", "",
        "![Rural and urban historical trends](charts/rural_urban_trends.png)", "",
        "![Matched area comparison](charts/rural_urban_period_comparison.png)", "",
        "![State monthly heatmap](charts/state_month_heatmap.png)", "",
    ])
    (output_dir / "summary.md").write_text("\n".join(summaries))
    return metrics


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data", help="Directory containing the two supplied CSV files")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs", help="Directory to write charts, tables, cleaned data, and report")
    args = parser.parse_args(argv)
    metrics = run(args.data_dir.resolve(), args.output_dir.resolve())
    panel = metrics["state_paired_panel"]
    print(f"Analysis complete: {panel['n_states']} complete state comparisons; report: {args.output_dir.resolve() / 'summary.md'}")
    print(f"Jan–Mar mean {panel['means']['pre_covid_rate_pct']:.2f}%; Apr–May {panel['means']['first_wave_rate_pct']:.2f}%; Aug–Oct {panel['means']['later_recovery_rate_pct']:.2f}% (unweighted state means).")
    return metrics


if __name__ == "__main__":
    main()
