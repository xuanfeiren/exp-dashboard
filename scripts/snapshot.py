#!/usr/bin/env python3
"""Freeze a dashboard into one self-contained HTML (data inlined, no polling) — for the campaign
folder / report appendix after the run ends.

    snapshot.py <dashboard_dir>/index.html <dashboard_dir>/live.json <dashboard_dir>/snapshot_YYYYMMDD.html
"""
import json, sys


def main():
    html_in, live_in, out = sys.argv[1:4]
    html = open(html_in, encoding="utf-8").read()
    live = json.load(open(live_in))
    live["_snapshot"] = True
    tag = "<script>window.__SNAPSHOT__ = " + json.dumps(live, ensure_ascii=False).replace("</", "<\\/") + ";</script>\n<script>"
    if "<script>" not in html:
        sys.exit("no <script> block found in " + html_in)
    html = html.replace("<script>", tag, 1)
    open(out, "w", encoding="utf-8").write(html)
    print("wrote", out)


if __name__ == "__main__":
    main()
