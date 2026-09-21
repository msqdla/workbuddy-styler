# 公众号样式排版工具

把任意一篇微信公众号文章的**排版样式**（字号 / 颜色 / 行距 / 标题装饰 / 引用块 / 列表 / 代码块 / 主题色 / 背景）抓取下来，一键套用到你自己的 **Markdown** 内容，生成可直接粘贴进公众号编辑器的 HTML。

## 网页版（推荐）

```bash
python3 app.py
# 浏览器打开 http://localhost:8777
```

操作三步：

1. 粘贴公众号文章链接 → 「抓取样式」（结果自动缓存，同链接不会重复抓）
2. 粘贴 / 上传你的 Markdown
3. 「生成同款排版」→ 右侧手机预览，可下载 HTML、复制正文（Ctrl+V 粘进公众号后台样式保留）、导出长图 PNG

可选微调：主题色、背景色、字号、行高、字间距、首行缩进、对齐、图片内嵌 base64。

## 命令行版

```bash
python3 style_it.py <公众号URL> <input.md> -o out.html [--png out.png] [--embed] \
                    [--accent "#c0392b"] [--font-size 16] [--line-height 1.8]
```

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `app.py` | Flask 网页服务（抓取 / 渲染 / 导出长图三个接口） |
| `extractor.py` | Playwright 打开原文，对正文做逐元素计算样式采样，聚类出段落 / 标题 / 引用 / 列表 / 代码 / 分割线等样式签名 |
| `renderer.py` | Markdown → HTML，按样式签名逐标签套用，缺失项自动兜底 |
| `style_it.py` | 命令行入口 |
| `static/index.html` | 网页前端 |
| `sample.md` | 示例 Markdown |
| `示例输出_*.html` | 用两篇不同风格文章生成的演示成品 |

## 工作原理

公众号正文样式几乎全部是**内联 style**（第三方编辑器如秀米、135 也是如此）。工具用无头浏览器加载原文后：

- 按文本量加权统计出正文字号 / 颜色 / 行距 / 字间距 / 对齐；
- 对带文本的块元素做「样式签名」聚类，取众数作为段落样式，字号更大或带装饰背景的聚类为标题（最多 3 级，含父容器装饰条）；
- 从带左边框 / 背景色的块中识别引用样式，从小高度带边框的块中识别分割线；
- 统计非黑灰的高频文字颜色作为主题强调色；
- 保留原文 `<style>` 中与正文相关的 CSS 规则（容器 id 保持 `js_content`，class 型规则同样生效），并自动清理负边距、`visibility:hidden` 等会污染新页面的规则。

## 已知限制

- 仅支持 `mp.weixin.qq.com` 文章链接（含 `/s/短链` 与 `?__biz=` 长链）。
- 标题装饰复杂的文章（背景图标题条）能保留颜色与字号，但背景图本身不迁移。
- 原文视频 / 小程序卡片等富媒体不在 Markdown 表达范围内，不会出现在生成结果中。
- 抓取依赖无头浏览器访问，若原文被微信风控拦截会提示失败，稍后重试即可。

---

## 放到 GitHub 上用（三种姿势）

> 说明：抓取样式必须有服务端（要跨域打开公众号页面并跑无头浏览器），**纯 GitHub Pages 静态托管跑不了本工具**。下面三种方式都能真正用起来。

### 姿势 A：推到仓库 + Codespaces 在线用（最省事）

零安装，浏览器里就有完整环境：

1. 按下面「首次推送」把代码推到 GitHub
2. 仓库页面 → `<> Code` → `Codespaces` → `Create codespace on main`
3. 环境会自动装好依赖和 Chromium（约 2 分钟），8777 端口自动转发并弹出预览窗口
4. 直接用网页工具；也可以终端跑 `python3 style_it.py <url> <md> -o out.html`

本机跑则是：`bash start.sh`（Windows 双击 `start.bat`）。

### 姿势 B：GitHub Actions 自动出稿（推 md 就出成品）

把 Markdown 放进 `content/`，填好 `content/config.json`，推送后 Actions 自动：
抓取样式 → 生成成品 HTML + 长图 → 上传为构建产物 → 提交回仓库 `output/` 目录。

- 下载成品：仓库 → Actions → 最新一次运行 → Artifacts → `公众号排版成品`
- 在线看成品：手动触发（Actions → 生成公众号排版 → Run workflow）可勾选 `publish_pages`，发布到 GitHub Pages（需先在 Settings → Pages → Source 选 **GitHub Actions**）
- 换样式：改 `content/config.json` 里的 `style_url`

⚠️ 微信对数据中心 IP 有风控，Actions 上偶发抓取失败（页面返回验证页），重跑一次通常就好。

### 姿势 C：Docker 一行启动

```bash
docker build -t wx-styler .
docker run -p 8777:8777 wx-styler      # 打开 http://localhost:8777
```

### 首次推送

```bash
cd wechat-md-styler
git init && git add . && git commit -m "feat: 公众号样式排版工具"
gh repo create wx-md-styler --public --source=. --push     # 需要 gh auth login
```

没有 `gh` 就先在 GitHub 网页新建空仓库，然后：

```bash
git remote add origin git@github.com:<你的用户名>/wx-md-styler.git
git branch -M main && git push -u origin main
```

> `.gitignore` 已排除 `.cache/`、`output/`、`__pycache__/`，不会把缓存和成品误提交。
