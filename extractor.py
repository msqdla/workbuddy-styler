# -*- coding: utf-8 -*-
"""
从微信公众号文章 URL 中提取排版样式（字体 / 颜色 / 间距 / 标题 / 引用 / 列表 ...）
返回一个可复用的 theme(JSON) 字典。
"""
import re
import json
import hashlib
from pathlib import Path

from playwright.sync_api import sync_playwright

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

EXTRACT_JS = r"""
() => {
  const PROPS = ['fontSize','color','lineHeight','letterSpacing','wordSpacing','textAlign',
    'fontWeight','fontFamily','fontStyle','textDecorationLine','textIndent',
    'marginTop','marginBottom','marginLeft','marginRight',
    'paddingTop','paddingBottom','paddingLeft','paddingRight',
    'backgroundColor','backgroundImage','borderRadius','boxShadow',
    'borderTopWidth','borderTopStyle','borderTopColor',
    'borderRightWidth','borderRightStyle','borderRightColor',
    'borderBottomWidth','borderBottomStyle','borderBottomColor',
    'borderLeftWidth','borderLeftStyle','borderLeftColor',
    'display','maxWidth','opacity','whiteSpace','minHeight','height'];

  const snap = (el) => {
    const cs = getComputedStyle(el);
    const o = {};
    for (const p of PROPS) { const v = cs[p]; if (v) o[p] = v; }
    return o;
  };
  const txt = (el) => (el.innerText || '').trim();
  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 || r.height > 0 || (el.innerText || '').trim().length > 0;
  };
  const isGrey = (c) => {
    const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(c || '');
    if (!m) return true;
    const [r, g, b] = [+m[1], +m[2], +m[3]];
    return Math.max(r, g, b) - Math.min(r, g, b) < 18;
  };

  const root = document.querySelector('#js_content')
            || document.querySelector('.rich_media_content')
            || document.querySelector('#img-content')
            || document.querySelector('article')
            || document.body;

  // ---------- 1. 采样所有「带直接文本的块」 ----------
  const blocks = [];
  root.querySelectorAll('*').forEach((el) => {
    if (!visible(el)) return;
    const direct = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3)
      .map(n => n.textContent.trim()).join('');
    if (direct.length >= 6) blocks.push(el);
  });
  if (!blocks.length) {
    root.querySelectorAll('p, section, div').forEach(el => { if (txt(el).length >= 6) blocks.push(el); });
  }

  // ---------- 2. 正文字号 / 正文颜色（按文本量加权取众数） ----------
  const weighted = (fn, filter) => {
    const w = {};
    blocks.forEach(el => {
      if (filter && !filter(el)) return;
      const k = fn(el);
      if (!k) return;
      w[k] = (w[k] || 0) + Math.min(txt(el).length, 300);
    });
    const arr = Object.entries(w).sort((a, b) => b[1] - a[1]);
    return arr.length ? arr[0][0] : null;
  };
  const bodySize = weighted(el => getComputedStyle(el).fontSize) || '16px';
  const bodySizeNum = parseFloat(bodySize);
  const isBody = (el) => Math.abs(parseFloat(getComputedStyle(el).fontSize) - bodySizeNum) < 0.6;
  const bodyColor = weighted(el => getComputedStyle(el).color, isBody) || '#333333';

  // ---------- 3. 段落样式（正文块的样式签名取众数） ----------
  const P_KEYS = ['fontSize','color','lineHeight','letterSpacing','textAlign','textIndent',
                  'fontFamily','marginTop','marginBottom','paddingLeft','paddingRight'];
  const sigCount = {};
  blocks.filter(isBody).forEach(el => {
    const s = snap(el);
    const sig = JSON.stringify(P_KEYS.map(k => s[k] || ''));
    sigCount[sig] = sigCount[sig] || { n: 0, s };
    sigCount[sig].n += 1;
  });
  let paraStyle = {};
  const sigArr = Object.values(sigCount).sort((a, b) => b.n - a.n);
  if (sigArr.length) {
    const s = sigArr[0].s;
    P_KEYS.forEach(k => { if (s[k]) paraStyle[k] = s[k]; });
  }
  // 段落外层包裹（公众号多为 <section> 包 <p>）
  const wrapCount = {};
  blocks.filter(isBody).forEach(el => {
    const p = el.parentElement;
    if (!p || p === root) return;
    const s = snap(p);
    const sig = JSON.stringify(['marginTop','marginBottom','paddingTop','paddingBottom',
      'paddingLeft','paddingRight','backgroundColor','borderRadius','textAlign','lineHeight']
      .map(k => s[k] || ''));
    wrapCount[sig] = wrapCount[sig] || { n: 0, s };
    wrapCount[sig].n += 1;
  });
  let wrapStyle = {};
  const wArr = Object.values(wrapCount).sort((a, b) => b.n - a.n);
  if (wArr.length) {
    const s = wArr[0].s;
    const hasDecoration = s.backgroundColor && s.backgroundColor !== 'rgba(0, 0, 0, 0)';
    const hasSpacing = (s.marginTop && parseFloat(s.marginTop) > 0) || (s.paddingTop && parseFloat(s.paddingTop) > 0);
    if (hasDecoration || hasSpacing) {
      ['marginTop','marginBottom','paddingTop','paddingBottom','paddingLeft','paddingRight',
       'backgroundColor','borderRadius','textAlign','lineHeight'].forEach(k => { if (s[k]) wrapStyle[k] = s[k]; });
    }
  }

  // ---------- 4. 标题样式（按字号聚类，最多 3 级） ----------
  const headCand = {};
  // 标题候选：字号更大，或同字号但加粗/带装饰
  blocks.forEach(el => {
    const cs = getComputedStyle(el);
    const fs = parseFloat(cs.fontSize);
    const bold = parseInt(cs.fontWeight, 10) >= 600;
    if (fs <= bodySizeNum + 0.6 && !bold) return;
    const bucket = Math.round(fs * 2) / 2;
    if (!isFinite(bucket)) return;
    const s = snap(el);
    const parent = el.parentElement;
    const ps = parent && parent !== root ? snap(parent) : {};
    const hasDeco = (o) => (o.backgroundColor && o.backgroundColor !== 'rgba(0, 0, 0, 0)')
                        || (parseFloat(o.borderLeftWidth || 0) > 0)
                        || (o.backgroundImage && o.backgroundImage !== 'none');
    const score = (bold ? 3 : 0)
                + (fs - bodySizeNum) * 2
                + (hasDeco(s) ? 4 : 0) + (hasDeco(ps) ? 4 : 0)
                + Math.min(txt(el).length, 40) * 0.05;
    headCand[bucket] = headCand[bucket] || { n: 0, best: null, bestScore: -1 };
    headCand[bucket].n += 1;
    if (score > headCand[bucket].bestScore) {
      headCand[bucket].bestScore = score;
      headCand[bucket].best = { inner: s, wrapper: ps };
    }
  });
  const H_KEYS = ['fontSize','color','fontWeight','lineHeight','letterSpacing','textAlign',
                  'marginTop','marginBottom','paddingTop','paddingBottom','paddingLeft','paddingRight',
                  'backgroundColor','borderRadius','fontFamily'];
  const W_KEYS = ['backgroundColor','borderLeftWidth','borderLeftStyle','borderLeftColor','borderRadius',
                  'paddingTop','paddingBottom','paddingLeft','paddingRight','marginTop','marginBottom','textAlign'];
  const pick = (o, keys) => { const r = {}; keys.forEach(k => { if (o && o[k]) r[k] = o[k]; }); return r; };
  const levels = Object.keys(headCand).map(Number).sort((a, b) => b - a);
  const heads = {};
  const chosen = [];
  levels.forEach(lv => {
    if (chosen.length >= 3) return;
    if (chosen.some(c => Math.abs(c - lv) < 1.5)) return;
    chosen.push(lv);
  });
  chosen.forEach((lv, i) => {
    const b = headCand[lv] && headCand[lv].best;
    if (!b) return;
    heads['h' + (i + 1)] = {
      style: pick(b.inner, H_KEYS),
      wrapper: pick(b.wrapper, W_KEYS),
    };
  });

  // ---------- 5. 引用样式 ----------
  let quote = null;
  const qCand = [];
  root.querySelectorAll('*').forEach(el => {
    if (!visible(el)) return;
    const cs = getComputedStyle(el);
    const hasLeftBorder = parseFloat(cs.borderLeftWidth) > 0 && cs.borderLeftStyle !== 'none';
    const bg = cs.backgroundColor || 'rgba(0, 0, 0, 0)';
    const bgOk = (m) => !m || !(m[1] > 245 && m[2] > 245 && m[3] > 245);
    const hasBg = cs.backgroundColor && bg !== 'rgba(0, 0, 0, 0)'
                  && bgOk(/rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(bg));
    const h = el.getBoundingClientRect().height;
    if ((hasLeftBorder || hasBg) && txt(el).length > 8 && h < 900) {
      qCand.push({ el, cs, score: (hasLeftBorder ? 5 : 0) + (hasBg ? 1 : 0) });
    }
  });
  qCand.sort((a, b) => b.score - a.score);
  const rootChildren = new Set(Array.from(root.children));
  const q = qCand.find(c => {
    const el = c.el;
    if (el === root || rootChildren.has(el)) return false;
    if (txt(el).length > 400) return false;
    // 必须有可见左边框，或非白/非透明背景，否则视为无效引用样式
    const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(c.cs.backgroundColor || '');
    const isWhite = m && +m[1] > 245 && +m[2] > 245 && +m[3] > 245;
    const hasBorder = parseFloat(c.cs.borderLeftWidth) > 0 && c.cs.borderLeftStyle !== 'none';
    const hasRealBg = !isWhite && c.cs.backgroundColor !== 'rgba(0, 0, 0, 0)';
    return hasBorder || hasRealBg;
  });
  if (q) {
    const el = q.el, cs = q.cs;
    quote = {
      borderLeftWidth: cs.borderLeftWidth, borderLeftStyle: cs.borderLeftStyle,
      borderLeftColor: cs.borderLeftColor, backgroundColor: cs.backgroundColor,
      paddingTop: cs.paddingTop, paddingBottom: cs.paddingBottom,
      paddingLeft: cs.paddingLeft, paddingRight: cs.paddingRight,
      marginTop: cs.marginTop, marginBottom: cs.marginBottom,
      color: cs.color, fontSize: cs.fontSize, lineHeight: cs.lineHeight,
      borderRadius: cs.borderRadius,
    };
  }

  // ---------- 6. 列表 / 代码 / 分割线 / 图片 ----------
  const lis = Array.from(root.querySelectorAll('li')).filter(visible);
  let li = null;
  if (lis.length >= 2) {
    const s = snap(lis[0]);
    li = pick(s, ['fontSize','color','lineHeight','letterSpacing','marginTop','marginBottom',
                  'paddingLeft','textAlign','fontFamily']);
  }

  const codes = Array.from(root.querySelectorAll('pre, code')).filter(visible);
  let code = null, pre = null;
  if (codes.length) {
    const s = snap(codes[0]);
    code = pick(s, ['fontSize','color','backgroundColor','padding','borderRadius','fontFamily']);
    const pe = root.querySelector('pre');
    if (pe) pre = pick(snap(pe), ['backgroundColor','padding','borderRadius','fontSize','lineHeight',
                                  'color','borderLeftWidth','borderLeftStyle','borderLeftColor','marginTop','marginBottom']);
  }

  let divider = null;
  const hr = root.querySelector('hr');
  if (hr) {
    const s = snap(hr);
    divider = pick(s, ['borderTopWidth','borderTopStyle','borderTopColor','borderBottomWidth',
                       'borderBottomStyle','borderBottomColor','height','backgroundColor',
                       'backgroundImage','marginTop','marginBottom','opacity']);
  } else {
    root.querySelectorAll('section, div, p').forEach(el => {
      if (divider || !visible(el)) return;
      const cs = getComputedStyle(el);
      const h = el.getBoundingClientRect().height;
      const bw = parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
      if (h > 0 && h < 8 && txt(el).length === 0 && (bw > 0 || cs.backgroundImage !== 'none')) {
        divider = pick(cs, ['borderTopWidth','borderTopStyle','borderTopColor','borderBottomWidth',
                            'borderBottomStyle','borderBottomColor','height','backgroundColor',
                            'backgroundImage','marginTop','marginBottom','opacity']);
      }
    });
  }

  const img = root.querySelector('img');
  let imgStyle = { maxWidth: '100%', display: 'block', margin: '0 auto', borderRadius: paraStyle.borderRadius || '' };
  if (img) {
    const s = snap(img);
    imgStyle = Object.assign({}, pick(s, ['borderRadius','boxShadow','borderTopWidth','borderTopStyle',
                                          'borderTopColor','maxWidth','opacity']), { display: 'block', margin: '0 auto' });
  }

  // ---------- 7. 主题强调色 ----------
  const colorW = {};
  root.querySelectorAll('*').forEach(el => {
    if (!visible(el)) return;
    const cs = getComputedStyle(el);
    if (txt(el).length === 0) return;
    if (isGrey(cs.color)) return;
    if (Math.abs(parseFloat(cs.color) - 0) >= 0) { /* noop */ }
    colorW[cs.color] = (colorW[cs.color] || 0) + Math.min(txt(el).length, 200);
  });
  const colorArr = Object.entries(colorW).sort((a, b) => b[1] - a[1]);
  let accent = null;
  for (const [c, n] of colorArr) {
    if (c !== bodyColor && n >= 8) { accent = c; break; }
  }
  if (!accent && colorArr.length) accent = colorArr[0][0];
  if (!accent) accent = '#07c160';

  // ---------- 8. 页面背景 / 容器 ----------
  let pageBg = 'rgba(0, 0, 0, 0)';
  ['.rich_media_area', '.rich_media', '#page-content', 'body'].forEach(sel => {
    const el = document.querySelector(sel);
    if (!el) return;
    const c = getComputedStyle(el).backgroundColor;
    if (c && c !== 'rgba(0, 0, 0, 0)') { if (pageBg === 'rgba(0, 0, 0, 0)') pageBg = c; }
  });
  if (pageBg === 'rgba(0, 0, 0, 0)') pageBg = '#ffffff';

  const rs = snap(root);
  const container = pick(rs, ['fontSize','color','lineHeight','letterSpacing','textAlign',
                              'paddingLeft','paddingRight','paddingTop','paddingBottom','fontFamily','maxWidth']);

  // ---------- 9. 原始 CSS（保留正文相关规则，供 class 型样式生效） ----------
  let rawCss = '';
  document.querySelectorAll('style').forEach(st => { rawCss += (st.textContent || '') + '\n'; });
  rawCss = rawCss.replace(/html\s*\{[^}]*\}/g, '').replace(/\bbody\s*\{[^}]*\}/g, '');

  const title = (document.querySelector('#activity-name') || {}).innerText
             || document.querySelector('meta[property="og:title"]')?.content
             || document.title || '';
  const account = (document.querySelector('#js_name') || {}).innerText
               || document.querySelector('.rich_media_meta_nickname')?.innerText || '';

  // ---------- 10. 原文清洗后的 HTML（用于预览对照） ----------
  root.querySelectorAll('img').forEach(im => {
    const ds = im.getAttribute('data-src') || im.getAttribute('data-croporisrc');
    if (ds && !im.getAttribute('src')) im.setAttribute('src', ds);
    const st = im.style;
    st.maxWidth = '100%'; st.height = 'auto';
  });
  const preview = root.outerHTML;

  return {
    meta: { title: (title || '').trim(), account: (account || '').trim() },
    page: { background: pageBg, accent, bodySize, bodyColor, fontFamily: paraStyle.fontFamily || container.fontFamily || '' },
    container: { style: container, className: root.className || '', rawId: root.id || '' },
    styles: {
      p: paraStyle, wrapper: wrapStyle,
      h1: heads.h1 || null, h2: heads.h2 || null, h3: heads.h3 || null,
      blockquote: quote, li, code, pre, hr: divider, img: imgStyle,
      a: { color: accent, textDecoration: 'none' },
      strong: { color: accent, fontWeight: 'bold' },
    },
    rawCss,
    preview,
  };
}
"""


