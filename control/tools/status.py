#!/usr/bin/env python3
"""Aleekhan project control — single source of truth for phase/step/gate/decision status.

Pure standard library. Usage (run from repo root):
  python3 control/tools/status.py init --handoff handoff/            # build PROJECT_STATUS.json from handoff CSVs
  python3 control/tools/status.py brief                              # short Persian summary (used by SessionStart hook)
  python3 control/tools/status.py render                             # write control/STATUS_FA.md + control/STATUS.html
  python3 control/tools/status.py start-phase PHASE_00 --by "<employer name>"
  python3 control/tools/status.py step PHASE_00 00.1 IN_PROGRESS
  python3 control/tools/status.py step PHASE_00 00.1 IN_REVIEW --commit <sha> --report reports/phase-00/step-1/REPORT.md
  python3 control/tools/status.py step PHASE_00 00.1 PASS --review reports/phase-00/step-1/REVIEW.md
  python3 control/tools/status.py gate PHASE_00 ACCEPTED --by "<employer name>" [--note ...]
  python3 control/tools/status.py decide DEC-001 APPROVED --by "<owner>" --note "<decision text>"
  python3 control/tools/status.py test-add PHASE_00 "<what to test>" "<how to test>"
  python3 control/tools/status.py test-done T-001 --result PASS|FAIL --note "..."
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = ROOT / "control" / "PROJECT_STATUS.json"
LOCK_PATH = ROOT / "control" / "SESSION_LOCK.json"
LOCK_TTL_HOURS = 12

for _st in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252/cp720
    try:
        _st.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def machine() -> str:
    import platform
    return os.environ.get("ALEEKHAN_MACHINE") or platform.node() or "unknown"

STEP_NAMES = {
    1: "Discovery & Contract", 2: "Database", 3: "Domain Engine", 4: "Backend/API",
    5: "UI", 6: "Integration", 7: "Security & Ops", 8: "Report & Review",
}
STEP_STATES = ["TODO", "IN_PROGRESS", "IN_REVIEW", "REWORK", "PASS", "BLOCKED"]
STEP_TRANSITIONS = {
    "TODO": {"IN_PROGRESS", "BLOCKED"},
    "IN_PROGRESS": {"IN_REVIEW", "BLOCKED"},
    "IN_REVIEW": {"PASS", "REWORK", "BLOCKED"},
    "REWORK": {"IN_PROGRESS", "BLOCKED"},
    "BLOCKED": {"IN_PROGRESS", "TODO"},
    "PASS": {"REWORK"},  # reopen only through a recorded REV issue
}
PHASE_STATES = ["NOT_STARTED", "ACTIVE", "GATE_PENDING", "ACCEPTED", "BLOCKED"]
CLOSED_DECISION = {"APPROVED", "CLOSED", "REJECTED_ALTERNATIVE_CHOSEN"}

STATE_FA = {
    "NOT_STARTED": "شروع‌نشده", "ACTIVE": "فعال", "GATE_PENDING": "منتظر تأیید Gate",
    "ACCEPTED": "پذیرفته‌شده", "BLOCKED": "مسدود",
    "TODO": "در صف", "IN_PROGRESS": "در حال انجام", "IN_REVIEW": "در ممیزی",
    "REWORK": "اصلاح", "PASS": "قبول",
}

# Planning assumption (calendar weeks incl. review + decision turnaround). NOT an approved schedule.
DEFAULT_EST_WEEKS = {
    "PHASE_00": 2, "PHASE_01": 3, "PHASE_02": 3, "PHASE_03": 4, "PHASE_04": 4,
    "PHASE_05": 4, "PHASE_06": 4, "PHASE_07": 5, "PHASE_08": 3, "PHASE_09": 2,
    "PHASE_10": 3, "PHASE_11": 3, "PHASE_12": 3, "PHASE_13": 4, "PHASE_14": 4,
}

# ---------------------------------------------------------------- Jalali dates
def g2j(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


J_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(s) -> str:
    return str(s).translate(FA_DIGITS)


def jdate(d: dt.date, long: bool = False) -> str:
    y, m, dd = g2j(d.year, d.month, d.day)
    if long:
        return fa(f"{dd} {J_MONTHS[m-1]} {y}")
    return fa(f"{y}/{m:02d}/{dd:02d}")


def jmonth(d: dt.date) -> str:
    y, m, _ = g2j(d.year, d.month, d.day)
    return fa(f"{J_MONTHS[m-1]} {y}")


def today() -> dt.date:
    env = os.environ.get("ALEEKHAN_TODAY")
    return dt.date.fromisoformat(env) if env else dt.date.today()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

# ---------------------------------------------------------------- persistence
def load() -> dict:
    if not STATUS_PATH.exists():
        sys.exit(f"missing {STATUS_PATH}; run `init` first")
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def save(s: dict) -> None:
    s["updated_at"] = now_iso()
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATUS_PATH)


def event(s: dict, kind: str, **kw) -> None:
    s.setdefault("events", []).append({"at": now_iso(), "kind": kind, **kw})


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

# ---------------------------------------------------------------- init
def cmd_init(a) -> None:
    h = Path(a.handoff)
    phases = []
    for r in read_csv(h / "03_PHASE_PLAN" / "PHASE_INDEX.csv"):
        pid = r["phase"]
        n = int(pid.split("_")[1])
        phases.append({
            "id": pid, "title_fa": r["title_fa"], "title_en": r["title_en"],
            "pages": [p for p in r["pages"].split(";") if p and p != "0"],
            "deps": [d for d in r["depends_on"].split(";") if d],
            "est_weeks": DEFAULT_EST_WEEKS.get(pid, 3), "state": "NOT_STARTED",
            "started_at": None, "gate_pending_at": None, "accepted_at": None, "accepted_by": None,
            "steps": {f"{n:02d}.{i}": {"name": STEP_NAMES[i], "state": "TODO", "commit": None,
                                       "report": None, "review": None, "rework_cycles": 0,
                                       "started_at": None, "done_at": None} for i in range(1, 9)},
        })
    decisions = []
    for r in read_csv(h / "11_PROJECT_MANAGEMENT" / "DECISION_REGISTER.csv"):
        decisions.append({"id": r["decision_id"], "priority": r["priority"], "gate": r["decision_gate"],
                          "domain": r["domain"], "issue": r["issue"], "status": r["status"],
                          "owner": r["owner"], "phase": r["affects_phase"], "source": r["source"],
                          "resolution": None, "decided_by": None, "decided_at": None})
    extra = Path(a.extra_decisions) if a.extra_decisions else ROOT / "control" / "decisions" / "DECISIONS_ADDENDUM.csv"
    if extra.exists():
        for r in read_csv(extra):
            decisions.append({"id": r["decision_id"], "priority": r["priority"], "gate": r["decision_gate"],
                              "domain": r["domain"], "issue": r["issue"], "status": r["status"],
                              "owner": r["owner"], "phase": r["affects_phase"], "source": r["source"],
                              "resolution": None, "decided_by": None, "decided_at": None})
    log = ROOT / "control" / "decisions" / "DECISION_LOG.csv"
    if log.exists():  # decisions already taken by the employer before repo setup
        byid = {d["id"]: d for d in decisions}
        for r in read_csv(log):
            d = byid.get(r["decision_id"])
            if d:
                d.update(status=r["status"], decided_by=r["decided_by"], decided_at=r["decided_at"], resolution=r["resolution"])
    s = {"project": "Aleekhan", "baseline": "ALEEKHAN_MASTER_HANDOFF v1.0 (2026-11-01)",
         "schedule_note": "est_weeks are planning ASSUMPTIONS, not approved dates",
         "created_at": now_iso(), "phases": phases, "decisions": decisions,
         "ready_for_test": [], "events": []}
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    save(s)
    print(f"initialised {len(phases)} phases, {sum(len(p['steps']) for p in phases)} steps, {len(decisions)} decisions")

# ---------------------------------------------------------------- helpers
def phase(s, pid):
    for p in s["phases"]:
        if p["id"] == pid:
            return p
    sys.exit(f"unknown phase {pid}")


def open_p0(s, pid=None):
    return [d for d in s["decisions"] if d["priority"] == "P0" and d["status"] not in CLOSED_DECISION
            and (pid is None or d["phase"] == pid)]


def pass_fraction(p) -> float:
    st = list(p["steps"].values())
    return sum(1 for x in st if x["state"] == "PASS") / len(st)


def velocity(s) -> tuple[float, int]:
    """actual/planned ratio. Prefer whole accepted phases (includes review + employer decision time);
    fall back to finished steps (>=3) with a conservative floor; 1.0 otherwise."""
    pa = pp = 0.0
    for p in s["phases"]:
        if p["state"] == "ACCEPTED" and p["started_at"] and p["accepted_at"]:
            d = (dt.datetime.fromisoformat(p["accepted_at"]) - dt.datetime.fromisoformat(p["started_at"])).total_seconds() / 86400
            pa += max(d, 0.5)
            pp += p["est_weeks"] * 7
    if pp:
        return max(0.4, min(3.0, pa / pp)), sum(1 for p in s["phases"] if p["state"] == "ACCEPTED")
    actual = planned = 0.0
    n = 0
    for p in s["phases"]:
        per_step = p["est_weeks"] * 7 / len(p["steps"])
        for x in p["steps"].values():
            if x["state"] == "PASS" and x["started_at"] and x["done_at"]:
                a = (dt.datetime.fromisoformat(x["done_at"]) - dt.datetime.fromisoformat(x["started_at"])).total_seconds() / 86400
                actual += max(a, 0.05)
                planned += per_step
                n += 1
    if n < 3 or planned == 0:
        return 1.0, n
    return max(0.5, min(3.0, actual / planned)), n


def topo(s):
    done, order = set(), []
    pend = list(s["phases"])
    while pend:
        for p in list(pend):
            if all(d in done for d in p["deps"]):
                order.append(p)
                done.add(p["id"])
                pend.remove(p)
    return order


def schedule(s, factor: float) -> dict:
    t0 = today()
    fin, start = {}, {}
    for p in topo(s):
        base = max([fin[d] for d in p["deps"]] + [t0])
        if p["state"] == "ACCEPTED" and p["accepted_at"]:
            acc = dt.date.fromisoformat(p["accepted_at"][:10])
            start[p["id"]] = dt.date.fromisoformat(p["started_at"][:10]) if p["started_at"] else acc
            fin[p["id"]] = acc
            continue
        remaining_days = p["est_weeks"] * 7 * factor * (1 - pass_fraction(p))
        if p["state"] == "GATE_PENDING":
            remaining_days = 3  # employer review/UAT window assumption
        st = dt.date.fromisoformat(p["started_at"][:10]) if p["started_at"] else base
        start[p["id"]] = st
        fin[p["id"]] = base + dt.timedelta(days=round(remaining_days))
    return {"start": start, "finish": fin}


def critical_path(s, target="PHASE_13"):
    ph = {p["id"]: p for p in s["phases"]}
    memo = {}

    def longest(pid):
        if pid in memo:
            return memo[pid]
        p = ph[pid]
        best = (0, [])
        for d in p["deps"]:
            c = longest(d)
            if c[0] > best[0]:
                best = c
        memo[pid] = (best[0] + p["est_weeks"], best[1] + [pid])
        return memo[pid]
    return longest(target)


def forecast(s):
    f, n = velocity(s)
    out = {"velocity": f, "measured_steps": n}
    for name, k in (("optimistic", 0.7), ("baseline", 1.0), ("pessimistic", 1.5)):
        sc = schedule(s, f * k)
        out[name] = {"pilot_start": sc["start"]["PHASE_13"] if "PHASE_13" in sc["start"] else None,
                     "pilot_start_calc": sc["finish"]["PHASE_12"], "go_live": sc["finish"]["PHASE_13"],
                     "schedule": sc}
    return out


def current(s):
    active = [p for p in s["phases"] if p["state"] in ("ACTIVE", "GATE_PENDING", "BLOCKED")]
    cur_steps = []
    for p in active:
        for sid, x in p["steps"].items():
            if x["state"] != "PASS":
                cur_steps.append((p, sid, x))
                break
    return active, cur_steps


def next_startable(s):
    acc = {p["id"] for p in s["phases"] if p["state"] == "ACCEPTED"}
    return [p for p in s["phases"] if p["state"] == "NOT_STARTED" and all(d in acc for d in p["deps"])]

# ---------------------------------------------------------------- mutations
def cmd_start_phase(a):
    s = load()
    p = phase(s, a.phase)
    acc = {q["id"] for q in s["phases"] if q["state"] == "ACCEPTED"}
    missing = [d for d in p["deps"] if d not in acc]
    if missing:
        sys.exit(f"REFUSED: {a.phase} depends on unaccepted gates: {missing}")
    if p["state"] != "NOT_STARTED":
        sys.exit(f"REFUSED: {a.phase} is {p['state']}")
    if not a.by:
        sys.exit("REFUSED: --by <employer> required (formal start authorisation)")
    p["state"], p["started_at"] = "ACTIVE", now_iso()
    event(s, "phase_started", phase=a.phase, by=a.by)
    save(s)
    print(f"{a.phase} ACTIVE")


def cmd_step(a):
    s = load()
    p = phase(s, a.phase)
    if p["state"] not in ("ACTIVE", "BLOCKED", "GATE_PENDING"):
        sys.exit(f"REFUSED: phase {a.phase} is {p['state']}; start it first")
    x = p["steps"].get(a.step) or sys.exit(f"unknown step {a.step}")
    new = a.state
    if new not in STEP_TRANSITIONS[x["state"]]:
        sys.exit(f"REFUSED: {x['state']} -> {new} not allowed")
    order = sorted(p["steps"])
    prev = order[:order.index(a.step)]
    if new == "IN_PROGRESS" and any(p["steps"][q]["state"] != "PASS" for q in prev):
        sys.exit(f"REFUSED: earlier steps of {a.phase} not PASS")
    if new == "IN_REVIEW":
        if not (a.commit and a.report):
            sys.exit("REFUSED: IN_REVIEW needs --commit and --report")
        if not (ROOT / a.report).exists():
            sys.exit(f"REFUSED: report file not found: {a.report}")
        x["commit"], x["report"] = a.commit, a.report
    if new == "PASS":
        if not a.review or not (ROOT / a.review).exists():
            sys.exit("REFUSED: PASS needs --review <independent reviewer file> that exists")
        txt = (ROOT / a.review).read_text(encoding="utf-8")
        if "VERDICT: PASS" not in txt:
            sys.exit("REFUSED: review file does not contain 'VERDICT: PASS'")
        x["review"], x["done_at"] = a.review, now_iso()
    if new == "REWORK":
        x["rework_cycles"] += 1
        if a.review:
            x["review"] = a.review
    if new == "IN_PROGRESS" and not x["started_at"]:
        x["started_at"] = now_iso()
    if new == "BLOCKED":
        p["state"] = "BLOCKED"
    elif p["state"] == "BLOCKED":
        p["state"] = "ACTIVE"
    x["state"] = new
    if all(q["state"] == "PASS" for q in p["steps"].values()):
        p["state"], p["gate_pending_at"] = "GATE_PENDING", now_iso()
        event(s, "gate_pending", phase=a.phase)
    event(s, "step", phase=a.phase, step=a.step, state=new, note=a.note, commit=a.commit)
    save(s)
    print(f"{a.phase} {a.step} -> {new}; phase {p['state']}")


def cmd_gate(a):
    s = load()
    p = phase(s, a.phase)
    if p["state"] != "GATE_PENDING":
        sys.exit(f"REFUSED: {a.phase} is {p['state']}, not GATE_PENDING")
    if not a.by:
        sys.exit("REFUSED: --by <employer> required")
    blockers = open_p0(s, a.phase)
    if a.verdict == "ACCEPTED" and blockers:
        sys.exit("REFUSED: open P0 decisions: " + ", ".join(d["id"] for d in blockers))
    if a.verdict == "ACCEPTED":
        p["state"], p["accepted_at"], p["accepted_by"] = "ACCEPTED", now_iso(), a.by
    else:
        p["state"] = "ACTIVE"
    event(s, "gate", phase=a.phase, verdict=a.verdict, by=a.by, note=a.note)
    save(s)
    print(f"{a.phase} gate {a.verdict}")


def cmd_decide(a):
    s = load()
    for d in s["decisions"]:
        if d["id"] == a.id:
            if a.status in CLOSED_DECISION and not (a.by and a.note):
                sys.exit("REFUSED: closing a decision needs --by and --note (decision text)")
            d.update(status=a.status, resolution=a.note or d["resolution"], decided_by=a.by, decided_at=now_iso())
            log = ROOT / "control" / "decisions" / "DECISION_LOG.csv"
            new_file = not log.exists()
            with open(log, "a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["decision_id", "status", "decided_by", "decided_at", "resolution"])
                w.writerow([a.id, a.status, a.by or "", now_iso()[:10], a.note or ""])
            event(s, "decision", id=a.id, status=a.status, by=a.by, note=a.note)
            save(s)
            print(f"{a.id} -> {a.status}")
            return
    sys.exit(f"unknown decision {a.id}")


def cmd_add_decision(a):
    """Register a decision raised after init (from DECISIONS_ADDENDUM.csv). Never overwrites an existing id."""
    s = load()
    if any(d["id"] == a.id for d in s["decisions"]):
        sys.exit(f"REFUSED: {a.id} already exists")
    extra = ROOT / "control" / "decisions" / "DECISIONS_ADDENDUM.csv"
    rows = [r for r in read_csv(extra) if r["decision_id"] == a.id] if extra.exists() else []
    if not rows:
        sys.exit(f"REFUSED: add {a.id} to control/decisions/DECISIONS_ADDENDUM.csv first")
    r = rows[0]
    s["decisions"].append({"id": r["decision_id"], "priority": r["priority"], "gate": r["decision_gate"],
                           "domain": r["domain"], "issue": r["issue"], "status": r["status"],
                           "owner": r["owner"], "phase": r["affects_phase"], "source": r["source"],
                           "resolution": None, "decided_by": None, "decided_at": None})
    event(s, "decision_added", id=a.id, status=r["status"])
    save(s)
    print(f"{a.id} added ({r['status']})")


def cmd_test_add(a):
    s = load()
    tid = f"T-{len(s['ready_for_test']) + 1:03d}"
    s["ready_for_test"].append({"id": tid, "phase": a.phase, "what": a.what, "how": a.how,
                                "since": now_iso(), "result": None, "note": None})
    event(s, "test_ready", id=tid, phase=a.phase)
    save(s)
    print(tid)


def cmd_test_done(a):
    s = load()
    for t in s["ready_for_test"]:
        if t["id"] == a.id:
            t["result"], t["note"] = a.result, a.note
            event(s, "test_result", id=a.id, result=a.result)
            save(s)
            print(f"{a.id} {a.result}")
            return
    sys.exit("unknown test id")

# ---------------------------------------------------------------- multi-machine lock
def read_lock():
    if LOCK_PATH.exists():
        try:
            return json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def lock_age_h(lk) -> float:
    return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(lk["since"])).total_seconds() / 3600


def cmd_lock(a):
    lk = read_lock()
    me = machine()
    if a.action == "show":
        print("قفل: آزاد" if not lk else f"قفل: {lk['machine']} از {lk['since']} ({lk_age_txt(lk)})")
        return
    if a.action == "acquire":
        if lk and lk["machine"] != me and lock_age_h(lk) < LOCK_TTL_HOURS and not a.force:
            sys.exit(f"REFUSED: work is locked by '{lk['machine']}' since {lk['since']}. "
                     f"Finish/release there first, or use --force if that machine is gone.")
        LOCK_PATH.write_text(json.dumps({"machine": me, "since": now_iso(), "note": a.note}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"lock acquired by {me}")
    if a.action == "release":
        if lk and lk["machine"] != me and not a.force:
            sys.exit(f"REFUSED: lock belongs to '{lk['machine']}'")
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
        print("lock released")


def lk_age_txt(lk) -> str:
    h = lock_age_h(lk)
    return f"{h:.1f} ساعت پیش" + (" — منقضی" if h >= LOCK_TTL_HOURS else "")


# ---------------------------------------------------------------- reports
def summary(s) -> dict:
    steps = [x for p in s["phases"] for x in p["steps"].values()]
    passed = sum(1 for x in steps if x["state"] == "PASS")
    active, cur = current(s)
    fc = forecast(s)
    horizon = {p["id"] for p in active} | {p["id"] for p in next_startable(s)}
    if not active and not any(p["state"] == "ACCEPTED" for p in s["phases"]):
        horizon |= {"PHASE_00"}
    needs = [d for d in s["decisions"] if d["status"] not in CLOSED_DECISION and d["phase"] in horizon]
    cp_len, cp = critical_path(s)
    return {"steps_total": len(steps), "steps_pass": passed, "active": active, "current_steps": cur,
            "next": next_startable(s), "forecast": fc, "needs": needs, "critical_path": cp,
            "critical_len": cp_len, "open_p0": open_p0(s),
            "tests_open": [t for t in s["ready_for_test"] if not t["result"]]}


def cmd_brief(a):
    s = load()
    m = summary(s)
    fc = m["forecast"]
    print("== وضعیت پروژه عالیخان ==")
    lk = read_lock()
    print(f"این سیستم: {machine()} | " + ("قفل کار: آزاد" if not lk else f"قفل کار دست: {lk['machine']} ({lk_age_txt(lk)})"))
    if m["active"]:
        for p in m["active"]:
            print(f"فاز {fa(p['id'][-2:])} «{p['title_fa']}»: {STATE_FA[p['state']]}")
        for p, sid, x in m["current_steps"]:
            print(f"  گام جاری {fa(sid)} {x['name']}: {STATE_FA[x['state']]} (اصلاح: {fa(x['rework_cycles'])})")
    else:
        print("هیچ فازی فعال نیست. قابل شروع: " + (", ".join(p["id"] for p in m["next"]) or "-"))
    print(f"پیشرفت: {fa(m['steps_pass'])}/{fa(m['steps_total'])} گام قبول‌شده")
    print(f"آماده تست کارفرما: {fa(len(m['tests_open']))} مورد")
    print("تصمیم‌های باز در افق فعلی: " + (", ".join(f"{d['id']}({d['priority']})" for d in m["needs"]) or "ندارد"))
    b = fc["baseline"]
    print(f"برآورد شروع پایلوت (فرض برنامه‌ریزی): خوش‌بینانه {jdate(fc['optimistic']['pilot_start_calc'])} | "
          f"مبنا {jdate(b['pilot_start_calc'])} | بدبینانه {jdate(fc['pessimistic']['pilot_start_calc'])}"
          f" — ضریب سرعت {fc['velocity']:.2f} از {fa(fc['measured_steps'])} گام اندازه‌گیری‌شده")


def mermaid(s, cp) -> str:
    cls = {"NOT_STARTED": "ns", "ACTIVE": "act", "GATE_PENDING": "gp", "ACCEPTED": "ok", "BLOCKED": "bl"}
    lines = ["flowchart LR"]
    for p in s["phases"]:
        n = p["id"][-2:]
        lines.append(f'  P{n}["{n} · {p["title_fa"]}<br/>{p["est_weeks"]}w · {STATE_FA[p["state"]]}"]:::{cls[p["state"]]}')
    for p in s["phases"]:
        for d in p["deps"]:
            arrow = "==>" if (d in cp and p["id"] in cp and cp.index(p["id"]) == cp.index(d) + 1) else "-->"
            lines.append(f"  P{d[-2:]} {arrow} P{p['id'][-2:]}")
    lines += ["  classDef ns fill:#eef0f3,stroke:#8a94a6,color:#1d2433",
              "  classDef act fill:#dbe9ff,stroke:#2f6fe4,color:#0b2a66,stroke-width:2px",
              "  classDef gp fill:#fff1cc,stroke:#c98a00,color:#5a3d00,stroke-width:2px",
              "  classDef ok fill:#d8f3e3,stroke:#1f9254,color:#0c3d22",
              "  classDef bl fill:#ffe0e0,stroke:#d33b3b,color:#5c0f0f,stroke-width:2px"]
    return "\n".join(lines)


def render_md(s, m) -> str:
    fc = m["forecast"]
    L = [f"# وضعیت پروژه عالیخان — {jdate(today(), True)}", "",
         "> تاریخ‌ها برآورد برنامه‌ریزی‌اند، نه تعهد. با هر گام قبول‌شده، ضریب سرعت واقعی جایگزین فرض می‌شود.", ""]
    L += ["## خلاصه", "",
          f"- **فاز فعال:** " + (", ".join(f"{p['id']} {p['title_fa']} ({STATE_FA[p['state']]})" for p in m["active"]) or "ندارد — " + "قابل شروع: " + ", ".join(p["id"] for p in m["next"])),
          f"- **گام جاری:** " + (", ".join(f"{sid} {x['name']} ({STATE_FA[x['state']]})" for _, sid, x in m["current_steps"]) or "—"),
          f"- **پیشرفت:** {m['steps_pass']}/{m['steps_total']} گام قبول‌شده",
          f"- **آماده تست شما:** {len(m['tests_open'])} مورد",
          f"- **تصمیم P0 باز (کل پروژه):** {len(m['open_p0'])}",
          f"- **شروع پایلوت (PHASE_13):** خوش‌بینانه {jdate(fc['optimistic']['pilot_start_calc'], True)} · مبنا **{jdate(fc['baseline']['pilot_start_calc'], True)}** · بدبینانه {jdate(fc['pessimistic']['pilot_start_calc'], True)}",
          f"- **مسیر بحرانی:** {' → '.join(x[-2:] for x in m['critical_path'])} — تا شروع پایلوت {m['critical_len'] - phase(s, 'PHASE_13')['est_weeks']} هفته برآوردی", ""]
    L += ["## آماده تست", ""]
    if m["tests_open"]:
        L += ["| شناسه | فاز | چه چیزی | چطور تست کنید |", "|---|---|---|---|"]
        L += [f"| {t['id']} | {t['phase']} | {t['what']} | {t['how']} |" for t in m["tests_open"]]
    else:
        L += ["هنوز چیزی برای تست عملیاتی آماده نیست."]
    L += ["", "## منتظر تصمیم شما (افق فعلی)", ""]
    if m["needs"]:
        L += ["| شناسه | اولویت | موضوع | مالک | وضعیت |", "|---|---|---|---|---|"]
        L += [f"| {d['id']} | {d['priority']} | {d['issue']} | {d['owner']} | {d['status']} |" for d in m["needs"]]
    else:
        L += ["تصمیم بازی در افق فعلی نیست."]
    L += ["", "## گراف وابستگی فازها", "", "```mermaid", mermaid(s, m["critical_path"]), "```", "",
          "## جدول فازها", "", "| فاز | عنوان | وابستگی | وضعیت | گام قبول | برآورد (هفته) | شروع | پایان (مبنا) |",
          "|---|---|---|---|---|---|---|---|"]
    sc = fc["baseline"]["schedule"]
    for p in s["phases"]:
        ok = sum(1 for x in p["steps"].values() if x["state"] == "PASS")
        L.append(f"| {p['id']} | {p['title_fa']} | {', '.join(d[-2:] for d in p['deps']) or '—'} | {STATE_FA[p['state']]} | {ok}/8 | {p['est_weeks']} | {jdate(sc['start'][p['id']])} | {jdate(sc['finish'][p['id']])} |")
    ev = s.get("events", [])[-15:]
    L += ["", "## آخرین رویدادها", ""]
    L += [f"- `{e['at']}` {e['kind']} " + " ".join(f"{k}={v}" for k, v in e.items() if k not in ('at', 'kind') and v) for e in reversed(ev)] or ["—"]
    return "\n".join(L) + "\n"


def render_html(s, m) -> str:
    fc = m["forecast"]
    sc = fc["baseline"]["schedule"]
    cp = m["critical_path"]
    order = topo(s)
    ids = {p["id"]: p for p in s["phases"]}
    anc = {}
    for p in order:
        a_ = set()
        for d in p["deps"]:
            a_ |= {d} | anc[d]
        anc[p["id"]] = a_
    def reduced(p):  # transitive reduction for a readable drawing
        return [d for d in p["deps"] if not any(d in anc[o] for o in p["deps"] if o != d)]
    level = {}
    for p in order:
        level[p["id"]] = 1 + max([level[d] for d in p["deps"]] + [-1])
    rows_ = {}
    for p in order:
        rows_.setdefault(level[p["id"]], []).append(p)
    NW, NH, GX, GY = 250, 54, 28, 34
    maxc = max(len(v) for v in rows_.values())
    W = maxc * NW + (maxc - 1) * GX + 20
    H = len(rows_) * (NH + GY) - GY + 20
    pos = {}
    for r, ps in rows_.items():
        tot = len(ps) * NW + (len(ps) - 1) * GX
        x0 = (W - tot) / 2
        for i, p in enumerate(ps):
            x = W - x0 - (i + 1) * NW - i * GX  # RTL order inside a row
            pos[p["id"]] = (x, 10 + r * (NH + GY))
    edges = []
    for p in s["phases"]:
        for d in reduced(p):
            x1, y1 = pos[d]; x2, y2 = pos[p["id"]]
            crit = d in cp and p["id"] in cp and cp.index(p["id"]) == cp.index(d) + 1
            sx, sy, ex, ey = x1 + NW / 2, y1 + NH, x2 + NW / 2, y2 - 2
            my = (sy + ey) / 2
            edges.append(f'<path d="M{sx:.0f},{sy:.0f} C{sx:.0f},{my:.0f} {ex:.0f},{my:.0f} {ex:.0f},{ey:.0f}" class="edge{" crit" if crit else ""}" marker-end="url(#{"ac" if crit else "a"})"/>')
    nodes = []
    for p in s["phases"]:
        x, y = pos[p["id"]]
        ok = sum(1 for q in p["steps"].values() if q["state"] == "PASS")
        w = (NW - 24) * ok / 8
        t = p["title_fa"]
        t = t if len(t) <= 34 else t[:33] + "…"
        nodes.append(
            f'<g class="node st-{p["state"]}{" oncp" if p["id"] in cp else ""}"><title>{html.escape(p["title_fa"])} — {p["est_weeks"]} هفته برآورد</title>'
            f'<rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="6"/>'
            f'<text x="{x + NW - 12}" y="{y + 21}" class="nid" text-anchor="start" direction="rtl">فاز {fa(p["id"][-2:])} — {STATE_FA[p["state"]]} ({fa(ok)} از {fa(8)} گام)</text>'
            f'<text x="{x + NW - 12}" y="{y + 39}" class="nt" text-anchor="start" direction="rtl">{html.escape(t)}</text>'
            f'<rect x="{x + 12}" y="{y + NH - 8}" width="{NW - 24}" height="3" rx="1.5" class="pbg"/>'
            f'<rect x="{x + NW - 12 - w:.1f}" y="{y + NH - 8}" width="{w:.1f}" height="3" rx="1.5" class="pfg"/></g>')
    graph = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="گراف وابستگی فازها" style="direction:ltr;margin-inline:auto">'
             '<defs><marker id="a" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="ah"/></marker>'
             '<marker id="ac" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="ahc"/></marker></defs>'
             + "".join(edges) + "".join(nodes) + "</svg>")
    # Gantt
    t0 = min(sc["start"].values())
    t1 = max(sc["finish"].values())
    span = max((t1 - t0).days, 1)
    rows = []
    for p in s["phases"]:
        a_, b_ = sc["start"][p["id"]], sc["finish"][p["id"]]
        r0 = (a_ - t0).days / span * 100
        r1 = max((b_ - a_).days / span * 100, 0.8)
        rows.append(f'<div class="grow"><div class="glab"><b>{fa(p["id"][-2:])}</b> {html.escape(p["title_fa"])}</div>'
                    f'<div class="gtrack"><div class="gbar st-{p["state"]}{" oncp" if p["id"] in cp else ""}" style="right:{r0:.2f}%;width:{r1:.2f}%" title="{jdate(a_)} تا {jdate(b_)}"></div></div>'
                    f'<div class="gdate">{jdate(b_)}</div></div>')
    ticks = []
    d = dt.date(t0.year, t0.month, 1)
    while d <= t1:
        if d >= t0:
            ticks.append(f'<span style="right:{(d - t0).days / span * 100:.2f}%">{jmonth(d)}</span>')
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    pil = fc["baseline"]["pilot_start_calc"]
    pil_mark = f'<div class="pmark" style="right:{(pil - t0).days / span * 100:.2f}%;height:{len(s["phases"]) * 27 + 4}px"><span>شروع پایلوت</span></div>'
    def tbl(rows_, head):
        if not rows_:
            return '<p class="empty">موردی نیست.</p>'
        return '<div class="tw"><table><thead><tr>' + "".join(f"<th>{h}</th>" for h in head) + "</tr></thead><tbody>" + "".join(rows_) + "</tbody></table></div>"
    needs_rows = [f'<tr><td class="mono">{d["id"]}</td><td><span class="pri p{d["priority"][-1]}">{d["priority"]}</span></td><td>{html.escape(d["issue"])}</td><td>{html.escape(d["owner"])}</td><td>{d["phase"][-2:]}</td></tr>' for d in m["needs"]]
    test_rows = [f'<tr><td class="mono">{t["id"]}</td><td>{t["phase"][-2:]}</td><td>{html.escape(t["what"])}</td><td>{html.escape(t["how"])}</td></tr>' for t in m["tests_open"]]
    act = "، ".join(f'{fa(p["id"][-2:])} · {p["title_fa"]}' for p in m["active"]) or "هیچ فازی هنوز شروع نشده"
    cur = "، ".join(f'{fa(sid)} {x["name"]} — {STATE_FA[x["state"]]}' for _, sid, x in m["current_steps"]) or ("قابل شروع: " + "، ".join(fa(p["id"][-2:]) for p in m["next"]) if m["next"] else "—")
    p0_all = len(m["open_p0"])
    return TEMPLATE.format(
        today=jdate(today(), True), act=html.escape(act), cur=html.escape(cur),
        sp=fa(m["steps_pass"]), st=fa(m["steps_total"]), pct=m["steps_pass"] / m["steps_total"] * 100,
        tests=fa(len(m["tests_open"])), p0=fa(p0_all),
        pil_o=jdate(fc["optimistic"]["pilot_start_calc"], True), pil_b=jdate(pil, True),
        pil_p=jdate(fc["pessimistic"]["pilot_start_calc"], True),
        vel=fa(f'{fc["velocity"]:.2f}'), meas=fa(fc["measured_steps"]),
        cp=" ← ".join(fa(x[-2:]) for x in m["critical_path"]), cpl=fa(m["critical_len"] - ids["PHASE_13"]["est_weeks"]),
        graph=graph, gantt="".join(rows), ticks="".join(ticks), pmark=pil_mark,
        needs=tbl(needs_rows, ["شناسه", "اولویت", "موضوع", "مالک", "فاز"]),
        tests_tbl=tbl(test_rows, ["شناسه", "فاز", "چه چیزی", "چطور تست کنید"]),
        updated=html.escape(s.get("updated_at", "")))


TEMPLATE = """<title>کنترل پروژه عالیخان</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;700;800&family=JetBrains+Mono:wght@500&display=swap">
<style>
/* layout: one reading column, summary strip -> needs -> dependency graph -> timeline; RTL */
:root{{--bg:#f5f6f2;--surface:#ffffff;--ink:#1c2420;--muted:#5d6a63;--line:#d9ded8;--accent:#0f6b5c;--accent-soft:#d6ece6;
--ns:#e9ece8;--ns-s:#8d9891;--act:#d9e7ff;--act-s:#2c63d6;--gp:#fff0c7;--gp-s:#b07a00;--ok:#d5f0df;--ok-s:#1d8a4e;--bl:#ffdede;--bl-s:#c43434;
--crit:#c2410c;--font:"Vazirmatn",Tahoma,"Segoe UI",sans-serif;--mono:"JetBrains Mono",ui-monospace,Consolas,monospace}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#121715;--surface:#1a211e;--ink:#e6ece8;--muted:#9aa8a0;--line:#2c3631;--accent:#4cc3a9;--accent-soft:#1d3a33;
--ns:#232b27;--ns-s:#6e7b74;--act:#1b2c4d;--act-s:#6f9dff;--gp:#3a2f12;--gp-s:#e0b33e;--ok:#173a27;--ok-s:#4bc583;--bl:#401c1c;--bl-s:#ff7b7b;--crit:#fb8c4c;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#121715;--surface:#1a211e;--ink:#e6ece8;--muted:#9aa8a0;--line:#2c3631;--accent:#4cc3a9;--accent-soft:#1d3a33;
--ns:#232b27;--ns-s:#6e7b74;--act:#1b2c4d;--act-s:#6f9dff;--gp:#3a2f12;--gp-s:#e0b33e;--ok:#173a27;--ok-s:#4bc583;--bl:#401c1c;--bl-s:#ff7b7b;--crit:#fb8c4c;color-scheme:dark}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);font-family:var(--font);direction:rtl;margin:0;line-height:1.7;font-size:15px}}
.wrap{{max-width:1180px;margin:0 auto;padding-block:28px 56px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:28px}}
header{{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:end;gap:8px 24px;border-bottom:2px solid var(--ink);padding-bottom:12px}}
h1{{font-size:clamp(22px,3.4vw,30px);font-weight:800;margin:0;text-wrap:balance}}
h2{{font-size:17px;font-weight:700;margin:0 0 10px}}
.sub{{color:var(--muted);font-size:13px}}
.strip{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:8px;overflow:hidden}}
.cell{{background:var(--surface);padding:14px 16px;display:grid;gap:2px;min-width:0}}
.lab{{font-size:12px;color:var(--muted);letter-spacing:.02em}}
.val{{font-size:17px;font-weight:700}}
.val.big{{font-size:22px;color:var(--accent)}}
.meter{{height:6px;background:var(--ns);border-radius:3px;overflow:hidden;margin-top:6px}}
.meter i{{display:block;height:100%;background:var(--accent);width:{pct:.1f}%;margin-inline-start:0}}
@media (max-width:820px){{.strip{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media (max-width:480px){{.strip{{grid-template-columns:1fr}}}}
.note{{background:var(--accent-soft);border-radius:8px;padding:10px 14px;font-size:13px}}
section{{display:grid;gap:4px;min-width:0}}
.tw,.gw{{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--surface)}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}}
th,td{{text-align:right;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-weight:700;color:var(--muted);font-size:12px;background:var(--bg)}}
tr:last-child td{{border-bottom:0}}
.mono{{font-family:var(--mono);font-size:12.5px;white-space:nowrap;direction:ltr;text-align:right}}
.pri{{font-family:var(--mono);font-size:11.5px;padding:1px 7px;border-radius:10px;border:1px solid}}
.pri.p0{{color:var(--bl-s);background:var(--bl);border-color:var(--bl-s)}} .pri.p1{{color:var(--gp-s);background:var(--gp);border-color:var(--gp-s)}} .pri.p2{{color:var(--muted);border-color:var(--line)}}
.empty{{color:var(--muted);margin:0;padding:12px 14px;border:1px dashed var(--line);border-radius:8px}}
.gw{{padding:10px}}
svg{{display:block;font-family:var(--font)}}
.edge{{fill:none;stroke:var(--ns-s);stroke-width:1.2;opacity:.75}} .edge.crit{{stroke:var(--crit);stroke-width:2.4;opacity:1}}
.ah{{fill:var(--ns-s)}} .ahc{{fill:var(--crit)}}
.node rect:first-of-type{{stroke-width:1.4}}
.node.oncp rect:first-of-type{{stroke:var(--crit)!important;stroke-width:2.4}}
.nid{{font-size:12px;font-weight:700;fill:var(--ink)}}
.nt{{font-size:12.5px;fill:var(--muted)}}
.pbg{{fill:var(--line)}} .pfg{{fill:var(--accent)}}
.st-NOT_STARTED rect:first-of-type{{fill:var(--ns);stroke:var(--ns-s)}} .st-ACTIVE rect:first-of-type{{fill:var(--act);stroke:var(--act-s)}}
.st-GATE_PENDING rect:first-of-type{{fill:var(--gp);stroke:var(--gp-s)}} .st-ACCEPTED rect:first-of-type{{fill:var(--ok);stroke:var(--ok-s)}} .st-BLOCKED rect:first-of-type{{fill:var(--bl);stroke:var(--bl-s)}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px;color:var(--muted)}}
.legend span::before{{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;margin-inline-end:6px;vertical-align:-1px;background:var(--c);border:1px solid var(--s)}}
.gantt{{display:grid;gap:4px;padding:10px 12px 28px;min-width:640px}}
.grow{{display:grid;grid-template-columns:minmax(150px,230px) 1fr 82px;gap:10px;align-items:center;font-size:12.5px}}
.glab{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}} .glab b{{font-family:var(--mono);margin-inline-end:4px}}
.gtrack{{position:relative;height:14px;background:var(--bg);border-radius:3px}}
.gbar{{position:absolute;top:0;bottom:0;border-radius:3px;background:var(--ns-s);opacity:.55}}
.gbar.oncp{{background:var(--crit);opacity:.85}} .gbar.st-ACTIVE{{background:var(--act-s);opacity:1}} .gbar.st-ACCEPTED{{background:var(--ok-s);opacity:1}} .gbar.st-GATE_PENDING{{background:var(--gp-s);opacity:1}} .gbar.st-BLOCKED{{background:var(--bl-s);opacity:1}}
.gdate{{font-family:var(--mono);font-size:11.5px;color:var(--muted);text-align:left}}
.gaxis{{position:relative;height:22px;margin-inline-start:calc(min(230px, 30%) + 10px);margin-inline-end:92px;font-size:11px;color:var(--muted)}}
.gaxis span{{position:absolute;top:2px;white-space:nowrap;transform:translateX(50%)}}
.pzone{{position:relative;margin-inline-start:calc(min(230px, 30%) + 10px);margin-inline-end:92px;height:0}}
.pmark{{position:absolute;top:0;border-inline-start:2px dashed var(--crit);pointer-events:none}}
.pmark span{{position:absolute;bottom:-20px;right:-30px;font-size:11px;font-weight:700;color:var(--crit);white-space:nowrap}}
footer{{font-size:12px;color:var(--muted)}}
</style>
<div class="wrap">
<header><div><h1>کنترل پروژه عالیخان</h1><div class="sub">وضعیت فازها، Gateها و برآورد پایلوت · {today}</div></div>
<div class="sub">مبنا: بسته Handoff نسخه ۱٫۰ · ۱۵ فاز · ۱۲۰ گام</div></header>
<div class="strip">
<div class="cell"><span class="lab">فاز فعال</span><span class="val">{act}</span></div>
<div class="cell"><span class="lab">گام جاری</span><span class="val">{cur}</span></div>
<div class="cell"><span class="lab">پیشرفت گام‌ها</span><span class="val">{sp} از {st}</span><div class="meter"><i></i></div></div>
<div class="cell"><span class="lab">آماده تست شما</span><span class="val">{tests} مورد</span></div>
<div class="cell"><span class="lab">تصمیم‌های P0 باز</span><span class="val">{p0}</span></div>
<div class="cell"><span class="lab">شروع پایلوت (برآورد مبنا)</span><span class="val big">{pil_b}</span><span class="sub">بازه: {pil_o} تا {pil_p}</span></div>
</div>
<div class="note">تاریخ‌ها برآوردند و تعهد نیستند. فرض: هر فاز با ممیزی و زمان پاسخ تصمیم‌ها، مدت مشخصی می‌گیرد. ضریب سرعت فعلی {vel} است (از {meas} گام اندازه‌گیری‌شده). بیشترین ریسک زمان، تأخیر در تصمیم‌های P0 است، نه کدنویسی.</div>
<section><h2>منتظر تصمیم شما</h2>{needs}</section>
<section><h2>آماده تست</h2>{tests_tbl}</section>
<section><h2>گراف وابستگی فازها</h2>
<div class="legend"><span style="--c:var(--ns);--s:var(--ns-s)">شروع‌نشده</span><span style="--c:var(--act);--s:var(--act-s)">فعال</span><span style="--c:var(--gp);--s:var(--gp-s)">منتظر Gate</span><span style="--c:var(--ok);--s:var(--ok-s)">پذیرفته‌شده</span><span style="--c:var(--bl);--s:var(--bl-s)">مسدود</span><span style="--c:transparent;--s:var(--crit)">مسیر بحرانی</span></div>
<div class="gw">{graph}</div>
<div class="sub">مسیر بحرانی: {cp}. طول تا شروع پایلوت: {cpl} هفته برآوردی. یال‌های ضمنی (وابستگی‌هایی که از مسیر دیگر برقرارند) برای خوانایی رسم نشده‌اند.</div></section>
<section><h2>زمان‌بندی برآوردی</h2>
<div class="gw"><div class="gantt"><div class="gaxis">{ticks}</div><div class="pzone">{pmark}</div>{gantt}</div></div></section>
<footer>تولیدشده خودکار از control/PROJECT_STATUS.json · آخرین به‌روزرسانی {updated}</footer>
</div>
"""


def cmd_render(a):
    s = load()
    m = summary(s)
    (ROOT / "control" / "STATUS_FA.md").write_text(render_md(s, m), encoding="utf-8")
    (ROOT / "control" / "STATUS.html").write_text(render_html(s, m), encoding="utf-8")
    print("wrote control/STATUS_FA.md and control/STATUS.html")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("init"); x.add_argument("--handoff", required=True); x.add_argument("--extra-decisions"); x.set_defaults(f=cmd_init)
    sub.add_parser("brief").set_defaults(f=cmd_brief)
    sub.add_parser("render").set_defaults(f=cmd_render)
    x = sub.add_parser("start-phase"); x.add_argument("phase"); x.add_argument("--by"); x.set_defaults(f=cmd_start_phase)
    x = sub.add_parser("step"); x.add_argument("phase"); x.add_argument("step"); x.add_argument("state", choices=STEP_STATES)
    x.add_argument("--commit"); x.add_argument("--report"); x.add_argument("--review"); x.add_argument("--note"); x.set_defaults(f=cmd_step)
    x = sub.add_parser("gate"); x.add_argument("phase"); x.add_argument("verdict", choices=["ACCEPTED", "REJECTED"])
    x.add_argument("--by"); x.add_argument("--note"); x.set_defaults(f=cmd_gate)
    x = sub.add_parser("decide"); x.add_argument("id"); x.add_argument("status"); x.add_argument("--by"); x.add_argument("--note"); x.set_defaults(f=cmd_decide)
    x = sub.add_parser("add-decision"); x.add_argument("id"); x.set_defaults(f=cmd_add_decision)
    x = sub.add_parser("test-add"); x.add_argument("phase"); x.add_argument("what"); x.add_argument("how"); x.set_defaults(f=cmd_test_add)
    x = sub.add_parser("test-done"); x.add_argument("id"); x.add_argument("--result", required=True, choices=["PASS", "FAIL"]); x.add_argument("--note"); x.set_defaults(f=cmd_test_done)
    x = sub.add_parser("lock"); x.add_argument("action", choices=["acquire", "release", "show"]); x.add_argument("--force", action="store_true"); x.add_argument("--note"); x.set_defaults(f=cmd_lock)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
