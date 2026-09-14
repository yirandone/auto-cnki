# -*- coding: utf-8 -*-
"""
新闻传播学每日文献推送（B 方案：综合排序取 3 篇）
- 数据源：cnki-mcp（命令行）
- 智能筛选：DeepSeek（写推荐理由）
- 输出：邮件
"""
import os
import sys
import json
import smtplib
import subprocess
from datetime import datetime, timedelta, date as date_cls
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------- 配置 ----------------
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

JOURNALS = [
    "国际新闻界",
    "新闻与传播研究",
    "现代传播(中国传媒大学学报)",
    "新闻大学",
    "新闻记者",
]
TOPICS = ["算法推荐", "平台治理", "数字新闻", "情感传播"]

PUSHED_FILE = BASE_DIR / "pushed.txt"
OUTPUT_DIR = BASE_DIR / "digest_output"

RESULT_COUNT = 3                                  # 每天推几篇
POOL_SIZE = 60                                    # 每次检索拉取条数
WINDOW_DAYS_TIERS = (30, 90, 365, 100000)         # 时间窗，不够自动放宽

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
QQ_EMAIL = os.getenv("QQ_EMAIL", "")
QQ_SMTP_CODE = os.getenv("QQ_SMTP_CODE", "")
MAIL_TO = "2677562625@qq.com"

DRY_RUN = "--dry-run" in sys.argv
TODAY = datetime.now().date()

# ---------------- 调用 cnki-mcp ----------------
def run_cli(args):
    """调用 cnki-mcp，强制 UTF-8 输出并兼容解码，避免中文乱码。"""
    cmd = ["uv", "run", "cnki-mcp", "tool"] + args
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(cmd, capture_output=True, cwd=str(BASE_DIR), env=env)
    raw = proc.stdout
    text = None
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"命令失败: {' '.join(cmd)}\n{err[-800:]}")
    return text

def parse_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for s_ch, e_ch in (("[", "]"), ("{", "}")):
        s, e = text.find(s_ch), text.rfind(e_ch)
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("无法解析 JSON:\n" + text[:500])

def parse_date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None

def build_expression():
    topics = " + ".join(f"'{t}'" for t in TOPICS)
    journals = " + ".join(f"'{j}'" for j in JOURNALS)
    return f"KY=({topics}) and LY=({journals})"

def search(sort_by, limit=POOL_SIZE):
    out = run_cli([
        "search", "--advanced", build_expression(),
        "--sort-by", sort_by, "--limit", str(limit), "--output", "json",
    ])
    data = parse_json(out)
    return data if isinstance(data, list) else []

def get_info(article):
    authors = article.get("authors") or []
    args = ["info", "--title", article["title"], "--output", "json"]
    if authors:
        args += ["--author", authors[0]]
    year = str(article.get("date", ""))[:4]
    if year:
        args += ["--year", year]
    if article.get("journal"):
        args += ["--source", article["journal"]]
    try:
        data = parse_json(run_cli(args))
    except Exception as e:
        print("info 获取失败:", e)
        return {}
    art = data.get("article") if isinstance(data, dict) else None
    return art or {}

# ---------------- 已推送清单（去重） ----------------
def load_pushed():
    if not PUSHED_FILE.exists():
        return set()
    return {ln.strip() for ln in PUSHED_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()}

def add_pushed(titles):
    with PUSHED_FILE.open("a", encoding="utf-8") as f:
        for t in titles:
            f.write(t + "\n")

# ---------------- DeepSeek ----------------
def call_deepseek(prompt):
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

def get_reason(info):
    """让 DeepSeek 写一句推荐理由。"""
    title = info.get("title", "")
    kw = "、".join(info.get("keywords") or [])
    abstract = (info.get("abstract") or "")[:400]
    prompt = (
        "你是新闻传播学领域的研究助理。请用一句话（40 字以内）说明下面这篇论文"
        "为什么值得关注，语气客观、直击要点，不要重复标题。\n\n"
        f"题目：{title}\n关键词：{kw}\n摘要：{abstract}\n\n"
        "只返回这一句话，不要任何前缀。"
    )
    try:
        return call_deepseek(prompt).strip()
    except Exception as e:
        print("DeepSeek 调用失败:", e)
        return ""