TAG_KEEP = {"p", "section", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
            "blockquote", "img", "strong", "em", "a", "table", "thead", "tbody",
            "tr", "td", "th", "pre", "code", "hr", "span", "figure", "figcaption"}


def filter_css(raw: str, html: str, limit: int = 150000) -> str:
    """只保留与正文相关的 CSS 规则，避免整站样式（动辄 1MB）污染输出"""
    raw = re.sub(r"@font-face\s*\{[^}]*\}", "", raw, flags=re.I)
    classes = set()
    for m in re.finditer(r'class="([^"]*)"', html or ""):
        for c in m.group(1).split():
            if 0 < len(c) < 64:
                classes.add(c)
    out = []
    for m in re.finditer(r"([^{}@]+)\{([^{}]*)\}", raw):
        sel, body = m.group(1).strip(), m.group(2).strip()
        if not sel or "@" in sel or len(sel) > 600:
            continue
        keep = False
        for c in classes:
            if "." + c in sel:
                keep = True
                break
        if not keep and re.search(r"#(js_content|img-content|page-content|js_article)", sel):
            keep = True
        if not keep:
            parts = [x.strip() for x in sel.split(",") if x.strip()]
            if parts and all(re.fullmatch(r"[a-z]+\d?", p) for p in parts):
                if any(p in TAG_KEEP for p in parts):
                    keep = True
        if keep:
            out.append(f"{sel} {{{body}}}")
    return "\n".join(out)[:limit]


