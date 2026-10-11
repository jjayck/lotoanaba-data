# -*- coding: utf-8 -*-
"""ロト6/ロト7 当選番号を取得・検証して、変化があれば公開リポジトリへ push する(Mac の launchd から実行)。

- 標準ライブラリのみ。取得先は HTTPS 固定・証明書検証あり・サイズ上限あり
- 検証を通らないデータは絶対に書き込まない(異常時は macOS 通知を出して終了コード1)
- 既存行の書き換え・件数減少は拒否(追記のみ許可)
使い方: python3 update_data.py [--dry-run] [--no-push]
"""
import argparse, hashlib, json, os, re, subprocess, sys, urllib.request, ssl
from datetime import datetime, timezone, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SPECS = {
    # name: (取得URL, 本数字の個数, 最大値, ボーナス個数, 等級数)
    "loto6": ("https://loto6.thekyo.jp/data/loto6.csv", 6, 43, 1, 5),
    "loto7": ("https://loto7.thekyo.jp/data/loto7.csv", 7, 37, 2, 6),
}
MAX_BYTES = 2_000_000
MAX_NEW_ROWS = 5          # 1回の更新で増えてよい回数(異常な大量追加を拒否)
JST = timezone(timedelta(hours=9))


def fail(msg):
    print("ERROR:", msg, file=sys.stderr)
    try:
        subprocess.run(["osascript", "-e",
                        'display notification "%s" with title "lotoanaba-data 更新失敗"' % msg.replace('"', "'")[:180]],
                       check=False, timeout=10)
    except Exception:
        pass
    sys.exit(1)


def fetch(url):
    if not url.startswith("https://"):
        raise ValueError("https以外は拒否")
    req = urllib.request.Request(url, headers={"User-Agent": "lotoanaba-data/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("サイズ上限超過")
    return data


def parse(name, raw):
    _, pick, top, nb, ng = SPECS[name]
    need = 2 + pick + nb + ng * 2
    rows, prev_no = [], 0
    lines = [l.strip() for l in raw.decode("cp932").splitlines() if l.strip()]
    for line in lines[1:]:  # 先頭はヘッダ
        f = [x.strip() for x in line.split(",")]
        if len(f) < need:
            raise ValueError("項目数不足: " + line[:60])
        f = f[:need]
        if not re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", f[1]):
            raise ValueError("日付不正: " + line[:60])
        nums = [int(x) for x in f[2:2 + pick]]
        bonus = [int(x) for x in f[2 + pick:2 + pick + nb]]
        if not all(1 <= n <= top for n in nums + bonus) or len(set(nums + bonus)) != pick + nb:
            raise ValueError("数字不正: " + line[:60])
        if not all(re.fullmatch(r"\d+", x) for x in f[2 + pick + nb:]):
            raise ValueError("数値項目不正: " + line[:60])
        no = int(f[0])
        if no != prev_no + 1:
            raise ValueError("回号が連続していません: %d の次が %d" % (prev_no, no))
        prev_no = no
        rows.append(",".join(f))
    if len(rows) < 100:
        raise ValueError("件数が少なすぎます")
    return rows


def key_part(name, row):
    _, pick, _, nb, _ = SPECS[name]
    return row.split(",")[:2 + pick + nb]  # 回号・日付・本数字・ボーナス


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="書き込まず検証だけ")
    ap.add_argument("--no-push", action="store_true", help="書き込みまでで push しない")
    a = ap.parse_args()

    meta, changed = {}, False
    for name, spec in SPECS.items():
        try:
            new = parse(name, fetch(spec[0]))
        except Exception as e:
            fail("%s 取得/検証: %s" % (name, e))
        path = os.path.join(ROOT, name + ".csv")
        old = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                old = [l for l in f.read().splitlines() if l]
        if old:
            if len(new) < len(old):
                fail("%s 件数が減少(%d→%d)" % (name, len(old), len(new)))
            if len(new) - len(old) > MAX_NEW_ROWS:
                fail("%s 追加が多すぎ(+%d)。手動確認してください" % (name, len(new) - len(old)))
            for o, n in zip(old, new):
                if key_part(name, o) != key_part(name, n):
                    fail("%s 既存行が変化: 第%s回" % (name, o.split(",")[0]))
        body = ("\n".join(new) + "\n").encode("utf-8")
        if not old or body != ("\n".join(old) + "\n").encode("utf-8"):
            changed = True
            print("%s: %d → %d 回" % (name, len(old), len(new)))
            if not a.dry_run:
                tmp = path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(body)
                os.replace(tmp, path)
        else:
            print("%s: 変更なし(%d回)" % (name, len(new)))
        meta[name] = {"count": len(new), "latest": int(new[-1].split(",")[0]),
                      "sha256": hashlib.sha256(body).hexdigest()}

    if not changed or a.dry_run:
        print("終了(変更なし or dry-run)")
        return
    meta["updated"] = datetime.now(JST).isoformat(timespec="seconds")
    with open(os.path.join(ROOT, "meta.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
        f.write("\n")
    if a.no_push:
        return
    try:
        run = lambda *c: subprocess.run(["git", "-C", ROOT, *c], check=True, timeout=120)
        run("add", "loto6.csv", "loto7.csv", "meta.json")
        run("commit", "-m", "data: 当選番号を更新 (loto6=%d, loto7=%d)" % (meta["loto6"]["latest"], meta["loto7"]["latest"]))
        run("push", "origin", "main")
    except Exception as e:
        fail("git push 失敗: %s" % e)
    print("push 完了")


if __name__ == "__main__":
    main()
