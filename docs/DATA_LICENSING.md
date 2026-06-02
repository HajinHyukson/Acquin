# Data Licensing Review (Phase 5)

Status: **OPEN — must be resolved before commercial deployment or
redistribution** (context doc §4.2, §22 Q1–Q2).

## Sources in the codebase

| Provider | Module | Use | Licensing status |
|---|---|---|---|
| `sample` | `data/providers/sample.py` | Synthetic, deterministic | No license needed; **never present as real data**. |
| `pykrx` | `data/providers/pykrx_provider.py` | Real KOSPI data (prototype) | Scrapes/derives from public KRX/Naver sources. Acceptable for prototyping/personal use; **redistribution and commercial use are not cleared**. |
| `licensed` | `data/providers/licensed.py` | Production stub | To be implemented against a licensed vendor (KRX/Koscom/broker). |

## Questions to resolve before launch

For the chosen production source, confirm in writing whether the license permits:

- [ ] Storage of raw and derived data
- [ ] Redistribution / user-facing charts
- [ ] Derived analytics (correlations, event studies)
- [ ] ML model training on the data
- [ ] Paid subscription / commercial products
- [ ] Retention of historical and delisted-stock data

## Recommendation

1. Decide deployment intent (personal vs commercial) — context doc §22 Q2.
2. If commercial: procure a licensed feed (KRX/Koscom or a vendor) and implement
   `LicensedProvider`; do **not** ship `pykrx`-sourced data to end users.
3. Record the executed license terms and any usage constraints here, and gate
   redistribution features accordingly.

## Product-labelling constraint (always applies)

개인/기관 cumulative net buy is a **net-buy position proxy**, not holdings. Only
외국인 보유량/보유비율 are real holdings, and only from verified foreign-ownership
data. This is enforced in API metadata and the frontend; keep it regardless of
source.
