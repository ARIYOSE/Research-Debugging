"""
slicer.py : trace.csv から時間方向の動的後ろ向きスライスを求め、縮約して表示する
 
使い方:
    python slicer.py trace_bug1.csv --frame 101 --var player.state
    python slicer.py trace_bug1.csv --frame 101 --var player.state --expect player.grounded:60
    python slicer.py trace_bug1.csv --frame 101 --var player.state --window 30 --out slice.csv
 
スライス（Agrawal & Horgan の手法3：動的依存グラフ）:
    - trace.csv の1行 = 1回の代入（ノード）。同じ変数でもフレームが違えば別ノード
    - 各ノードの uses の変数について、その時点で「最後に書き込まれたノード」へ辺を張る
    - 基準のノードから辺を逆向きに辿り、到達したノードの集合をスライスとする
 
縮約:
    - 同じ「書き込み場所」（変数名 + ソースの行）のノードを、連続するフレームごとに区間にまとめる
    - 離散値（フラグや状態）の場所は、値が変わったら区間を切る
    - 連続値（位置や速度）の場所は、次のどちらかで区間を切る
        (a) 変化点：3階差分が閾値を超えた（=加速度が一定でなくなった）
        (b) 出来事：関係する離散値の変数が、そのフレームで値を変えた
    - (b) の出来事が起きたのに (a) の変化点が無かった箇所を「効果の無い出来事」として報告する
      （止まるべきところで止まらない、すり抜ける、などの C 型のバグの手がかり）
"""
 
import argparse
import csv
from collections import defaultdict, deque
 
 
# ------------------------------------------------------------
# 記録の読み込みと動的依存グラフ
# ------------------------------------------------------------
 
def load_trace(path):
    nodes, deps, readers = [], [], []
    last_def = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uses = [u for u in row["uses"].split(";") if u]
            node = {
                "frame": int(row["frame"]),
                "file": row["file"],
                "line": int(row["line"]),
                "var": row["var"],
                "value": row["value"],                   
                "num": to_float(row["value"]),
                "uses": uses,
            }
            i = len(nodes)
            ds = [last_def[u] for u in uses if u in last_def]
            deps.append(ds)
            readers.append([])
            for j in ds:
                readers[j].append(i)
            last_def[node["var"]] = i
            nodes.append(node)
    return nodes, deps, readers
 
 
def to_float(s):
    try:
        return float(s)
    except ValueError:
        return None
 
 
def site_of(n):
    return (n["var"], n["file"], n["line"])
 
 
def site_name(site):
    var, file, line = site
    return f"{var} ({file}:{line})"
 
 
def find_criterion(nodes, frame, var):
    """指定されたフレーム以下でのvarの最終定義のノード"""
    found = None
    for i, n in enumerate(nodes):
        if n["frame"] > frame:
            break
        if n["var"] == var:
            found = i
    return found
 

def backward_slice(deps, nodes, start, window=None):
    """depsを幅優先探索で辿る、--windowで探索範囲を指定できる"""
    start_frame = nodes[start]["frame"]
    depth = {start: 0}
    queue = deque([start])
    while queue:
        i = queue.popleft()
        for j in deps[i]:
            if j in depth:
                continue
            if window is not None and start_frame - nodes[j]["frame"] > window:
                continue
            depth[j] = depth[i] + 1
            queue.append(j)
    return depth
 
 
# ------------------------------------------------------------
# 縮約のための下準備
# ------------------------------------------------------------
 
def classify_sites(nodes, max_levels):
    """書き込み場所ごとに、離散値（整数で種類が少ない）か連続値かを判定する"""
    values = defaultdict(set)
    for n in nodes:
        values[site_of(n)].add(n["num"])
    discrete = {}
    for site, vs in values.items():
        discrete[site] = (None not in vs
                          and all(float(v).is_integer() for v in vs)
                          and len(vs) <= max_levels)
    return discrete
 
 
def variable_graph(nodes):
    """変数どうしの関係（どちらかがもう一方を uses に持つ）を、無向グラフとして作る"""
    adj = defaultdict(set)
    for n in nodes:
        for u in n["uses"]:
            if u != n["var"]:
                adj[n["var"]].add(u)
                adj[u].add(n["var"])
    return adj
 
 
def related_vars(adj, var, hops):
    seen = {var: 0}
    queue = deque([var])
    while queue:
        v = queue.popleft()
        if seen[v] == hops:
            continue
        for w in adj[v]:
            if w not in seen:
                seen[w] = seen[v] + 1
                queue.append(w)
    return set(seen)
 
 
def find_events(nodes, readers, discrete, ignore_prefixes):
    """離散値の場所で値が変わったノード（＝出来事）を集める。
    誰にも読まれなかった値と、入力（外からの刺激）は除く"""
    last_value = {}
    events = []   # (frame, var, old, new, node index)
    for i, n in enumerate(nodes):
        site = site_of(n)
        if not discrete[site]:
            continue
        old = last_value.get(site)
        last_value[site] = n["num"]
        if old is None or old == n["num"]:
            continue
        if any(n["var"].startswith(p) for p in ignore_prefixes):
            continue
        if not readers[i]:
            continue
        events.append((n["frame"], n["var"], old, n["num"], i))
    return events
 
 
