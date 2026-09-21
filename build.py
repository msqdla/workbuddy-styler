# -*- coding: utf-8 -*-
"""
批量生成：按 content/config.json 的配置，把多篇 Markdown 套用指定公众号样式输出成品。

  python3 build.py                          # 按 content/config.json 生成到 output/
  python3 build.py --url <链接> --md a.md   # 单篇临时生成
"""
import argparse
import json
from pathlib import Path

from extractor import extract_theme
from renderer import render
from style_it import png_from_html

BASE = Path(__file__).parent
CONFIG = BASE / "content" / "config.json"
INDEX_CSS = """
body{margin:0;background:#f4f6f8;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#1f2329}
.wrap{max-width:760px;margin:0 auto;padding:40px 20px}
h1{font-size:22px;margin:0 0 6px}
.sub{color:#86909c;font-size:13px;margin-bottom:24px}
.card{background:#fff;border:1px solid #e5e6eb;border-radius:12px;padding:16px 18px;margin-bottom:14px;display:flex;align-items:center;gap:14px}
.card .t{font-size:15px;font-weight:600}
.card .m{font-size:12px;color:#86909c;margin-top:4px}
.card a{margin-left:auto;text-decoration:none;background:#07c160;color:#fff;padding:7px 14px;border-radius:8px;font-size:13px;white-space:nowrap}
.card a.png{background:#165dff}
"""


def slug(name: str) -> str:
    keep = "".join(c for c in name if c not in '\\/:*?"<>|').strip()
    return keep or "article"


def build_one(theme, url, md_path: Path, title: str, out_dir: Path, with_png: bool, width: int):
    md_text = md_path.read_text(encoding="utf-8")
    title = title or md_path.stem
    html = render(theme, md_text, title=title)
    stem = slug(md_path.stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    hp = out_dir / f"{stem}.html"
    hp.write_text(html, encoding="utf-8")
    item = {"title": title, "html": hp.name, "png": "", "source": md_path.name, "url": url}
    if with_png:
        pp = out_dir / f"{stem}.png"
        try:
            png_from_html(html, pp, width=width)
            item["png"] = pp.name
        except Exception as e:  # 长图失败不影响 HTML 成品
            item["png"] = ""
            print(f"  [warn] 长图导出失败：{str(e)[:120]}")
    print(f"  ✅ {title} → {hp.name} ({len(html)} 字节)")
    return item


def write_index(items, out_dir: Path, site_title: str):
    cards = []
    for it in items:
        links = f'<a href="{it["html"]}" target="_blank">打开 HTML</a>'
        if it["png"]:
            links += f' <a class="png" href="{it["png"]}" target="_blank">长图</a>'
        cards.append(
            f'<div class="card"><div><div class="t">{it["title"]}</div>'
            f'<div class="m">源文件 {it["source"]} · 样式来源 {it["url"][:60]}…</div></div>{links}</div>'
        )
    page = (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{site_title}</title><style>{INDEX_CSS}</style></head><body><div class="wrap">'
            f'<h1>{site_title}</h1><div class="sub">共 {len(items)} 篇 · 由 GitHub Actions 自动生成</div>'
            + "".join(cards) + "</div></body></html>")
    (out_dir / "index.html").write_text(page, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="批量套用公众号样式生成成品")
    ap.add_argument("--config", default=str(CONFIG), help="配置文件路径")
    ap.add_argument("--url", default="", help="覆盖样式来源链接")
    ap.add_argument("--md", default="", help="单篇 Markdown 路径（覆盖配置）")
    ap.add_argument("--title", default="", help="标题")
    ap.add_argument("--out", default=str(BASE / "output"), help="输出目录")
    ap.add_argument("--png", action="store_true", help="同时导出长图")
    ap.add_argument("--width", type=int, default=750, help="长图宽度")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = {}
    cfg_path = Path(args.config)
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    url = args.url or cfg.get("style_url", "")
    if not url:
        raise SystemExit("请在 content/config.json 中填写 style_url，或用 --url 指定公众号文章链接")

    site_title = cfg.get("site_title", "公众号排版成品")
    print(f"[1/3] 抓取样式：{url}")
    theme = extract_theme(url)
    print(f"      正文 {theme['page']['bodySize']} / 主色 {theme['page']['accent']}")

    print("[2/3] 生成文章")
    items = []
    if args.md:
        items.append(build_one(theme, url, Path(args.md), args.title, out_dir, args.png, args.width))
    else:
        articles = cfg.get("articles") or []
        if not articles:
            raise SystemExit("content/config.json 里没有配置 articles，或用 --md 指定单篇")
        for a in articles:
            md_path = Path(a["md"])
            if not md_path.is_absolute():
                md_path = cfg_path.parent / md_path
            items.append(build_one(theme, url, md_path, a.get("title", ""), out_dir,
                                   a.get("png", args.png), args.width))

    print("[3/3] 生成索引页")
    write_index(items, out_dir, site_title)
    print(f"完成 → {out_dir.resolve()}（{len(items)} 篇）")


if __name__ == "__main__":
    main()
