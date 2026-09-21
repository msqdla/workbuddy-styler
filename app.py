# -*- coding: utf-8 -*-
"""
公众号样式排版工具 - 本地网页服务
启动:  python3 app.py   →  http://localhost:8777
"""
import io
import uuid

from flask import Flask, request, jsonify, send_file, send_from_directory

from extractor import extract_theme
from renderer import render
from style_it import png_from_html

app = Flask(__name__, static_folder="static", static_url_path="/static")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/fetch")
def api_fetch():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    refresh = bool(data.get("refresh"))
    if not url:
        return jsonify(ok=False, error="请输入公众号文章链接"), 400
    if "mp.weixin.qq.com" not in url:
        return jsonify(ok=False, error="目前只支持 mp.weixin.qq.com 的文章链接"), 400
    try:
        theme = extract_theme(url, use_cache=not refresh)
    except Exception as e:
        return jsonify(ok=False, error=f"抓取失败：{str(e)[:300]}"), 502
    page = theme.get("page", {})
    return jsonify(
        ok=True,
        theme=theme,
        preview=theme.pop("preview", ""),
        info={
            "title": theme.get("meta", {}).get("title", ""),
            "account": theme.get("meta", {}).get("account", ""),
            "bodySize": page.get("bodySize", ""),
            "bodyColor": page.get("bodyColor", ""),
            "accent": page.get("accent", ""),
            "background": page.get("background", ""),
            "cssSize": len(theme.get("rawCss", "")),
        },
    )


@app.post("/api/render")
def api_render():
    data = request.get_json(force=True)
    theme = data.get("theme")
    md_text = data.get("markdown") or ""
    if not theme or not md_text.strip():
        return jsonify(ok=False, error="缺少样式或 Markdown 内容"), 400
    try:
        html = render(
            theme, md_text,
            tweaks=data.get("tweaks") or {},
            title=data.get("title") or "",
            embed=bool(data.get("embed")),
            mode=data.get("mode", "full"),
        )
        frag = render(theme, md_text, tweaks=data.get("tweaks") or {},
                      title=data.get("title") or "", mode="fragment")
        return jsonify(ok=True, html=html, fragment=frag)
    except Exception as e:
        return jsonify(ok=False, error=f"渲染失败：{str(e)[:300]}"), 500


@app.post("/api/png")
def api_png():
    data = request.get_json(force=True)
    html = data.get("html") or ""
    if not html:
        return jsonify(ok=False, error="请先生成内容"), 400
    width = int(data.get("width") or 750)
    name = f"{uuid.uuid4().hex}.png"
    out = app.static_folder / name if hasattr(app.static_folder, "__truediv__") else None
    import pathlib
    out = pathlib.Path(app.static_folder) / name
    try:
        png_from_html(html, out, width=width)
        return send_file(out, mimetype="image/png", as_attachment=True,
                         download_name="公众号排版长图.png")
    finally:
        import threading
        threading.Timer(120, lambda: out.unlink(missing_ok=True)).start()


if __name__ == "__main__":
    print("\n  公众号样式排版工具已启动 →  http://localhost:8777\n")
    app.run(host="0.0.0.0", port=8777, debug=False)
