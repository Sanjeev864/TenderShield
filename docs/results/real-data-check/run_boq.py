import csv, io, json, os, sys
from pathlib import Path
SCR = Path(sys.argv[1]); REPO = Path(sys.argv[2])
os.environ.update(TS_DATA_DIR=str(SCR / "real/data"), TS_MODELS_DIR=str(SCR / "real/models"), TS_MARKET_COUNTRIES="India")
sys.path.insert(0, str(REPO / "backend"))
import logging; logging.disable(logging.INFO)
from fastapi.testclient import TestClient
from app.auth import issue_token
from app.db import fetch_one, session
from app.main import create_app
from app.restructuring.classifier import classify
# Line items exactly as listed in World Bank notice OP00474853 (RFB IN-PIU AGRI-574767-GO-RFB)
items = [
 ("Primary Processing Line for Millets (Vibro-Grader cum Aspirator, Destoner, dehuller, gravity separator, bucket elevators) 500-600 kg/hr", 1),
 ("Continuous Milling Line (Chakki mill and Roller mill) 500-600 kg/hr", 1),
 ("Cold Extrusion Line (Cold extruder and dryer) 200 kg/hr", 1),
 ("Cookies Making Line (Planetary mixture, cookie cutting and dropping machine, rotary rack oven) 100 kg/hr", 1),
 ("Flaking Line (grain roaster, roller flaker, separator) 100 kg/hr", 1),
 ("Vacuum Packing Machine", 1), ("Band Sealing Machine with nitrogen flush packing", 1),
 ("Weighing Balance 15 g - 30 kg", 2), ("Platform Weighing Scale 300 kg", 1)]
print("classifier on real line items:")
for (t, _), (cap, conf, dist, hits) in zip(items, classify([t for t, _ in items])):
    print(f"  {cap:<28} {conf:.2f}  {t[:70]}")
with session() as conn:
    u = fetch_one(conn, "SELECT * FROM users WHERE email='runner@tendershield.localhost'")
    tid = fetch_one(conn, "SELECT tender_id FROM tenders WHERE title LIKE '%Millet%'")["tender_id"]
c = TestClient(create_app(), headers={"Authorization": "Bearer " + issue_token(u)[0]})
buf = io.StringIO(); w = csv.writer(buf); w.writerow(["Description", "Qty", "Unit", "Rate", "Amount"])
for t, q in items: w.writerow([t, q, "Nos", "", ""])
r = c.post(f"/api/tenders/{tid}/boq", files={"file": ("boq.csv", buf.getvalue().encode(), "text/csv")}); print("boq", r.status_code, r.json())
r = c.post(f"/api/tenders/{tid}/restructure", json={}); p = r.json(); print("restructure", r.status_code, p.get("recommendation", {}).get("headline", p))
(SCR / "real/results/OP00474853/plan_with_boq.json").write_text(r.text)
for comp in p["components"]:
    print(f"  comp {comp['label']:<40} items={comp['n_items']} basis={comp['value_basis']} conf={comp['mean_confidence']} src={[i.get('source') for i in comp['items']]}")
for e in p["dependency_graph"]["edges"]: print(f"  dep {e['source']}<->{e['target']} {e['strength']} {e['types']} | {e['prior_rationale'][:90]}")
for k, s in p["structures"]["scenarios"].items():
    if s: print(f"  {k}: score={s['score']} n={s['n_packages']} | {s['summary'][:150]}")
for pk in p["recommendation"]["packages"]: print("  pkg", pk["package"], pk["scope"], "capable", pk["suppliers_with_full_capability_evidence"], "sme", pk["sme_candidates"])
sl = p["structures"]["scenarios"]["B_recommended"]["packages"][0]["match"]["shortlist"][:5]
print("  top suppliers P1:"); [print("    ", s["name"], {k: s.get(k) for k in ("n_awards", "max_inr_cr", "msme_status", "suitability") if k in s}) for s in sl]
print("  sensitivity", p["structures"]["sensitivity"]["recommended_stays_best"], "| review", p["relationships"]["requires_review"])
