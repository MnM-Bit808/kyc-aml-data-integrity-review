# Written by Claude Code — infrastructure, not analysis
"""
Acceptance checks for the sealed generator (generator/GENERATOR_SPEC.md, final section).

    python generator/acceptance_checks.py            # checks 1-10 plus the extra X checks
    python generator/acceptance_checks.py --no-repro # skip check 10 (it regenerates everything)

The answer key is loaded INSIDE Python, as the spec requires, and nothing read from it is ever
printed: every check prints PASS or FAIL and a fixed description, never a value. An exception
inside a check is reported as FAIL with the exception type only, because an exception message
could quote a value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate as G  # noqa: E402

LEAK_RE = re.compile(r"planted|hidden|true_|answer|seed|typology_actual", re.IGNORECASE)


def _raw(root: Path, name: str) -> pd.DataFrame:
    """Every cell as a string; a null cell reads as '' and whitespace is preserved."""
    return pd.read_csv(root / "data" / "raw" / name, dtype=str, keep_default_na=False)


def _proc(root: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(root / "data" / "processed" / name, dtype=str, keep_default_na=False)


def _key(root: Path) -> dict:
    with open(root / G.KEY_RELPATH, encoding="utf-8") as fh:
        return json.load(fh)


def _sha(path: Path) -> str:
    return G.sha256_file(path)


# ------------------------------------------------------------------------------------------
# The ten acceptance checks from the spec
# ------------------------------------------------------------------------------------------
def check_1(root):
    c = _raw(root, "customers.csv")
    return len(c) == G.N_CUSTOMERS and not c.duplicated(["bank_id", "account_id"]).any()


def check_2(root):
    c = _raw(root, "customers.csv")
    for m, n in G.MARKET_CUSTOMERS.items():
        sub = c[c["market"] == m]
        if len(sub) != n:
            return False
        target = n * G.MARKET_BUSINESS_SHARE[m]
        nb = int((sub["customer_type"] == "Business").sum())
        if abs(nb - target) > 0.02 * target:
            return False
    return True


def check_3(root):
    def rows(name):
        with open(root / "data" / "raw" / name, "rb") as fh:
            return sum(1 for _ in fh) - 1
    return rows("card_activity.csv") < 2_000_000 and rows("card_statements.csv") == G.N_CUSTOMERS * 12


def check_4(root):
    lab = _proc(root, "customer_labels.csv")
    none = lab["suspicious_role"] == "none"
    ok_roles = lab["suspicious_role"].isin(["sender", "receiver", "both", "none"]).all()
    return bool(ok_roles and (lab.loc[none, "transfer_suspicious"] == "0").all()
                and (lab.loc[~none, "transfer_suspicious"] == "1").all())


def check_5(root):
    for path in sorted((root / "data" / "raw").glob("*.csv")):
        with open(path, encoding="utf-8") as fh:
            header = fh.readline()
        if any(LEAK_RE.search(col) for col in header.strip().split(",")):
            return False
    for name in G.PROCESSED_OUTPUTS:
        path = root / "data" / "processed" / name
        cols = (pd.read_parquet(path).columns if name.endswith(".parquet")
                else pd.read_csv(path, nrows=0).columns)
        if any(LEAK_RE.search(col) for col in cols):
            return False
    return True


def expected_parameter_keys(ranges: dict) -> list:
    """Walks generator_ranges.yaml independently of generate.draw_parameters()."""
    keys = []
    dims = ranges["H1"]["dimensions"]
    per_dim = ranges["H1"].get("drawn_independently_per_dimension", False)

    def walk(node, path):
        if isinstance(node, dict):
            if "dist" in node:
                if path[0] == "H1" and per_dim:
                    keys.extend(".".join(path + [d]) for d in dims)
                else:
                    keys.append(".".join(path))
                return
            for k, v in node.items():
                walk(v, path + [str(k)])
        elif isinstance(node, str) and node.startswith("drawn_at_random"):
            keys.append(".".join(path))
        elif path[-1].endswith("_probability"):
            keys.append(".".join(path))

    for top, block in ranges.items():
        if top in ("seeds", "approved_on", "approved_by", "locked"):
            continue
        walk(block, [top])
    return keys


PROBABILITY_OUTCOME = {"H2.null_probability": "H2.is_null", "H3.present_probability": "H3.present"}


def check_6(root):
    key = _key(root)
    ranges, _ = G.load_config()
    if str(key["seeds"]["sampling_seed"]) != str(ranges["seeds"]["sampling_seed"]):
        return False
    seed = key["seeds"]["hidden_parameter_seed"]
    if not (isinstance(seed, str) and seed.isdigit() and int(seed) > 0):
        return False
    drawn = key["drawn_parameters"]
    for k in expected_parameter_keys(ranges):
        k = PROBABILITY_OUTCOME.get(k, k)
        if k not in drawn or drawn[k] is None:
            return False
    for d in ranges["H1"]["dimensions"]:
        if drawn.get(f"H1.worst_market.{d}") not in G.MARKETS:
            return False
    return len(drawn["H5.cluster_size"]) == drawn["H5.duplicate_clusters"]


def _decoy_field_clean(root, field) -> bool:
    c = _raw(root, "customers.csv")
    ind = c["customer_type"] == "Individual"
    as_of = pd.Timestamp(str(G.load_config()[1]["as_of_date"]))
    if field == "date_of_birth":
        v = c.loc[ind, field]
        if (v.str.strip() == "").any():
            return False
        d = pd.to_datetime(v, format="%Y-%m-%d", errors="coerce")
        if d.isna().any():
            return False
        age = (as_of - d).dt.days / 365.25
        return bool(((age >= 18) & (age <= 120)).all())
    if field == "postcode":
        for m, pat in G.POSTCODE_RE.items():
            v = c.loc[c["market"] == m, field]
            if not v.str.match(pat).all():
                return False
        return True
    if field == "pep_flag":
        return bool(c[field].isin(G.VALID_PEP).all())
    if field == "id_doc_type":
        return bool(c.loc[ind, field].isin(G.VALID_ID_DOC_TYPES).all())
    return False


def check_7(root):
    key = _key(root)
    field = key["drawn_parameters"]["decoy.clean_dimension"]
    if field not in G.DECOY_CANDIDATES:
        return False
    cols = key["planted_cells"]["columns"]
    fi = cols.index("field")
    if any(row[fi] == field for row in key["planted_cells"]["rows"]):
        return False
    return _decoy_field_clean(root, field)


def check_8(root):
    bo = _raw(root, "beneficial_owners.csv")
    pct = pd.to_numeric(bo["ownership_pct"])
    return bool(((pct == 25.0) & (bo["id_verified_flag"] == "False")).any())


def check_9(root):
    key = _key(root)
    cols = key["planted_cells"]["columns"]
    ki, pi = cols.index("kind"), cols.index("planted")
    planted = [r[pi] for r in key["planted_cells"]["rows"] if r[ki] == "missing_value"]
    n_ws = sum(1 for v in planted if isinstance(v, str) and v.strip() == "" and v != "")
    n_null = sum(1 for v in planted if v is None)
    if not (n_ws > 0 and n_null > 0):
        return False
    # In the file itself: some whitespace-only cells, and .isna() does not see them.
    c = pd.read_csv(root / "data" / "raw" / "customers.csv", dtype=str)
    ws_cells = 0
    for col in c.columns:
        s = c[col]
        ws_cells += int((s.notna() & (s.str.strip() == "")).sum())
    return ws_cells > 0


def _ranges_hashes_allowed() -> set:
    """The ranges file may legitimately differ from generation time in one way only: the
    `locked` flag flipped from false to true after the run (GENERATOR_SPEC.md step 5)."""
    raw = G.RANGES_PATH.read_bytes()
    unlocked = re.sub(rb"(?m)^locked: true\b", b"locked: false", raw, count=1)
    return {hashlib.sha256(raw).hexdigest(), hashlib.sha256(unlocked).hexdigest()}


def check_10(root):
    seed = G.load_key_seed(root)
    stored = _key(root)
    tmp = Path(tempfile.mkdtemp(prefix="kyc_repro_"))
    try:
        res = G.generate(seed, tmp, write_key=False, verbose=False)
        for rel, meta in res["files"].items():
            if meta["sha256"] != _sha(root / rel):
                return False
        if res["key_sha256"] == _sha(root / G.KEY_RELPATH):
            return True
        # Otherwise the ONLY permitted difference is the recorded ranges-file hash, and only
        # when the ranges file differs from generation time by the lock flag alone.
        regenerated = json.loads(res["key_bytes"])
        if stored["provenance"]["generator_ranges_sha256"] not in _ranges_hashes_allowed():
            return False
        for k in (regenerated, stored):
            k["provenance"].pop("generator_ranges_sha256")
        return regenerated == stored
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------------------------
# Extra checks: things that would make the data wrong even with 1-10 passing
# ------------------------------------------------------------------------------------------
def check_x1_labels_rederived(root):
    """transfer_suspicious / suspicious_role re-derived from the raw IBM file, independently."""
    t = pd.read_csv(G.IBM_TRANS_PATH, dtype=str, keep_default_na=False)
    lab = t["Is Laundering"] == "1"
    snd = set(zip(t.loc[lab, "From Bank"], t.loc[lab, "Account"]))
    rcv = set(zip(t.loc[lab, "To Bank"], t.loc[lab, "Account.1"]))
    cl = _proc(root, "customer_labels.csv")
    for b, a, ts, role in zip(cl["bank_id"], cl["account_id"], cl["transfer_suspicious"], cl["suspicious_role"]):
        s, r = (b, a) in snd, (b, a) in rcv
        exp = "both" if s and r else "sender" if s else "receiver" if r else "none"
        if role != exp or ts != ("0" if exp == "none" else "1"):
            return False
    return True


def check_x2_sample_from_public_seed(root):
    """The Day 2 recipe in generate.py's docstring reproduces the portfolio's accounts."""
    ranges, _ = G.load_config()
    t = pd.read_csv(G.IBM_TRANS_PATH, dtype=str, keep_default_na=False)
    u = pd.concat([t[["From Bank", "Account"]].set_axis(["b", "a"], axis=1),
                   t[["To Bank", "Account.1"]].set_axis(["b", "a"], axis=1)]).drop_duplicates()
    u = u.sort_values(["b", "a"]).reset_index(drop=True)
    lab = t["Is Laundering"] == "1"
    inv = set(zip(t.loc[lab, "From Bank"], t.loc[lab, "Account"])) | \
        set(zip(t.loc[lab, "To Bank"], t.loc[lab, "Account.1"]))
    is_inv = np.array([(b, a) in inv for b, a in zip(u["b"], u["a"])])
    non = u[~is_inv].reset_index(drop=True)
    k = G.N_CUSTOMERS - int(is_inv.sum())
    idx = np.random.default_rng(int(ranges["seeds"]["sampling_seed"])).choice(len(non), size=k, replace=False)
    expected = set(zip(u.loc[is_inv, "b"], u.loc[is_inv, "a"])) | set(zip(non.loc[idx, "b"], non.loc[idx, "a"]))
    c = _raw(root, "customers.csv")
    return expected == set(zip(c["bank_id"], c["account_id"]))


def check_x3_card_balance_identity(root):
    """Implied purchases (balance change + payments + merchant refunds - cash advances -
    refund requests) are never negative, from the second statement month on."""
    st = _raw(root, "card_statements.csv")
    act = _raw(root, "card_activity.csv")
    st["bal"] = (pd.to_numeric(st["statement_balance"]) * 100).round().astype(np.int64)
    act["amt"] = (pd.to_numeric(act["amount"]) * 100).round().astype(np.int64)
    act["month"] = act["event_date"].str[:7]
    agg = act.pivot_table(index=["customer_id", "month"], columns="event_type", values="amt",
                          aggfunc="sum", fill_value=0)
    st = st.sort_values(["customer_id", "statement_month"])
    st["prev"] = st.groupby("customer_id")["bal"].shift(1)
    st = st.merge(agg, left_on=["customer_id", "statement_month"], right_index=True, how="left").fillna(0)
    for col in ("payment", "merchant_refund", "cash_advance", "refund_request"):
        if col not in st.columns:
            st[col] = 0
    s = st[st["prev"].notna() & (st["statement_month"] != st["statement_month"].min())]
    implied = s["bal"] - s["prev"] + s["payment"] + s["merchant_refund"] - s["cash_advance"] - s["refund_request"]
    months_ok = set(act["month"]) <= set(st["statement_month"])
    return bool((implied >= 0).all() and months_ok)


def check_x4_ids_and_links(root):
    c = _raw(root, "customers.csv")
    bo = _raw(root, "beneficial_owners.csv")
    ch = _raw(root, "customer_changes.csv")
    act = _raw(root, "card_activity.csv")
    st = _raw(root, "card_statements.csv")
    lab = _raw(root, "card_labels.csv")
    ids = set(c["customer_id"])
    return bool(c["customer_id"].is_unique and bo["bo_id"].is_unique and ch["change_id"].is_unique
                and act["event_id"].is_unique and set(ch["customer_id"]) <= ids
                and set(act["customer_id"]) <= ids and set(st["customer_id"]) == ids
                and set(lab["customer_id"]) == ids)


def check_x5_key_matches_data(root):
    """Every planted customer cell in the answer key is what the file actually holds."""
    key = _key(root)
    cols = key["planted_cells"]["columns"]
    ti, ri, fi, pi = (cols.index(x) for x in ("table", "record_id", "field", "planted"))
    c = _raw(root, "customers.csv").set_index("customer_id")
    seen = set()
    for row in key["planted_cells"]["rows"]:
        if row[ti] != "customers":
            continue
        if (row[ri], row[fi]) in seen:
            return False            # a cell planted twice would hide the first defect
        seen.add((row[ri], row[fi]))
        want = "" if row[pi] is None else row[pi]
        if c.at[row[ri], row[fi]] != want:
            return False
    return True


def check_x6_no_accidental_na_tokens(root):
    """pandas' default NA parsing must find exactly the empty cells - no natural text such as
    'NA' or 'None' silently turning into a missing value."""
    for name in G.RAW_OUTPUTS:
        a = pd.read_csv(root / "data" / "raw" / name, dtype=str)
        b = _raw(root, name)
        if int(a.isna().sum().sum()) != int((b == "").sum().sum()):
            return False
    return True


def check_x7_h2_structure(root):
    """The planted gap/suspicion odds ratio is recovered from the key within sampling error
    (|z| < 4 on the log odds ratio, pooled across markets with market strata)."""
    key = _key(root)
    gap = set(key["hypotheses"]["H2_gap_customers"])
    lab = _proc(root, "customer_labels.csv")
    c = _raw(root, "customers.csv")[["customer_id", "market"]]
    d = lab.merge(c, on="customer_id")
    d["gap"] = d["customer_id"].isin(gap)
    d["s"] = d["transfer_suspicious"] == "1"
    # Mantel-Haenszel pooled odds ratio over markets and its Robins-Breslow-Greenland variance
    num = den = 0.0
    pr = ps = qs = 0.0
    for _, g in d.groupby("market"):
        a = float((g["s"] & g["gap"]).sum()); b = float((g["s"] & ~g["gap"]).sum())
        cc = float((~g["s"] & g["gap"]).sum()); dd = float((~g["s"] & ~g["gap"]).sum())
        n = a + b + cc + dd
        R, S = a * dd / n, b * cc / n
        Pp, Q = (a + dd) / n, (b + cc) / n
        num += R; den += S
        pr += Pp * R; ps += (Pp * S + Q * R); qs += Q * S
    if den == 0 or num == 0:
        return False
    or_mh = num / den
    var = pr / (2 * num ** 2) + ps / (2 * num * den) + qs / (2 * den ** 2)
    z = (np.log(or_mh) - np.log(key["drawn_parameters"]["H2.effective_odds_ratio"])) / np.sqrt(var)
    return bool(abs(z) < 4)


CHECKS = [
    ("1", "customers.csv: exactly 50,000 rows, (bank_id, account_id) unique", check_1),
    ("2", "market split 21,000/18,000/11,000; business counts within 2% of target", check_2),
    ("3", "card_activity under 2,000,000 rows; card_statements exactly 600,000", check_3),
    ("4", "transfer_suspicious and suspicious_role mutually consistent", check_4),
    ("5", "no output column name matches the leak pattern", check_5),
    ("6", "answer key parses and records the seed and every drawn value", check_6),
    ("7", "decoy has zero planted defects in every market", check_7),
    ("8", "an unverified owner at exactly 25.0% exists (the boundary case)", check_8),
    ("9", "some missing values are whitespace, invisible to .isna()", check_9),
    ("X1", "customer labels re-derived independently from the raw IBM file", check_x1_labels_rederived),
    ("X2", "Day 2 sampling recipe (public seed only) reproduces the portfolio", check_x2_sample_from_public_seed),
    ("X3", "card balance identity holds; implied purchases never negative", check_x3_card_balance_identity),
    ("X4", "ids unique; every event/statement/label links to a customer", check_x4_ids_and_links),
    ("X5", "every planted customer cell in the key matches the file", check_x5_key_matches_data),
    ("X6", "no natural text collides with a pandas NA token", check_x6_no_accidental_na_tokens),
    ("X7", "planted H2 odds ratio recoverable within sampling error", check_x7_h2_structure),
    ("10", "same secret seed reproduces byte-identical output", check_10),
]


def run_all(root: Path = G.REPO, include_repro: bool = True) -> bool:
    print("Acceptance checks (PASS/FAIL only; no values are printed):")
    failures = 0
    for cid, desc, fn in CHECKS:
        if cid == "10" and not include_repro:
            print(f"  CHECK {cid:>2}: SKIP  {desc}")
            continue
        try:
            ok = bool(fn(root))
            note = ""
        except Exception as exc:          # never print the message: it could quote a value
            ok, note = False, f"  [{type(exc).__name__}]"
        failures += (not ok)
        print(f"  CHECK {cid:>2}: {'PASS' if ok else 'FAIL'}  {desc}{note}", flush=True)
    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    return failures == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=G.REPO)
    ap.add_argument("--no-repro", action="store_true")
    a = ap.parse_args()
    sys.exit(0 if run_all(a.root, include_repro=not a.no_repro) else 1)
