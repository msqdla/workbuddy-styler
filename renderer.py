# -*- coding: utf-8 -*-
"""
把 Markdown 渲染成「指定公众号文章同款排版」的 HTML。
"""
import re
import base64
import mimetypes
from pathlib import Path

import markdown
from bs4 import BeautifulSoup, NavigableString
import requests

MD_EXT = ["extra", "sane_lists", "toc", "attr_list"]

KILL_PROPS = {"position", "top", "left", "right", "bottom", "z-index", "width", "height"}


def kebab(k: str) -> str:
    return re.sub(r"([A-Z])", r"-\1", k).lower()


def style_str(d: dict, drop=()) -> str:
    if not d:
        return ""
    out = []
    for k, v in d.items():
        if not v or k in drop or k in KILL_PROPS:
            continue
        if isinstance(v, (int, float)):
            v = f"{v}px"
        v = str(v).replace('"', "'")  # 防止 font-family 的双引号破坏 style 属性
        out.append(f"{kebab(k)}:{v}")
    return ";".join(out)


def merge(base: dict, *others) -> dict:
    r = dict(base or {})
    for o in others:
        if o:
            r.update(o)
    return r


def px(v, default=0.0) -> float:
    try:
        return float(re.sub(r"[^\d.\-]", "", str(v or "")) or default)
    except ValueError:
        return default


# ---------------------------------------------------------------- 默认兜底样式
def default_styles(theme: dict) -> dict:
    page = theme.get("page", {})
    accent = page.get("accent") or "#07c160"
    body = theme.get("styles", {}).get("p") or {}
    size = px(page.get("bodySize") or body.get("fontSize"), 16)
    color = page.get("bodyColor") or body.get("color") or "#333"
    fam = page.get("fontFamily") or body.get("fontFamily") or ""
    base = {
        "fontSize": f"{size}px",
        "color": color,
        "lineHeight": body.get("lineHeight") or f"{round(size * 1.75, 2)}px",
        "letterSpacing": body.get("letterSpacing") or "0.5px",
        "textAlign": body.get("textAlign") or "justify",
        "fontFamily": fam,
        "marginTop": "0px",
        "marginBottom": f"{round(size * 1.2, 2)}px",
    }
    def head(ratio, color_=None, extra=None):
        d = dict(base)
        d.update({
            "fontSize": f"{round(size * ratio, 2)}px",
            "fontWeight": "bold",
            "color": color_ or accent,
            "lineHeight": f"{round(size * ratio * 1.35, 2)}px",
            "textAlign": body.get("textAlign") or "left",
            "marginTop": f"{round(size * 1.4, 2)}px",
            "marginBottom": f"{round(size * 0.7, 2)}px",
        })
        if extra:
            d.update(extra)
        return {"style": d, "wrapper": {}}
    return {
        "p": base,
        "wrapper": {},
        "h1": head(1.5),
        "h2": head(1.3),
        "h3": head(1.15),
        "blockquote": {
            "borderLeftWidth": "3px", "borderLeftStyle": "solid", "borderLeftColor": accent,
            "backgroundColor": "rgba(0,0,0,0)", "paddingTop": "4px", "paddingBottom": "4px",
            "paddingLeft": "12px", "paddingRight": "8px",
            "marginTop": f"{round(size * 0.8, 2)}px", "marginBottom": f"{round(size * 0.8, 2)}px",
            "color": "rgba(0,0,0,0.65)", "fontSize": f"{max(size - 1, 12)}px",
            "lineHeight": base["lineHeight"], "borderRadius": "0px",
        },
        "li": merge(base, {"marginTop": "0px", "marginBottom": f"{round(size * 0.5, 2)}px",
                           "paddingLeft": "0px", "textAlign": body.get("textAlign") or "left"}),
        "code": {"fontSize": f"{max(size - 2, 12)}px", "color": "#c7254e",
                 "backgroundColor": "rgba(27,31,35,0.06)", "padding": "2px 5px",
                 "borderRadius": "3px", "fontFamily": "Menlo, Consolas, monospace"},
        "pre": {"backgroundColor": "rgba(27,31,35,0.05)", "padding": "14px 16px",
                "borderRadius": "6px", "fontSize": f"{max(size - 2, 12)}px",
                "lineHeight": f"{round(size * 1.6, 2)}px", "color": "#24292e",
                "marginTop": f"{round(size * 0.8, 2)}px", "marginBottom": f"{round(size * 0.8, 2)}px",
                "fontFamily": "Menlo, Consolas, monospace"},
        "hr": {"borderTopWidth": "1px", "borderTopStyle": "solid", "borderTopColor": "#e5e5e5",
               "borderBottomWidth": "0px", "borderBottomStyle": "none", "height": "1px",
               "backgroundColor": "rgba(0,0,0,0)", "marginTop": f"{round(size * 1.5, 2)}px",
               "marginBottom": f"{round(size * 1.5, 2)}px"},
        "img": {"maxWidth": "100%", "display": "block", "margin": "0 auto", "borderRadius": "4px"},
        "a": {"color": accent, "textDecoration": "none"},
        "strong": {"color": accent, "fontWeight": "bold"},
        "em": {"fontStyle": "italic"},
        "table": {"width": "100%", "borderCollapse": "collapse", "fontSize": f"{max(size - 1, 12)}px",
                  "marginTop": f"{round(size * 0.8, 2)}px", "marginBottom": f"{round(size * 0.8, 2)}px"},
        "th": {"backgroundColor": "rgba(0,0,0,0.04)", "padding": "8px 10px",
               "borderTopWidth": "1px", "borderTopStyle": "solid", "borderTopColor": "#e5e5e5",
               "fontWeight": "bold", "textAlign": "left"},
        "td": {"padding": "8px 10px", "borderTopWidth": "1px", "borderTopStyle": "solid",
               "borderTopColor": "#eeeeee"},
        "figcaption": {"fontSize": f"{max(size - 3, 11)}px", "color": "rgba(0,0,0,0.45)",
                       "textAlign": "center", "marginTop": "6px"},
    }


