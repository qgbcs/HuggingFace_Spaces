# -*- coding: utf-8 -*-
"""分析 _poll.json：对每个目标 cid 比对 服务端已发水位 / 各 broker 实收 / 重组放行。"""
import collections, json

d = json.load(open("_poll.json", encoding="utf-8"))
polls, raw = d["polls"], d["raw"]

# 只看 WS 目标（polls 的 detail 里 desc=10.120.116.253:1133）
ws_cids = set()
for p in polls:
    for c in p.get("detail", []):
        if "10.120.116.253" in c.get("desc", ""):
            ws_cids.add(c["cid"])
print("WS cids:", sorted(ws_cids))

# raw: (cid, seq, broker, ts)
by_cid = collections.defaultdict(dict)  # cid -> seq -> [(broker,ts)]
for cid, seq, broker, ts in raw:
    by_cid[cid].setdefault(seq, []).append((broker, ts))

for cid in sorted(ws_cids):
    seqs = by_cid.get(cid, {})
    if not seqs:
        print("\ncid=%d 无原始帧" % cid)
        continue
    smax = max(seqs)
    # opened=0/数据/closed 都算；只分析连续空间的空洞
    present = set(seqs)
    holes = sorted(s for s in range(0, smax + 1) if s not in present)
    multi = sum(1 for s, lst in seqs.items() if len(lst) > 1)
    print("\n==== cid=%d  seq范围 0..%d  缺失=%s  多副本seq=%d/%d"
          % (cid, smax, holes[:12], multi, len(seqs)))
    # 空洞附近各 broker 到达情况（前后各2个seq）
    for h in holes[:4]:
        around = {}
        for s in range(max(0, h - 2), min(smax, h + 3) + 1):
            lst = seqs.get(s)
            around[s] = (len(lst), sorted({b for b, _ in lst})[:3]) if lst else None
        print("  空洞 seq=%d 附近(broker数): %s" % (h, around))

# 时间线：每秒 client 放行水位 vs 服务端已发水位
print("\n==== 水位时间线（仅 WS cid）====")
for p in polls:
    det = {c["cid"]: c for c in p.get("detail", []) if c["cid"] in ws_cids}
    srv = (p.get("srv") or {}).get("conns", {}) if p.get("srv") else {}
    srv = {int(k): v for k, v in srv.items() if int(k) in ws_cids}
    if not det and not srv:
        continue
    parts = []
    for cid in sorted(set(det) | set(srv)):
        c = det.get(cid)
        s = srv.get(cid)
        parts.append("cid%d{cli_next=%s wait=%s | srv_dmax=%s srv_umax=%s rw=%s}"
                     % (cid,
                        c["down_delivered_next"] if c else "-",
                        (c["down_waiting"][:4] if c else "-"),
                        s[0] if s else "-", s[1] if s else "-",
                        (s[2:5] if s else "-")))
    print("t=%s pub_err=%s  %s" % (p.get("ts"), p.get("pub_err"), " | ".join(parts)))