# ---------------- 选文（B 方案） ----------------
def pick_top_articles(pool, pushed, chosen, count=RESULT_COUNT):
    """按综合排序取前 count 篇；时间窗不够则自动放宽。"""
    base = [a for a in pool if a["title"] not in pushed and a["title"] not in chosen]
    picked = []
    used_days = WINDOW_DAYS_TIERS[-1]
    for days in WINDOW_DAYS_TIERS:
        cutoff = TODAY - timedelta(days=days)
        picked = [
            a for a in base
            if (parse_date(a.get("date")) or date_cls.min) >= cutoff
        ][:count]
        if len(picked) >= count:
            used_days = days
            break
    print(f"[选文] 时间窗 {used_days} 天，选中 {len(picked)} 篇")
    return picked, used_days

# ---------------- 邮件 ----------------
def build_email_html(articles, used_days):
    parts = [f"<h2>新闻传播学每日文献推送（{datetime.now():%Y-%m-%d}）</h2>"]
    parts.append(f"<p style='color:#888'>范围：5 本核心期刊 · 议题：{'、'.join(TOPICS)} · 时间窗：近 {used_days} 天</p>")
    for i, item in enumerate(articles, 1):
        info = item["info"]
        parts.append(f"<h3>{i}. {info.get('title','')}</h3>")
        parts.append(f"<p><b>作者：</b>{'、'.join(info.get('authors') or [])}</p>")
        parts.append(f"<p><b>期刊：</b>{info.get('source','')}（{info.get('year','')}）</p>")
        parts.append(f"<p><b>关键词：</b>{'、'.join(info.get('keywords') or [])}</p>")
        if item.get("reason"):
            parts.append(f"<p><b>推荐理由：</b>{item['reason']}</p>")
        parts.append(f"<p><b>摘要：</b>{info.get('abstract','（无摘要）')}</p>")
        parts.append(f"<p><a href=\"{info.get('url','')}\">→ 知网详情页</a></p><hr>")
    return "\n".join(parts)

def send_email(subject, html):
    msg = MIMEText(html, "html", "utf-8")
    msg["From"] = formataddr(("CNKI 每日文献", QQ_EMAIL))
    msg["To"] = MAIL_TO
    msg["Subject"] = Header(subject, "utf-8")
    with smtplib.SMTP_SSL("smtp.qq.com", 465) as server:
        server.login(QQ_EMAIL, QQ_SMTP_CODE)
        server.sendmail(QQ_EMAIL, [MAIL_TO], msg.as_string())

# ---------------- 主流程 ----------------
def main():
    pushed = load_pushed()
    chosen = set()
    print("检索式:", build_expression())

    pool = search("comprehensive")
    print(f"[检索] 共 {len(pool)} 条候选")

    picked, used_days = pick_top_articles(pool, pushed, chosen, RESULT_COUNT)

    articles = []
    for a in picked:
        print(f"[选中] {a['title']}")
        info = get_info(a)
        if not info.get("title"):
            info = {
                "title": a["title"],
                "authors": a.get("authors", []),
                "source": a.get("journal", ""),
                "year": str(a.get("date", ""))[:4],
            }
        reason = get_reason(info)
        articles.append({"search": a, "info": info, "reason": reason})

    if not articles:
        print("没有可推送的新文献。")
        return

    html = build_email_html(articles, used_days)
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"新闻传播学每日文献 {today}"

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / f"{today}.html").write_text(html, encoding="utf-8")

    if DRY_RUN:
        print("\n=== DRY RUN，不发送邮件 ===\n")
        print(html)
        return

    send_email(subject, html)
    add_pushed(item["info"].get("title", item["search"]["title"]) for item in articles)
    print("邮件已发送 →", MAIL_TO)

if __name__ == "__main__":
    main()