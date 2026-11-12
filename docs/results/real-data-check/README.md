# Real-data check: 2026-11-12

This was run on branch `feature/sdg93-upgrade` against downloaded public datasets and three real
World Bank-financed Indian tenders. Every number below comes from a run. The raw downloads are listed in
`data/real/raw/MANIFEST.json`.

- `run_real.py`: renders each notice to PDF, uploads it, restructures it and generates the dossier.
- `run_boq.py`: gives the millet tender's line items as a BOQ. It was used for the "before" run.
- `<notice>/plan_before*.json`: output before the extraction fix.
- `<notice>/plan.json`: output after the fix.

## Verdict

**Before the fix:** the system ran end to end but gave wrong advice. It built its components from
boilerplate (a financing sentence, an office name, a contact line) and missed the real line items.

**After the fix:** for all three tenders, the components now match what the notice actually procures,
and the advice ("keep as one contract") is correct for notices that each cover one capability.
Package values are still unknown, so scale checks and package sizing cannot run (see the limits below).

## 1. Data collected

| Dataset | Records | Notes |
|---|---|---|
| CPV 2008 vocabulary | 9,454 codes | Training data for the capability classifier |
| Prozorro (Ukraine) lots / bids / contracts | 92,802 lots, 238,228 bids, 95,272 contracts | Competition model; co-bidding |
| World Bank Major Contract Awards, India | 12,436 rows read, 7,434 awards stored | Signing dates 1992-11-28 to 2020-01-01. The primary World Bank URL returns 404; the mirror stops in January 2020 |
| World Bank procurement notices, India | 500 notices (134 Invitations for Bids) | Source of the tested tenders |
| Market store | 102,706 awards, 238,228 bids, 43,416 supplier profiles | Indian suppliers come from World Bank awards only |

Model results:

| Model | Before | After the fix (14 capabilities) |
|---|---|---|
| Capability classifier, 5-fold CV on CPV | macro-F1 0.7518, accuracy 0.79 | macro-F1 0.7397, accuracy 0.7913. The new `industrial_machinery` class scores F1 0.64 |
| Competition model, held-out 14,170 lots | Poisson deviance 0.6907 vs 0.7008 baseline | unchanged |

The macro-F1 drop comes from adding a 14th, harder class. Accuracy did not change.

## 2-5. Three real tenders, before and after

| Tender | What it procures | Before | After |
|---|---|---|---|
| **OP00474853**, SMART Maharashtra: millet processing plant, supply, installation, testing and commissioning | 9 line items: processing, milling, extrusion, cookie and flaking lines; vacuum packing, band sealing, weighing balance, platform scale | 2 components built from boilerplate (a financing sentence as *ICT*, a PIU name as *Medical*). "Consider 2 packages" | **All 9 line items** extracted as `line_item` and classified *Industrial & process machinery* (confidence 0.31–0.98). One component, keep integrated. 34 suppliers have capability evidence |
| **OP00471901**, Gurugram Metro Pkg-2 | Viaduct and elevated stations, 13.3 km | "Construction Period: 30 months" as *Civil*, a bidder-contact line as *ICT*. "Consider 2 packages" | The "Name of work" field extracted and classified *Civil*. One component. 888 suppliers have civil evidence, 677 of them small by the size proxy |
| **OP00464558**, PTCUL Uttarakhand | Restoration of a 132 kV GIS substation and line (EPC) | No items found, HTTP 422 | The quoted "Detail of Work" extracted and classified *Electrical*. 257 suppliers. Top of the shortlist: L&T, ABB, Alstom, Alstom T&D, BHEL, all real substation contractors |

In all three, the boilerplate is gone: financing text, the implementation unit, the construction period, email, mobile and IFSC lines.

## What was changed

1. **Line-item tables.** Notice and PDF tables arrive with one cell per line. Rows are now read after a header such as
   "Description of Goods", "Detail of Work" or "Name of Work", using sequential row numbers.
   - Before, bare numbers were dropped as page noise, and goods items without a work verb were filtered out.
2. **Labelled and quoted work names.** "Name of work:", "Contract title:" and quoted work names in invitations are now read.
3. **Boilerplate filter.** It now also covers financing and loan text, procurement regulations, contact and bank
   details, registration, construction or completion periods, and evaluation weightings.
4. **Tender title as a fallback.** The title is used when the documents give no scope.
5. **Explicit items are kept.** Table rows and labelled fields are kept at low confidence (they are flagged in data
   quality). Only free-text paragraphs need confidence 0.35 or more.
6. **BOQ handling.** When a BOQ is uploaded, it is the item list. Document text no longer adds extra components.
7. **New capability.** `industrial_machinery` covers CPV 422/423/426–428/4291–4294/4297/4299: food processing, ovens,
   machine tools, packing and weighing machinery. Dependency priors were added for it.
   - Civil and electrical lexicon terms were added from the real notices: viaduct, elevated station, sub-station,
     transmission line, GIS.
8. **Tests.** `tests/test_real_notices.py` checks all of this against the three real notices (74 tests pass).

## Remaining limits found on real data

- **No values.** None of the three notices states an estimated value. Package values are therefore unknown, so the
  similar-work scale check reports "package value unknown" and SME sizing cannot run. The Rs 75 lakh bid security is
  not used as a hint. The full bidding documents (BOQ and estimate) from the state portals are needed.
- **Notices are too coarse to split.** Each notice describes one capability, so there is nothing to restructure. A
  meaningful demonstration needs a full bidding document with a multi-trade scope or BOQ.
- **Items in one capability are never split.** For example, the processing lines and the packing/weighing machines
  stay together because both are industrial machinery. An expert might split them.
- **Thin and old evidence for machinery.** The 34 machinery suppliers have only 1–2 awards each, and the latest is
  from 2002–2012. Some are machine-tool or lab-equipment firms, not food-processing firms.
  - The World Bank mirror stops in 2020. Correction to the first report: the 7-year window only lowers a supplier's
    ranking, it does not exclude older awards.
- **Supplier names are not merged.** "ALSTOM LTD.", "M/S ALSTOM LTD., JAIPUR" and "ALSTOM T&D INDIA LIMITED" are
  separate suppliers, and the Jaipur one is wrongly marked "small" by the size proxy.
- **No Indian bid data.** Relationship screening found 0 relationships to review in every run, because there are no
  Indian bids to compare.
- **Real accuracy is unmeasured.** Extraction precision/recall/F1, classification accuracy on Indian lines, matching
  precision and package agreement with experts all need hand-labelled gold sets.
