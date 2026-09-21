# -*- coding: utf-8 -*-
"""
浏览器启动适配：优先用 playwright 自带的 chromium，失败则回退系统已装的 Chrome/Chromium。
这样在本地、Codespaces、Docker、GitHub Actions 里都能开箱即用。
"""
import os
import shutil

COMMON_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]


def _candidates():
    paths = [None]  # None = playwright 自带浏览器
    env = os.environ.get("CHROME_PATH")
    if env:
        paths.append(env)
    for p in ("/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        paths.append(p)
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        w = shutil.which(name)
        if w:
            paths.append(w)
    return paths


def launch(pw, **kwargs):
    """返回一个已启动的 Browser，自动挑选可用的浏览器可执行文件"""
    errs = []
    seen = set()
    for exe in _candidates():
        if exe in seen:
            continue
        seen.add(exe)
        if exe and not os.path.exists(exe):
            continue
        try:
            return pw.chromium.launch(executable_path=exe,
                                      args=COMMON_ARGS, **kwargs)
        except Exception as e:
            errs.append(f"{exe or 'bundled'}: {str(e)[:120]}")
    raise RuntimeError(
        "找不到可用的 Chromium/Chrome。请先执行 `playwright install chromium`，"
        "或设置环境变量 CHROME_PATH 指向本机浏览器。\n" + "\n".join(errs[:3])
    )