def _cache_path(url: str) -> Path:
    return CACHE_DIR / (hashlib.md5(url.encode()).hexdigest() + ".json")


def extract_theme(url: str, use_cache: bool = True, timeout: int = 45000) -> dict:
    """抓取公众号文章并提取样式主题"""
    key = _cache_path(url)
    if use_cache and key.exists():
        try:
            t = json.loads(key.read_text(encoding="utf-8"))
            if len(t.get("rawCss", "")) > 160000:  # 旧版缓存未过滤，重抓
                key.unlink()
            else:
                return t
        except Exception:
            pass

    from browser import launch
    with sync_playwright() as p:
        browser = launch(p)
        ctx = browser.new_context(
            user_agent=UA_PC,
            viewport={"width": 1280, "height": 900},
            device_scale_factor=2,
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(1200)
            # 滚动一遍触发懒加载图片
            for i in range(6):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(250)
            page.wait_for_timeout(800)
            theme = page.evaluate(EXTRACT_JS)
        finally:
            ctx.close()
            browser.close()

    theme["meta"] = theme.get("meta") or {}
    theme["meta"]["url"] = url
    theme["rawCss"] = filter_css(theme.get("rawCss", ""), theme.get("preview", ""))
    key.write_text(json.dumps(theme, ensure_ascii=False), encoding="utf-8")
    return theme


if __name__ == "__main__":
    import sys
    u = sys.argv[1] if len(sys.argv) > 1 else "https://mp.weixin.qq.com/s/Uw6b7_W_NkCZDIce4Obn6g"
    t = extract_theme(u, use_cache=False)
    print(json.dumps({k: v for k, v in t.items() if k != "rawCss" and k != "preview"},
                     ensure_ascii=False, indent=2))