def resolve_styles(theme: dict, tweaks: dict = None) -> dict:
    """合并原文样式 + 兜底 + 用户微调"""
    s = default_styles(theme)
    got = theme.get("styles", {}) or {}
    for k, v in got.items():
        if v:
            s[k] = v
    # 引用样式合法性检查：无左边框且无有效背景 → 丢弃走兜底
    q = s.get("blockquote") or {}
    bl = px(q.get("borderLeftWidth"))
    bg = (q.get("backgroundColor") or "").lower()
    m = re.search(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", bg)
    is_white = bool(m and int(m.group(1)) > 245 and int(m.group(2)) > 245 and int(m.group(3)) > 245)
    if bl <= 0 and (not bg or bg in ("rgba(0, 0, 0, 0)", "transparent") or is_white):
        s["blockquote"] = default_styles(theme)["blockquote"]
    # 清理负 margin（原文的排版技巧，套用到新内容会造成重叠）
    for key in ("blockquote", "li", "code", "pre", "hr"):
        d = s.get(key)
        if not d:
            continue
        for mk in ("marginTop", "marginBottom"):
            if px(d.get(mk)) < 0:
                d[mk] = "0px"
    for hk in ("h1", "h2", "h3"):
        if s.get(hk):
            for mk in ("marginTop", "marginBottom"):
                if px(s[hk]["style"].get(mk)) < 0:
                    s[hk]["style"][mk] = "0px"
                if px(s[hk].get("wrapper", {}).get(mk)) < 0:
                    s[hk]["wrapper"][mk] = "0px"
    # 标题补齐：原文没抓到的层级用已抓到的等比缩放
    heads = {k: s[k] for k in ("h1", "h2", "h3") if s.get(k)}
    base_p = s["p"]
    if "h1" not in heads:
        s["h1"] = {"style": merge(base_p, {"fontSize": f"{px(base_p.get('fontSize'), 16) * 1.5}px",
                                           "fontWeight": "bold", "color": s["a"]["color"]}), "wrapper": {}}
    if "h2" not in heads:
        r = s["h1"]["style"]
        s["h2"] = {"style": merge(r, {"fontSize": f"{px(r.get('fontSize'), 24) * 0.87}px"}), "wrapper": {}}
    if "h3" not in heads:
        r = s["h2"]["style"]
        s["h3"] = {"style": merge(r, {"fontSize": f"{px(r.get('fontSize'), 20) * 0.88}px"}), "wrapper": {}}

    tw = tweaks or {}
    accent = tw.get("accent")
    if accent:
        s["a"]["color"] = accent
        s["strong"]["color"] = accent
        for k in ("h1", "h2", "h3"):
            if s.get(k) and s[k]["style"].get("color"):
                s[k]["style"]["color"] = accent
        if s.get("blockquote"):
            if s["blockquote"].get("borderLeftWidth") and px(s["blockquote"].get("borderLeftWidth")) > 0:
                s["blockquote"]["borderLeftColor"] = accent
    if tw.get("fontSize"):
        ratio = float(tw["fontSize"]) / px(base_p.get("fontSize"), 16)
        for k in ("h1", "h2", "h3"):
            if s.get(k):
                s[k]["style"]["fontSize"] = f"{px(s[k]['style'].get('fontSize'), 20) * ratio}px"
        s["p"]["fontSize"] = f"{float(tw['fontSize'])}px"
    if tw.get("lineHeight"):
        s["p"]["lineHeight"] = f"{float(tw['lineHeight'])}"
    if tw.get("letterSpacing"):
        s["p"]["letterSpacing"] = f"{float(tw['letterSpacing'])}px"
    if tw.get("align"):
        s["p"]["textAlign"] = tw["align"]
    if tw.get("indent"):
        s["p"]["textIndent"] = f"{float(tw['indent'])}em"
    return s


# ---------------------------------------------------------------- Markdown 渲染
def md_to_html(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=MD_EXT, output_format="html")


def embed_images(soup: BeautifulSoup, timeout=12):
    """把外链图片下载并内嵌为 base64，保证离线打开/粘贴都不丢图"""
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src or src.startswith("data:"):
            continue
        try:
            if src.startswith("http"):
                r = requests.get(src, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
                data, ctype = r.content, r.headers.get("Content-Type", "")
            else:
                p = Path(src)
                if not p.exists():
                    continue
                data = p.read_bytes()
                ctype = mimetypes.guess_type(src)[0] or "image/png"
            if not data:
                continue
            img["src"] = f"data:{ctype or 'image/png'};base64," + base64.b64encode(data).decode()
        except Exception:
            pass
        st = img.get("style", "")
        img["style"] = st + (";" if st else "") + "max-width:100%;height:auto"


def apply_styles(html: str, styles: dict, embed: bool = False) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if embed:
        embed_images(soup)

    p_drop = ("marginTop", "marginBottom") if styles.get("wrapper") else ()
    img_s = style_str(styles.get("img", {}))
    code_s = style_str(styles.get("code", {}))
    pre_s = style_str(styles.get("pre", {}))
    a_s = style_str(styles.get("a", {}))
    strong_s = style_str(styles.get("strong", {}))
    em_s = style_str(styles.get("em", {}))
    li_s = style_str(styles.get("li", {}))
    quote_s = style_str(styles.get("blockquote", {}))
    hr_s = style_str(styles.get("hr", {}))
    wrap_s = style_str(styles.get("wrapper", {}))
    table_s = style_str(styles.get("table", {}))
    th_s = style_str(styles.get("th", {}))
    td_s = style_str(styles.get("td", {}))

    def wrap(el, style):
        if not style:
            return el
        sec = soup.new_tag("section")
        sec["style"] = style
        el.insert_before(sec)
        sec.append(el.extract())
        return sec

    for el in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
                             "ul", "ol", "li", "pre", "code", "img", "hr", "a",
                             "strong", "em", "table", "th", "td"]):
        name = el.name
        if name == "p":
            # 空段落（markdown 里的分隔）跳过
            if not el.get_text(strip=True) and not el.find("img"):
                continue
            el["style"] = style_str(styles["p"], drop=p_drop)
            wrap(el, wrap_s)
        elif name in ("h1", "h2", "h3"):
            st = styles.get(name, {})
            el["style"] = style_str(st.get("style", {}))
            wrap(el, style_str(st.get("wrapper", {})))
        elif name in ("h4", "h5", "h6"):
            st = styles.get("h3", {})
            el["style"] = style_str(st.get("style", {}))
            wrap(el, style_str(st.get("wrapper", {})))
        elif name == "blockquote":
            el["style"] = quote_s
            for sub in el.find_all("p"):
                sub["style"] = style_str(styles["p"], drop=("marginTop", "marginBottom",
                                                            "textIndent", "textAlign"))
        elif name == "li":
            el["style"] = li_s
        elif name in ("ul", "ol"):
            el["style"] = "padding-left:1.6em;margin:0.6em 0"
        elif name == "pre":
            el["style"] = pre_s
            for c in el.find_all("code"):
                c["style"] = "background:transparent;padding:0"
        elif name == "code":
            if el.parent and el.parent.name == "pre":
                continue
            el["style"] = code_s
        elif name == "img":
            el["style"] = img_s + ";height:auto"
        elif name == "hr":
            el["style"] = hr_s
        elif name == "a":
            el["style"] = a_s
        elif name == "strong":
            if el.find_parent(["h1", "h2", "h3", "h4", "h5", "h6"]):
                continue
            el["style"] = strong_s
        elif name == "em":
            el["style"] = em_s
        elif name == "table":
            el["style"] = table_s
        elif name == "th":
            el["style"] = th_s
        elif name == "td":
            el["style"] = td_s

    # 孤立文本节点（markdown 未包裹的内容）包进 <p>
    for node in list(soup.contents):
        if isinstance(node, NavigableString) and node.strip():
            p = soup.new_tag("p")
            p["style"] = style_str(styles["p"], drop=p_drop)
            p.string = str(node)
            node.replace_with(p)
    return str(soup)


