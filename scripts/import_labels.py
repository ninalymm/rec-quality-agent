"""把人工标注导入 data/labels_main.csv。

两个来源，自动选择：
1. ~/Documents/labels_main.numbers（Numbers 直接保存的文件）
2. data/fill_main.txt（纯文本，qid<TAB>分数）

用法：python -m scripts.import_labels
"""
import csv
import pathlib

from app import config

NUMBERS = pathlib.Path.home() / "Documents" / "labels_main.numbers"
TARGET = config.DATA_DIR / "labels_main.csv"


def _clean(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(v)
    return str(v).strip()


def from_numbers():
    from numbers_parser import Document
    doc = Document(str(NUMBERS))
    rows = doc.sheets[0].tables[0].rows(values_only=True)
    out = {}
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        out[str(r[0])] = {"score": _clean(r[13]), "note": _clean(r[14])}
    return out


def from_text():
    out = {}
    for line in open(config.DATA_DIR / "fill_main.txt", encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            out[parts[0].strip()] = {"score": parts[1].strip(), "note": ""}
    return out


def main():
    if NUMBERS.exists():
        src, data = "Numbers", from_numbers()
    else:
        src, data = "fill_main.txt", from_text()

    rows = list(csv.DictReader(open(TARGET, encoding="utf-8-sig")))
    filled = 0
    for r in rows:
        d = data.get(r["qid"])
        if not d:
            continue
        if d["score"] in ("0", "1", "2"):
            r["可解释性(0/1/2)"] = d["score"]
            filled += 1
        if d["note"]:
            r["备注"] = d["note"]

    with open(TARGET, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("来源 %s：导入 %d 条有效分数 / 共 %d 条" % (src, filled, len(rows)))


if __name__ == "__main__":
    main()
