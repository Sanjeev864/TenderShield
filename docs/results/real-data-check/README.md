# Real-data check: 2026-11-12

This was run on branch `feature/sdg93-upgrade` against downloaded public datasets and three real
World Bank-financed Indian tenders. Every number below comes from the run. The raw downloads are listed in
`data/real/raw/MANIFEST.json`. The scripts are `run_real.py` (notice PDF in, plan and dossier out) and
`run_boq.py` (the same tender with its line items given as a BOQ).

## Verdict

**The system works end to end on real data, but on real tender notices it produces wrong
restructuring advice.** Several parts work as designed: the data download, model training, the
market store, upload, the API, the dossier and the database. The weak point is the first step,
turning real tender text into work items. It picks up boilerplate sentences and misses the actual
line items, so every later step reasons over the wrong components.

## 1. Data collected

| Dataset | Records | Notes |
|---|---|---|
| CPV 2008 vocabulary | 9,454 codes | Training data for the capability classifier |
| Prozorro (Ukraine) lots / bids / contracts | 92,802 lots, 238,228 bids, 95,272 contracts | Competition model; co-bidding |
| World Bank Major Contract Awards, India | 12,436 rows read, 7,434 awards stored | **Signing dates 1992-11-28 to 2020-01-01 only.** The primary World Bank URL returned 404; the mirror file stops in January 2020 |
| World Bank procurement notices, India | 500 notices (134 Invitations for Bids) | Source of the real tenders tested |
| Market store built | 102,706 awards, 238,228 bids, 43,416 supplier profiles | Indian suppliers come from World Bank awards only |

Retraining from scratch reproduced the committed model cards exactly:

- Capability classifier: CV macro-F1 0.7518.
- Competition model: Poisson deviance 0.6907 against a 0.7008 baseline, on 14,170 held-out lots.

**Bugs found and fixed in `backend/scripts/fetch_real_data.py`:**
- **SSL errors:** every download failed with `CERTIFICATE_VERIFY_FAILED` on macOS python.org builds. The script now uses the certifi CA bundle.
- **Wrong India filter:** the notices query used `countryshortname_exact`, which the API ignores, so only 11 of 500 notices were Indian. It now uses `project_ctry_name_exact` (500 of 500 Indian).

## 2-8. Three real tenders end to end

| Tender (World Bank notice) | What it really is | What TenderShield extracted | Result |
|---|---|---|---|
| OP00474853, SMART Maharashtra | Supply, installation, testing and commissioning (SITC) of a millet processing plant: 9 line items (processing, milling, extrusion, cookie and flaking lines, packing and weighing machines) | 2 "components" from boilerplate: a World Bank financing sentence as *Software/ICT* (conf 0.45), "Project Implementation Unit – Agriculture" as *Medical & lab* (0.36). None of the 9 line items | "Consider 2 packages" (**wrong basis**) |
| OP00471901, Gurugram Metro Pkg-2 | Viaduct and elevated stations, 13.3 km | "Construction Period: 30 months" as *Civil* (0.92), a bidder-contact sentence as *Software/ICT* (0.51) | "Consider 2 packages" (**wrong basis**) |
| OP00464558, PTCUL Uttarakhand | EPC restoration of a 132 kV GIS substation and line; bid security Rs 75 lakh, 18 months | Nothing | HTTP 422 "No scope items could be identified" (honest failure) |

With the millet line items given as a BOQ (`run_boq.py`), the classifier labelled the 9 real items as:
- *Mechanical/HVAC/plumbing*: 4 items.
- *Vehicles & heavy equipment*: 2 items.
- *Medical & lab*: 1 item.
- *Other*: 2 items.

The recommendation became "keep as one integrated contract". The top suppliers were ABB, L&T and Swaraj Mazda, which are not credible for millet machinery. All dependencies came out "weak – shared site only". Weight sensitivity: the recommendation stays best in 67% of 300 perturbations.

## Why it fails

1. **Item extraction (`components.items_from_documents`).** The tables in real notices become long flattened lines that fall outside the 30–900 character scope filter or the work-verb regex. Generic sentences with words like "Government" or "construction" get through. The document pages are still mixed into the components even when a BOQ is supplied (`boq_items + doc_items`).
2. **Taxonomy gap.** There is no category for food processing or industrial process machinery, so agro-processing items get forced into mechanical, vehicles or medical.
3. **Classifier transfer.** It is trained only on CPV code descriptions, which are short and EU-styled. Its confidence on real Indian BOQ lines was 0.29–0.96, with clear mislabels. There is no Indian gold set yet, so real accuracy is **unmeasured**.
4. **Stale Indian market data.** The World Bank mirror ends in January 2020 and `TS_RECENT_YEARS=7` keeps only awards from 2019 on, so almost all Indian award evidence is ignored. "Meet similar-work scale" was 0 for every package.
5. **No Indian bid data.** Co-bidding detection only has Ukrainian bids, so the Indian supplier relationship screening found 0 relationships to review in every run. That reflects missing data, not an absence of relationships.
6. **Values missing.** None of the three notices yielded an estimated value. The Rs 75 lakh bid security was not used as a hint, so every package value is "unknown".

## Not measurable yet (needs gold labels)

- Requirement extraction: precision, recall and F1.
- Classification accuracy on Indian tender lines.
- Supplier matching precision and ranking quality.
- Package generation compared with an expert split.
- Relationship-detection false-positive rate.

## Suggested next fixes, in order

1. Extract table rows and line items from tender text, and do not mix document items in when a BOQ exists.
2. Add an "industrial / process machinery" capability (and check the other gaps against the 134 Indian IFBs).
3. Label about 300 real Indian tender and BOQ lines into `data/annotations/capability_gold.csv`, then retrain and measure.
4. Get current Indian award data (a fresh World Bank export from a browser, CPPP award notices, or OCDS) and confirm the
   date coverage before trusting the supplier pools.
5. Use full bidding documents (scope and BOQ sections from the state e-procurement portals), not only the notice, for the
   end-to-end demonstration.