def third_diff(series, k):
    """series[k] における3階差分。足りなければ None"""
    if k < 3:
        return None
    (f0, a), (f1, b), (f2, c), (f3, d) = series[k - 3], series[k - 2], series[k - 1], series[k]
    if not (f1 == f0 + 1 and f2 == f1 + 1 and f3 == f2 + 1):
        return None
    if None in (a, b, c, d):
        return None
    return d - 3 * c + 3 * b - a
 
 
def changed_within(series, k, lag, tol):
    """series[k] から lag フレーム後までのどこかに変化点があるか（出来事の効果の遅れを許す）"""
    for j in range(k, min(k + lag + 1, len(series))):
        d3 = third_diff(series, j)
        if d3 is not None and abs(d3) > tol * max(1.0, abs(series[j][1] or 0.0)):
            return True
    return False
 
 
def site_series(nodes):
    """書き込み場所ごとの (frame, 数値) の列（記録全体）。同じフレームに複数あれば最後の値"""
    by_site = defaultdict(dict)
    for n in nodes:
        by_site[site_of(n)][n["frame"]] = n["num"]
    return {s: sorted(d.items()) for s, d in by_site.items()}
 
 
# ------------------------------------------------------------
# 縮約
# ------------------------------------------------------------
 
def compress(nodes, sliced, depth, discrete, events, adj, args):
    series = site_series(nodes)
    series_index = {s: {f: k for k, (f, _) in enumerate(ser)} for s, ser in series.items()}
 
    by_site = defaultdict(list)
    for i in sliced:
        by_site[site_of(nodes[i])].append(i)
 
    events_by_frame = defaultdict(list)
    for e in events:
        events_by_frame[e[0]].append(e)
 
    units = []
    effectless = []
 
    for site, idxs in by_site.items():
        idxs.sort(key=lambda i: (nodes[i]["frame"], i))
        is_disc = discrete[site]
        rel = related_vars(adj, site[0], args.relate)
 
        current = []
        reason = "start"
 
        def flush(next_reason):
            nonlocal current, reason
            if current:
                units.append(make_unit(nodes, depth, site, current, is_disc, reason))
            current = []
            reason = next_reason
 
        for i in idxs:
            n = nodes[i]
            if not current:
                current = [i]
                continue
            prev = nodes[current[-1]]
            if n["frame"] != prev["frame"] + 1:
                flush("gap")
                current = [i]
                continue
            if is_disc:
                if n["num"] != prev["num"]:
                    flush("value")
                    current = [i]
                else:
                    current.append(i)
                continue
 
            # 連続値：変化点と出来事を調べる
            k = series_index[site].get(n["frame"])
            d3 = third_diff(series[site], k) if k is not None else None
            scale = max(1.0, abs(n["num"] or 0.0))
            is_change = d3 is not None and abs(d3) > args.tol * scale
            evs = [e for e in events_by_frame[n["frame"]] if e[1] in rel and e[1] != site[0]]
 
            if evs and d3 is not None and not changed_within(series[site], k, args.lag, args.tol):
                for e in evs:
                    effectless.append((n["frame"], e, site, d3))
 
            if is_change:
                flush("change")
                current = [i]
            elif evs:
                flush("event:" + ",".join(e[1] for e in evs))
                current = [i]
            else:
                current.append(i)
        flush("end")
 
    return units, effectless
 
 
def make_unit(nodes, depth, site, idxs, is_disc, reason):
    first, last = nodes[idxs[0]], nodes[idxs[-1]]
    return {
        "site": site,
        "start": first["frame"],
        "end": last["frame"],
        "count": len(idxs),
        "first_value": first["value"],
        "last_value": last["value"],
        "discrete": is_disc,
        "depth": min(depth[i] for i in idxs),
        "reason": reason,
        "nodes": idxs,
    }
 
 
def describe(u):
    span = f"frame {u['start']}" if u["start"] == u["end"] else f"frame {u['start']}〜{u['end']}"
    if u["discrete"]:
        val = f"= {u['first_value']}"
    elif u["start"] == u["end"]:
        val = f"= {u['first_value']}"
    else:
        val = f"{u['first_value']} → {u['last_value']}"
    return f"{site_name(u['site']):<34} {span:<16} {val}"
 
 
# ------------------------------------------------------------
# メイン
# ------------------------------------------------------------
 
