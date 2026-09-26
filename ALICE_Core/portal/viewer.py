import html
import logging
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
import markdown
import config

logger = logging.getLogger(__name__)

router = APIRouter()


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title}</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --primary: #059669;
      --primary-hover: #047857;
      --primary-light: #ecfdf5;
      --secondary: #475569;
      --secondary-bg: #f1f5f9;
      --code-bg: #f1f5f9;
      --quote-border: #10b981;
      --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.07), 0 2px 4px -2px rgb(0 0 0 / 0.05);
    }}

    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f172a;
        --card-bg: #1e293b;
        --text: #f1f5f9;
        --text-muted: #94a3b8;
        --border: #334155;
        --primary: #10b981;
        --primary-hover: #34d399;
        --primary-light: rgba(16, 185, 129, 0.15);
        --secondary: #cbd5e1;
        --secondary-bg: #334155;
        --code-bg: #0f172a;
        --quote-border: #34d399;
        --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.2);
      }}
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", "Noto Sans JP", sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.75;
      padding: 1rem 0.75rem 3rem;
    }}

    .container {{
      max-width: 800px;
      margin: 0 auto;
    }}

    /* Header Bar */
    .header-bar {{
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      margin-bottom: 1.25rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--border);
    }}

    .brand-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    .brand-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--primary);
      background: var(--primary-light);
      padding: 0.25rem 0.65rem;
      border-radius: 9999px;
    }}

    .file-name {{
      font-size: 0.85rem;
      color: var(--text-muted);
      word-break: break-all;
    }}

    .action-row {{
      display: flex;
      gap: 0.5rem;
      justify-content: flex-end;
    }}

    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.45rem 0.85rem;
      font-size: 0.85rem;
      font-weight: 600;
      border-radius: 0.5rem;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.2s ease;
      border: 1px solid transparent;
    }}

    .btn-secondary {{
      background: var(--secondary-bg);
      color: var(--secondary);
      border-color: var(--border);
    }}

    .btn-secondary:hover {{
      opacity: 0.9;
    }}

    .btn-primary {{
      background: var(--primary);
      color: #ffffff;
    }}

    .btn-primary:hover {{
      background: var(--primary-hover);
    }}

    /* Content Card */
    .content-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.5rem 1.25rem;
      box-shadow: var(--shadow);
      word-break: break-word;
    }}

    @media (min-width: 640px) {{
      body {{
        padding: 2rem 1rem 4rem;
      }}
      .content-card {{
        padding: 2.5rem 2rem;
      }}
      .header-bar {{
        flex-direction: row;
        justify-content: space-between;
        align-items: center;
      }}
    }}

    /* Markdown Typography */
    .markdown-body h1,
    .markdown-body h2,
    .markdown-body h3,
    .markdown-body h4 {{
      color: var(--text);
      font-weight: 700;
      line-height: 1.35;
      margin-top: 1.75rem;
      margin-bottom: 0.75rem;
    }}

    .markdown-body h1:first-child,
    .markdown-body h2:first-child {{
      margin-top: 0;
    }}

    .markdown-body h1 {{
      font-size: 1.5rem;
      padding-bottom: 0.4rem;
      border-bottom: 2px solid var(--primary);
    }}

    .markdown-body h2 {{
      font-size: 1.25rem;
      padding-left: 0.6rem;
      border-left: 4px solid var(--primary);
    }}

    .markdown-body h3 {{
      font-size: 1.1rem;
    }}

    .markdown-body p {{
      margin-bottom: 1rem;
    }}

    .markdown-body ul,
    .markdown-body ol {{
      margin-bottom: 1rem;
      padding-left: 1.5rem;
    }}

    .markdown-body li {{
      margin-bottom: 0.35rem;
    }}

    .markdown-body blockquote {{
      border-left: 4px solid var(--quote-border);
      padding: 0.5rem 1rem;
      margin: 1rem 0;
      background: var(--primary-light);
      border-radius: 0 0.5rem 0.5rem 0;
      color: var(--text);
    }}

    .markdown-body pre {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      padding: 1rem;
      border-radius: 0.5rem;
      overflow-x: auto;
      font-size: 0.85rem;
      margin-bottom: 1rem;
    }}

    .markdown-body code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      background: var(--code-bg);
      padding: 0.2rem 0.4rem;
      border-radius: 0.3rem;
      font-size: 0.9em;
    }}

    .markdown-body pre code {{
      padding: 0;
      background: transparent;
    }}

    .markdown-body table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1rem 0;
      display: block;
      overflow-x: auto;
    }}

    .markdown-body th,
    .markdown-body td {{
      border: 1px solid var(--border);
      padding: 0.6rem 0.85rem;
      text-align: left;
    }}

    .markdown-body th {{
      background: var(--secondary-bg);
      font-weight: 600;
    }}

    .markdown-body hr {{
      border: 0;
      border-top: 1px solid var(--border);
      margin: 1.5rem 0;
    }}

    /* Navigation Tab Bar */
    .tab-bar {{
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0;
    }}

    .tab-btn {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.6rem 1.1rem;
      font-size: 0.9rem;
      font-weight: 600;
      border-radius: 0.5rem 0.5rem 0 0;
      text-decoration: none;
      color: var(--text-muted);
      background: transparent;
      border: 1px solid transparent;
      border-bottom: none;
      transition: all 0.2s ease;
    }}

    .tab-btn:hover {{
      color: var(--text);
      background: var(--secondary-bg);
    }}

    .tab-btn.active {{
      color: var(--primary);
      background: var(--card-bg);
      border-color: var(--border);
      border-bottom: 2px solid var(--primary);
    }}

    /* Toast Notification */
    .toast {{
      position: fixed;
      bottom: 2rem;
      left: 50%;
      transform: translateX(-50%) translateY(100px);
      background: #1e293b;
      color: #ffffff;
      padding: 0.6rem 1.25rem;
      border-radius: 9999px;
      font-size: 0.85rem;
      font-weight: 500;
      box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.3);
      opacity: 0;
      transition: all 0.3s ease;
      z-index: 1000;
    }}

    .toast.show {{
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="header-bar">
      <div class="brand-row">
        <div class="brand-badge">✨ Project ALICE</div>
        <span class="file-name">{safe_filename}</span>
      </div>
      <div class="action-row">
        <button id="copyBtn" class="btn btn-secondary" onclick="copyContent()">
          📋 コピー
        </button>
        <a href="{download_url}" class="btn btn-primary" download>
          📥 ダウンロード
        </a>
      </div>
    </header>

    {tab_bar_html}

    <main class="content-card">
      <article id="docContent" class="markdown-body">
        {rendered_html}
      </article>
    </main>
  </div>

  <div id="toast" class="toast">クリップボードにコピーしました</div>

  <script>
    function copyContent() {{
      const text = document.getElementById('docContent').innerText;
      navigator.clipboard.writeText(text).then(() => {{
        const toast = document.getElementById('toast');
        toast.classList.add('show');
        setTimeout(() => {{
          toast.classList.remove('show');
        }}, 2000);
      }}).catch(err => {{
        console.error('Copy failed:', err);
      }});
    }}
  </script>
</body>
</html>
"""


@router.get("/view/{filename}", response_class=HTMLResponse)
def view_document(filename: str):
    # パストラバーサル防止のため、ファイル名のベースネームのみを取り出す
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    path = Path(config.DIR_SHARE) / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="cp932") as f:
                raw_content = f.read()
        except Exception as e:
            logger.error(f"[Viewer] Failed to read file {safe_name}: {e}")
            raise HTTPException(status_code=500, detail="Failed to decode file.")
    except Exception as e:
        logger.error(f"[Viewer] Error opening file {safe_name}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")

    # MarkdownからHTMLへ変換
    rendered_html = markdown.markdown(
        raw_content,
        extensions=["extra", "nl2br", "sane_lists"]
    )

    page_title = safe_name
    safe_escaped_filename = html.escape(safe_name)
    download_url = f"{config.PUBLIC_URL}/download/{safe_name}"

    # 兄弟成果物（要約・解説講評・議事録）の相互リンクと3画面タブ生成
    tab_bar_html = ""
    share_dir = Path(config.DIR_SHARE)
    siblings: dict[str, str] = {}

    # 1. Job-prefixed 形式 (例: job_20260916_234905_伊藤さん面談_summary_summary.txt)
    m = re.match(r"^(.+?)_(?:summary|minutes)_(.+)$", safe_name)
    if m:
        job_prefix = m.group(1)
        for ext in [".md", ".txt"]:
            cand = share_dir / f"{job_prefix}_summary_summary{ext}"
            if cand.is_file():
                siblings["summary"] = cand.name
                break
        for ext in [".md", ".txt"]:
            cand = share_dir / f"{job_prefix}_summary_commentary{ext}"
            if cand.is_file():
                siblings["commentary"] = cand.name
                break
        for ext in [".md", ".txt"]:
            cand = share_dir / f"{job_prefix}_minutes_minutes{ext}"
            if cand.is_file():
                siblings["minutes"] = cand.name
                break

    # 2. 単独ファイル名形式 (例: summary.txt, commentary.md, minutes.md)
    if not siblings:
        for key, base in [("summary", "summary"), ("commentary", "commentary"), ("minutes", "minutes")]:
            for ext in [".md", ".txt"]:
                cand = share_dir / f"{base}{ext}"
                if cand.is_file():
                    siblings[key] = cand.name
                    break

    tab_defs = [
        ("summary", "📝 要約レポート"),
        ("commentary", "💡 解説・講評レポート"),
        ("minutes", "📋 議事録"),
    ]
    tabs_html = []
    if len(siblings) >= 2 or (safe_name in siblings.values() and len(siblings) > 1):
        for key, label in tab_defs:
            if key in siblings:
                target_file = siblings[key]
                is_active = target_file == safe_name
                active_cls = " active" if is_active else ""
                url = f"{config.PUBLIC_URL}/view/{target_file}"
                tabs_html.append(f'<a href="{url}" class="tab-btn{active_cls}">{label}</a>')

    if tabs_html:
        tab_bar_html = f'<nav class="tab-bar">{" ".join(tabs_html)}</nav>'

    html_content = HTML_TEMPLATE.format(
        page_title=html.escape(page_title),
        safe_filename=safe_escaped_filename,
        download_url=download_url,
        tab_bar_html=tab_bar_html,
        rendered_html=rendered_html
    )

    return HTMLResponse(content=html_content, status_code=200)
