#!/usr/bin/env python3
"""Append narrative / verdicts to the hand-maintained state.json that the collector merges into live.json.
The user reads the dashboard instead of the terminal, so every launch, verdict, incident and phase change goes here.

    logline.py STATE log "wave 1 launched: 4 arms"
    logline.py STATE now_doing "Wave 1 running (4 arms); wave 2 queued; ETA 15:50"
    logline.py STATE phase_note "one-line banner under the title"
    logline.py STATE phase analysis running "started writing the report"     # manual phases: queued|running|done
    logline.py STATE incident error "60 agents died at 180 min — credentials expired"
    logline.py STATE gate "G1 · lessons < none" pass "p=0.004, 25/25 vs 16/25"
    logline.py STATE hypothesis H2 refuted "code < lessons on both tasks"
    logline.py STATE notes "<replace the free-text notes block>"

Writes atomically; safe to call from anywhere the state file is reachable (locally or via one ssh command).
"""
import json, os, sys, time


def main():
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(1)
    path, kind, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    try: st = json.load(open(path))
    except (OSError, json.JSONDecodeError): st = {}
    now = time.time(); log = st.setdefault("log", [])
    if kind == "log":
        log.append({"t": now, "text": " ".join(rest)})
    elif kind in ("now_doing", "phase_note", "notes"):
        st[kind] = " ".join(rest);
        if kind == "now_doing": log.append({"t": now, "text": "→ " + st[kind]})
    elif kind == "incident":
        sev, text = rest[0], " ".join(rest[1:])
        st.setdefault("incidents", []).append({"t": now, "severity": sev, "text": text}); log.append({"t": now, "text": f"[{sev}] {text}"})
    elif kind == "gate":
        name, status, detail = rest[0], rest[1], " ".join(rest[2:])
        gates = st.setdefault("gates", [])
        for g in gates:
            if g.get("name") == name: g.update({"status": status, "detail": detail}); break
        else: gates.append({"name": name, "status": status, "detail": detail})
        log.append({"t": now, "text": f"gate {name}: {status} {detail}".strip()})
    elif kind == "hypothesis":
        hid, status, evidence = rest[0], rest[1], " ".join(rest[2:])
        hs = st.setdefault("hypotheses", [])
        for h in hs:
            if h.get("id") == hid: h.update({"status": status, "evidence": evidence}); break
        else: hs.append({"id": hid, "status": status, "evidence": evidence})  # text comes from plan.json (merged by id)
        log.append({"t": now, "text": f"{hid}: {status} — {evidence}".strip(" —")})
    elif kind == "phase":
        pid, status, note = rest[0], rest[1], " ".join(rest[2:])
        ph = st.setdefault("phases", {}).setdefault(pid, {})
        ph["status"] = status
        if status == "running" and not ph.get("start"): ph["start"] = now
        if status == "done": ph["end"] = now; ph.setdefault("start", now)
        if note: ph["note"] = note
        log.append({"t": now, "text": f"phase {pid} → {status} {note}".strip()})
    else:
        print(f"unknown kind {kind}"); sys.exit(1)
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


if __name__ == "__main__":
    main()
