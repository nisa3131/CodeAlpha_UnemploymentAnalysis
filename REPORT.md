# Unemployment Analysis with Python

**Prepared for:** nisa3131  
**Report date:** 19 October 2026 (Asia/Dhaka)  
**Repository:** `CodeAlpha_UnemploymentAnalysis`

This report uses the standard layout approved by the user: objectives, data, method, results, limitations, and reproducibility. All reported findings come from the supplied datasets and executed project analyses.


## 1  Objective

Clean and explore the supplied unemployment data, describe time and regional patterns around the Covid-19 disruption, assess what the short series can say about seasonality, and identify policy questions supported by the evidence. This is a descriptive analysis.


## 2  Data and provenance

Input: the user-supplied archive (1).zip, containing Unemployment in India.csv and Unemployment_Rate_upto_11_2020.csv. The task document links to https://www.kaggle.com/datasets/gokulrajkmv/unemployment-in-india. That link is cited as the assignment’s dataset reference; these analyses use the uploaded files rather than a new download. Original collection details and redistribution licensing were not independently verified. No dataset license is asserted.

| Dataset | Raw / clean rows | Observed coverage |
| --- | --- | --- |
| Historical state–area | 768 / 740 | May 2019–June 2020; 28 states/territories; Rural and Urban observations |
| 2020 state | 267 / 267 | January–October 2020; 27 states/territories; macro-region labels |

The filename ending in 11_2020 does not establish November coverage: the last observed month is October. The two files remain separate because their overlapping dates and different granularities would otherwise create double counting. No rural counterpart is invented for historical Chandigarh, which has only Urban records.


## 3  Cleaning and comparison design

Strip headers and text, parse monthly dates and numeric values strictly, standardize frequency labels, and rename the repeated Region field to macro_region in the 2020 file. Remove only 28 fully blank historical rows. Do not impute rates. Required fields, finite values, percentage bounds, integral employment counts, unique observation keys, and complete comparison panels are checked.

The historical entity-month grid has 30 missing cells and the 2020 state grid has 3. These are documented rather than filled. Source coordinate labels appear reversed because the latitude-labeled values exceed 90 degrees; they are preserved with explicit source labels and are not used for geographic maps.

The main comparison uses the same 25 complete states/territories across January–March (reference), April–May (initial disruption), and August–October (later period). Jammu & Kashmir and Sikkim are excluded for incomplete coverage. First average months within each state, then average states with equal weight. The balanced monthly trend uses the same states. Historical rural–urban comparisons require 20 common states with both areas observed in every relevant month; the full 14-month trend and January–June period panel are explicitly checked.

> All aggregate rates in this report are unweighted state or matched state–area means. They are not official population-weighted national rates. Rate differences are percentage points (pp). The reference period is descriptive; March may already contain pandemic disruption.


## 4  Results and policy interpretation

| Balanced 25-state measure | Jan–Mar | Apr–May | Aug–Oct |
| --- | --- | --- | --- |
| Unemployment rate (%) | 9.20 | 23.20 | 8.90 |
| Labour participation (%) | 44.13 | 37.33 | 42.07 |

*Equal state weights and the same states in each period.*

Mean unemployment rises by **14.00 pp** in April–May and is 0.30 pp below the reference in August–October. The balanced monthly peak is May 2020 at 23.37%. 9 of 25 states remain above their own reference rate in the later period. Participation also falls and does not return to its reference mean, so a lower unemployment percentage alone does not establish full labour-market recovery.

![Figure 1. Balanced 2020 state means for unemployment and labour participation. These show timing and association, not a causal pandemic effect.](outputs/charts/state_monthly_trends.png)

*Figure 1. Balanced 2020 state means for unemployment and labour participation. These show timing and association, not a causal pandemic effect.*

| Largest observed increases | Apr–May minus Jan–Mar (pp) |
| --- | --- |
| Puducherry | 65.84 |
| Jharkhand | 42.93 |
| Tamil Nadu | 38.14 |
| Bihar | 34.19 |
| Karnataka | 21.60 |

*Descriptive equal-period comparisons within each complete state; no survey uncertainty estimates are supplied.*

| Matched historical area | Jan–Mar % | Apr–May % | June % |
| --- | --- | --- | --- |
| Rural | 9.48 | 23.31 | 12.94 |
| Urban | 12.15 | 27.92 | 13.83 |

*Separate historical dataset; 20 same states per area in all comparison months.*

The matched Urban-minus-Rural gap is 2.67 pp before the disruption, 4.61 pp in April–May, and 0.89 pp in June. These comparisons describe the observed matched states rather than every rural or urban resident.

![Figure 2. Historical rural and urban means over a common, complete state panel. The short series supports observed fluctuations, not a recurring seasonal cycle.](outputs/charts/rural_urban_trends.png)

*Figure 2. Historical rural and urban means over a common, complete state panel. The short series supports observed fluctuations, not a recurring seasonal cycle.*

Within May–December 2019, the balanced rural series is highest in October (9.90%) and lowest in May (7.95%); the urban series is highest in September (12.06%) and lowest in June (10.63%). With only 14 historical and 10 state-series months, these are within-year patterns. Several comparable years are needed to distinguish seasonality from trend, sampling variation, and exceptional disruption.

- Policy direction: monitor unemployment, participation, and employment together. The simultaneous rate rise and participation fall motivate rapid access to income support and employment services during sudden disruptions.
- Use local monitoring and verified affected-labour-force sizes to plan support. Differences across states and rural–urban panels motivate further investigation; an equal-state mean alone is insufficient for allocating national funds.
- Check access to work and income protection in both rural and urban areas. Occupation and migration explanations require additional data because those fields are absent.
- Obtain longer series, survey weights, sample sizes, and policy-exposure information before evaluating a particular program’s effectiveness.


## 5  Limitations and next steps

There is no control group, identified counterfactual, policy-exposure measure, survey weight, sample size, or standard error. Causality and uncertainty intervals cannot be inferred from these files. Complete-panel exclusions limit coverage; survey methodology may differ across the two files. No predictive model, seasonal decomposition, official national estimate, or causal pandemic effect is claimed.


## 6  Reproducibility

Validation recorded on 19 October 2026: the delivered notebook executed 4 code cells with 0 recorded errors. The analysis pipeline and its built-in data/evaluation checks completed successfully.

Install the pinned requirements and rerun from the repository root. The notebook calls the same analysis pipeline.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python analysis.py
```

outputs/metrics.json records both source SHA-256 hashes, cleaning counts, complete panels, period means, and validation outcomes. Cleaned CSVs, missing-observation tables, entity/month coverage, matched comparisons, and six figures preserve the audit trail. No network is needed for analysis. --data-dir and --output-dir support alternate local paths.