PAGE_CSS = """
.wx-wrap{max-width:{maxw}px;margin:0 auto;padding:0}
#js_content, #js_content *{visibility:visible !important;-webkit-text-size-adjust:100%}
#js_content img{max-width:100% !important;height:auto !important}
#js_content pre{overflow-x:auto;white-space:pre-wrap;word-break:break-word}
#js_content table{width:100%;border-collapse:collapse}
@media (max-width:768px){
  .wx-wrap{padding:0 14px}
}
"""


def render(theme: dict, md_text: str, tweaks: dict = None, title: str = "",
           embed: bool = False, mode: str = "full", max_width: int = 677) -> str:
    styles = resolve_styles(theme, tweaks)
    body = apply_styles(md_to_html(md_text), styles, embed=embed)
    page = theme.get("page", {})
    accent = (tweaks or {}).get("accent") or page.get("accent") or "#07c160"
    bg = (tweaks or {}).get("background") or page.get("background") or "#ffffff"
    if bg in ("rgba(0, 0, 0, 0)", "transparent"):
        bg = "#ffffff"
    container = theme.get("container", {})
    cls = container.get("className", "")
    cont_style = style_str(container.get("style", {}),
                           drop=("maxWidth", "paddingLeft", "paddingRight", "fontSize"))
    raw_css = theme.get("rawCss", "") or ""
    if mode == "fragment":
        return f'<div id="js_content" class="{cls}" style="{cont_style}">{body}</div>'

    t = title or theme.get("meta", {}).get("title") or "生成文章"
    css = PAGE_CSS.replace("{maxw}", str(max_width))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{t}</title>
<style>
{raw_css}
{css}
</style>
</head>
<body style="margin:0;padding:0;background:{bg};">
<div class="wx-wrap">
<div id="js_content" class="{cls}" style="{cont_style};accent-color:{accent}">
{body}
</div>
</div>
</body>
</html>"""