def main():
    ap = argparse.ArgumentParser(description="時間方向の動的後ろ向きスライスと縮約")
    ap.add_argument("trace")
    ap.add_argument("--frame", type=int, required=True, help="異常を観測したフレーム")
    ap.add_argument("--var", required=True, help="異常を観測した変数")
    ap.add_argument("--window", type=int, default=None, help="遡るフレーム数の上限")
    ap.add_argument("--gap", type=int, default=5, help="古い値の使用とみなすフレーム差")
    ap.add_argument("--tol", type=float, default=1e-3, help="変化点とみなす3階差分の閾値")
    ap.add_argument("--relate", type=int, default=1, help="出来事を関係ありとみなす変数間の距離")
    ap.add_argument("--levels", type=int, default=4, help="離散値とみなす値の種類の上限")
    ap.add_argument("--lag", type=int, default=2, help="出来事から効果が出るまでに許すフレーム数")
    ap.add_argument("--top", type=int, default=20, help="表示する区間の数")
    ap.add_argument("--expect", default=None, help="正解の原因 var:frame（評価用、順位を表示）")
    ap.add_argument("--out", default=None, help="縮約した区間を CSV に書き出すパス")
    args = ap.parse_args()
 
    nodes, deps, readers = load_trace(args.trace)
    start = find_criterion(nodes, args.frame, args.var)
    if start is None:
        print(f"フレーム {args.frame} 以前に {args.var} の書き込みが見つかりません")
        return
 
    depth = backward_slice(deps, nodes, start, args.window)
    sliced = sorted(depth)
 
    discrete = classify_sites(nodes, args.levels)
    adj = variable_graph(nodes)
    events = find_events(nodes, readers, discrete, ignore_prefixes=("input.",))
    units, effectless = compress(nodes, sliced, depth, discrete, events, adj, args)
    units.sort(key=lambda u: (u["depth"], -u["end"]))
 
    # ---- 概要 ----
    s = nodes[start]
    frames = sorted({nodes[i]["frame"] for i in sliced})
    print(f"基準: frame {s['frame']}  {s['var']} = {s['value']}  ({s['file']}:{s['line']})")
    print(f"記録の総数        : ノード {len(nodes)}")
    print(f"スライス          : ノード {len(sliced)}（frame {frames[0]}〜{frames[-1]}）")
    print(f"縮約後の区間の数  : {len(units)}（スライスの {100 * len(units) / len(sliced):.1f}%）")
 
    # ---- 評価用：正解の原因の順位 ----
    if args.expect:
        var, fr = args.expect.split(":")
        fr = int(fr)
        rank = None
        for r, u in enumerate(units, 1):
            if u["site"][0] == var and u["start"] <= fr <= u["end"]:
                rank = r
                break
        if rank is None:
            print(f"正解 {args.expect}: スライスに含まれていません")
        else:
            print(f"正解 {args.expect}: {rank} 番目の区間に含まれています")
 
    # ---- 古い値の使用（A 型の手がかり） ----
    print(f"\n古い値の使用（{args.gap} フレーム以上前の書き込みを使っている依存）:")
    stale = []
    for i in sliced:
        for j in deps[i]:
            if j in depth:
                g = nodes[i]["frame"] - nodes[j]["frame"]
                if g >= args.gap:
                    stale.append((g, i, j))
    if not stale:
        print("  なし")
    for g, i, j in sorted(stale, reverse=True)[:10]:
        a, b = nodes[i], nodes[j]
        print(f"  {g:4d} フレーム前: frame {a['frame']} の {a['var']}（{a['file']}:{a['line']}）が"
              f" frame {b['frame']} の {b['var']} = {b['value']}（{b['file']}:{b['line']}）を使用")
 
    # ---- 効果の無い出来事（C 型の手がかり） ----
    print("\n効果の無い出来事（関係する変数が変わったのに、値が滑らかなまま続いた箇所）:")
    if not effectless:
        print("  なし")
    seen = set()
    for frame, e, site, d3 in sorted(effectless, key=lambda x: -x[0]):
        key = (frame, e[1], site)
        if key in seen:
            continue
        seen.add(key)
        print(f"  frame {frame}: {e[1]} が {fmt(e[2])} → {fmt(e[3])} に変化したが、"
              f"{site_name(site)} は変化点なし（3階差分 {d3:.2e}）")
        if len(seen) >= 10:
            break
 
    # ---- 縮約した区間の一覧 ----
    print(f"\n縮約した区間（基準に近い順・上位 {args.top}）:")
    for u in units[:args.top]:
        print(f"  段数 {u['depth']:3d}  {describe(u)}   [{u['count']} ノード, 区切り: {u['reason']}]")
 
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["depth", "var", "file", "line", "start", "end", "count",
                        "first_value", "last_value", "discrete", "reason"])
            for u in units:
                var, file, line = u["site"]
                w.writerow([u["depth"], var, file, line, u["start"], u["end"], u["count"],
                            u["first_value"], u["last_value"], int(u["discrete"]), u["reason"]])
        print(f"\n縮約した区間を {args.out} に書き出しました")
 
 
def fmt(v):
    return str(int(v)) if v is not None and float(v).is_integer() else str(v)
 
 
if __name__ == "__main__":
    main()