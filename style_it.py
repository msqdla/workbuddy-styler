# -*- coding: utf-8 -*-
"""
命令行用法：
  python3 style_it.py <公众号文章URL> <input.md> [-o out.html] [--png out.png] [--embed] [--title 标题]

示例：
  python3 style_it.py "https://mp.weixin.qq.com/s/xxxx" article.md -o result.html --png result.png
"""
import argparse
import json
import sys
from pathlib import Path

from extractor import extract_theme
from renderer import render

BASE = Path(__file__).parent


def png_from_html(html: str, out: Path, width: int = 750):
    from playwright.sync_api import sync_playwright
    from browser import launch
    tmp = BASE / ".cache" / "_render_tmp.html"
    BASE.joinpath(".cache").mkdir(exist_ok=True)
    tmp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = launch(p)
        try:
            pg = b.new_context(viewport={"width": width, "height": 1200},
                               device_scale_factor=2).new_page()
            pg.goto(tmp.as_uri())
            pg.wait_for_timeout(1500)
            pg.screenshot(path=str(out), full_page=True)
        finally:
            b.close()


def main():
    ap = argparse.ArgumentParser(description="按公众号文章样式排版 Markdown")
    ap.add_argument("url", help="公众号文章地址")
    ap.add_argument("markdown", help="Markdown 文件路径")
    ap.add_argument("-o", "--out", default="output.html", help="输出 HTML 路径")
    ap.add_argument("--png", default="", help="同时导出长图 PNG")
    ap.add_argument("--embed", action="store_true", help="把图片下载并内嵌 base64")
    ap.add_argument("--accent", default="", help="覆盖主题色，如 #c0392b")
    ap.add_argument("--background", default="", help="覆盖背景色")
    ap.add_argument("--font-size", type=float, default=0, help="覆盖正文字号(px)")
    ap.add_argument("--line-height", type=float, default=0, help="覆盖行高(倍数)")
    ap.add_argument("--title", default="", help="文章标题")
    ap.add_argument("--no-cache", action="store_true", help="忽略样式缓存重新抓取")
    args = ap.parse_args()

    md_text = Path(args.markdown).read_text(encoding="utf-8") if args.markdown != "-" else sys.stdin.read()
    print(f"[1/3] 抓取样式: {args.url}")
    theme = extract_theme(args.url, use_cache=not args.no_cache)
    print(f"      标题: {theme.get('meta', {}).get('title', '')[:60]}")
    print(f"      正文: {theme['page']['bodySize']} / {theme['page']['bodyColor']} / 主色 {theme['page']['accent']}")

    tweaks = {}
    if args.accent:
        tweaks["accent"] = args.accent
    if args.background:
        tweaks["background"] = args.background
    if args.font_size:
        tweaks["fontSize"] = args.font_size
    if args.line_height:
        tweaks["lineHeight"] = args.line_height

    print("[2/3] 渲染 Markdown")
    html = render(theme, md_text, tweaks, title=args.title, embed=args.embed)
    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"[3/3] 已输出: {out.resolve()} ({len(html)} 字节)")
    if args.png:
        png_from_html(html, Path(args.png))
        print(f"      长图: {Path(args.png).resolve()}")


if __name__ == "__main__":
    main()
