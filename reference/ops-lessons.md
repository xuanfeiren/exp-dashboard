# Operating lessons baked into this skill

Each of these cost a real multi-hour campaign. They are generic; the incidents behind them came from
agent-driven optimisation benchmarks, RL training sweeps and qualitative agent studies running for
hours to days on remote GPU/accelerator hosts.

## Monitoring itself
1. **A monitor must prove it can see data before it is trusted.** A stall detector once watched the
   final results directory while the live events were still in a scratch sandbox: every arm looked
   stalled at exactly the same minute and was cut. `collector.py --check` prints each arm's `src`;
   refuse to detach on `with_data = 0`.
2. **Live data location ≠ final data location.** Harnesses often write to a scratch dir while running
   and copy results out at the end; scratch dirs vanish on reboot. Adapters read both, preferring the
   live one while it exists (`adapters/multi_lane.py` `live_root`).
3. **Show heartbeat age, red when stale.** A frozen page that looks healthy is the worst failure mode.
   Stale means the collector, the puller or the link died — all three have happened.
4. **Detect silent arms and mass silence.** Sixty agents once died in the same minute when the host's
   credentials expired; the scheduler still listed them as running. `silent_after_min` per arm plus
   the automatic "N arms silent within 3 min" incident catch this.
5. **Silence thresholds scale with evaluation cost.** A task whose first evaluation takes 29 minutes
   must not have a 16-minute stall rule. Set `silent_after_min` from the slowest expected gap.
6. **Estimates italic, observations upright; provisional values starred.** Users read an ETA as a
   promise and a best-so-far as a final unless the typography says otherwise.

## Processes on the data host
7. Launch collectors and schedulers with `setsid nohup … < /dev/null > x.log 2>&1 &`. Without the
   stdin redirect the ssh session hangs; without `setsid` a recycled session takes the process tree.
8. `pkill -f PATTERN` matches the ssh command line that carries PATTERN and kills the ssh itself.
   Kill by exact command line (`pkill -xf "…"`) or with the `[c]ollector.py` bracket trick, in its own
   ssh call with nothing after it.
9. Heredocs and inline scripts through ssh get quote-mangled: `scp` the file, then run it.
10. Never edit a running shell script in place (bash reads it incrementally).
11. Orchestration and collection live **on the data host**. Laptops sleep, VPNs drop, sessions get
    summarised. The laptop is a puller and a browser.
12. Multi-day runs need credentials that renew themselves (instance roles, service accounts), not a
    human's login session.
13. Two schedulers on one host without a resource partition collide confusingly; show occupancy on
    the Ops tab and reserve a few units for side experiments.
14. Compiler/eval caches grow gigabytes per evaluation and have filled 500 GB disks mid-campaign.
    Report `disk_pct_used`; red above 90%.

## Reading the numbers
15. Every plot shows **all** levels of the grouping factor, not just this wave's arms.
16. Print `n` next to every aggregate. In one program, every n=3 story but one died at n=5.
17. Re-measure fixed reference artifacts through the run (anchors); >2% drift means the machine
    changed and the round's comparisons are discounted.
18. Cost / token counts are censored on arms that used the whole budget; show sums with that caveat.
19. Pre-registered gates go on the page before data arrives (`pending`), so verdicts are read against
    the frozen bar rather than the shape of the curves.

## Frontend
20. One HTML file, vanilla JS, inline SVG, no CDN, no build. It must open from
    `python3 -m http.server` on a box without internet and freeze into a single snapshot file.
21. Fetch with a cache-buster; write live.json via temp file + rename so a half file is never served.
22. Every chart carries a one-sentence "how to read this"; people come back weeks later and to
    campaigns they did not design.
