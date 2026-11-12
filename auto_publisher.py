import os
import re
import json
import yaml
import requests
import random
import subprocess
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.cloud import storage

PROJECT_DIR = Path(r"E:\app\make.money\1")
load_dotenv(PROJECT_DIR / ".env", override=True)

config_path = PROJECT_DIR / "config.yaml"
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", config.get("gcp", {}).get("project_id"))
GCP_LOCATION = os.getenv("GCP_LOCATION", config.get("gcp", {}).get("location", "us-central1"))
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", config.get("gcp", {}).get("gcs_bucket"))
TARGET_API_URL = os.getenv("TARGET_API_URL")
TARGET_API_TOKEN = os.getenv("TARGET_API_TOKEN")

AI_MODEL = config["ai_engine"]["model"]
FALLBACK_MODEL = config["ai_engine"].get("fallback_model", "gemini-3.6-flash")
TEMPERATURE = config["ai_engine"].get("temperature", 0.7)
MAX_OUTPUT_TOKENS = config["ai_engine"].get("max_output_tokens", 8192)

NICHES = config["content_settings"]["niches"]
DEFAULT_STATUS = config["content_settings"]["default_post_status"]
AUTO_PUSH_PAGES = config["content_settings"].get("auto_push_github_pages", True)
AFFILIATE_LINKS = config.get("affiliate_links", {})

SITE_URL = config["system"].get("site_url", "https://ednakrabgit.github.io/make.money")
SITE_TITLE = config["system"].get("site_title", "Tech & Smart Living Insights")
SITE_DESC = config["system"].get("site_description", "Expert reviews, smart home automation guides, and developer productivity tools.")

DOCS_DIR = PROJECT_DIR / "docs"
ARTICLES_DIR = DOCS_DIR / "articles"
MANIFEST_PATH = DOCS_DIR / "articles.json"
LOG_PATH = PROJECT_DIR / config["logging"]["log_path"]

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
ARTICLES_DIR.mkdir(parents=True, exist_ok=True)


def log_message(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(log_line + "\n")


def upload_to_gcs(local_path: Path, destination_blob_name: str, content_type: str = "text/plain") -> bool:
    if not GCS_BUCKET_NAME:
        return False
    try:
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(str(local_path), content_type=content_type)
        log_message(f"Uploaded to GCS: gs://{GCS_BUCKET_NAME}/{destination_blob_name}")
        return True
    except Exception as e:
        log_message(f"GCS upload error ({destination_blob_name}): {e}")
        return False


def clean_html_and_extract_meta(raw_text: str, default_niche: str):
    text = raw_text.strip()
    fence_match = re.search(r"```(?:html)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.DOTALL | re.IGNORECASE)
    if not title_match:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.DOTALL | re.IGNORECASE)
    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else f"{default_niche} Guide"

    body_match = re.search(r"<body[^>]*>(.*?)</body>", text, flags=re.DOTALL | re.IGNORECASE)
    body_html = body_match.group(1).strip() if body_match else text

    p_matches = re.findall(r"<p[^>]*>(.*?)</p>", body_html, flags=re.DOTALL | re.IGNORECASE)
    excerpt = ""
    for p in p_matches:
        clean_p = re.sub(r"<[^>]+>", "", p).strip()
        if len(clean_p) > 40:
            excerpt = clean_p[:180] + ("..." if len(clean_p) > 180 else "")
            break
    if not excerpt:
        excerpt = f"In-depth guide and practical recommendations for {default_niche}."

    return title, excerpt, body_html


def render_affiliate_cards(niche: str) -> str:
    items = AFFILIATE_LINKS.get(niche, [])
    if not items:
        return ""
    cards = []
    for item in items:
        cards.append(
            f"""
            <div class="deal-card">
                <span class="deal-badge">{item.get('badge', 'Recommended')}</span>
                <h4>{item.get('name')}</h4>
                <p>{item.get('description', '')}</p>
                <a href="{item.get('url')}" target="_blank" rel="nofollow sponsored noopener" class="deal-btn">
                    Check Latest Price & Deals &rarr;
                </a>
            </div>
            """
        )
    return f"""
    <section class="deals-box">
        <h3>Recommended Gear & Software Deals</h3>
        <div class="deals-grid">
            {''.join(cards)}
        </div>
        <p class="disclosure">Disclosure: This article contains affiliate links. We may earn a commission at no extra cost to you.</p>
    </section>
    """


def wrap_article_page(title: str, excerpt: str, body_html: str, niche: str, date_str: str) -> str:
    deals_section = render_affiliate_cards(niche)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | {SITE_TITLE}</title>
    <meta name="description" content="{excerpt}">
    <style>
        :root {{ --bg: #0f172a; --card: #1e293b; --text: #f8fafc; --muted: #94a3b8; --accent: #38bdf8; --cta: #f97316; }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.75; }}
        header {{ border-bottom: 1px solid #334155; padding: 1.2rem 1.5rem; background: rgba(15,23,42,0.9); position: sticky; top: 0; backdrop-filter: blur(8px); }}
        .nav {{ max-width: 860px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
        .brand {{ color: var(--text); text-decoration: none; font-weight: 700; font-size: 1.15rem; }}
        .back-link {{ color: var(--accent); text-decoration: none; font-size: 0.95rem; }}
        main {{ max-width: 860px; margin: 2.5rem auto; padding: 0 1.5rem 4rem; }}
        .meta {{ display: flex; gap: 0.75rem; align-items: center; margin-bottom: 1rem; font-size: 0.85rem; color: var(--muted); }}
        .badge {{ background: rgba(56,189,248,0.15); color: var(--accent); padding: 0.25rem 0.7rem; border-radius: 999px; font-weight: 600; }}
        article {{ background: var(--card); padding: 2.5rem; border-radius: 16px; border: 1px solid #334155; }}
        h1 {{ font-size: 2.1rem; line-height: 1.25; margin-top: 0; color: #fff; }}
        h2 {{ font-size: 1.45rem; color: var(--accent); margin-top: 2rem; border-bottom: 1px solid #334155; padding-bottom: 0.4rem; }}
        h3 {{ font-size: 1.2rem; color: #e2e8f0; margin-top: 1.5rem; }}
        a {{ color: var(--accent); }}
        .deals-box {{ margin-top: 2.5rem; padding: 1.75rem; background: rgba(15,23,42,0.7); border: 1px solid #38bdf8; border-radius: 14px; }}
        .deals-box h3 {{ margin-top: 0; color: #fff; }}
        .deals-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem; margin-top: 1rem; }}
        .deal-card {{ background: var(--card); padding: 1.25rem; border-radius: 12px; border: 1px solid #334155; display: flex; flex-direction: column; justify-content: space-between; }}
        .deal-badge {{ align-self: flex-start; background: rgba(249,115,22,0.2); color: #fb923c; font-size: 0.75rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 6px; margin-bottom: 0.5rem; }}
        .deal-card h4 {{ margin: 0.4rem 0; font-size: 1.05rem; color: #fff; }}
        .deal-card p {{ font-size: 0.9rem; color: var(--muted); margin: 0.4rem 0 1rem; }}
        .deal-btn {{ display: inline-block; text-align: center; background: var(--cta); color: #fff !important; text-decoration: none; font-weight: 700; padding: 0.65rem 1rem; border-radius: 8px; transition: opacity 0.2s; }}
        .deal-btn:hover {{ opacity: 0.9; }}
        .disclosure {{ font-size: 0.75rem; color: var(--muted); margin: 1rem 0 0; }}
        footer {{ text-align: center; padding: 2rem; color: var(--muted); font-size: 0.85rem; border-top: 1px solid #334155; }}
    </style>
</head>
<body>
    <header>
        <div class="nav">
            <a href="../index.html" class="brand">{SITE_TITLE}</a>
            <a href="../index.html" class="back-link">&larr; All Articles</a>
        </div>
    </header>
    <main>
        <article>
            <div class="meta">
                <span class="badge">{niche}</span>
                <span>Published {date_str}</span>
            </div>
            {body_html}
            {deals_section}
        </article>
    </main>
    <footer>
        &copy; {datetime.now().year} {SITE_TITLE}. Powered by Antigravity Autonomous Content Pipeline.
    </footer>
</body>
</html>"""


def rebuild_site_index(manifest: list):
    cards_html = []
    for item in manifest:
        cards_html.append(
            f"""
            <a href="articles/{item['filename']}" class="card">
                <div class="card-meta">
                    <span class="badge">{item['niche']}</span>
                    <span>{item['date']}</span>
                </div>
                <h2>{item['title']}</h2>
                <p>{item['excerpt']}</p>
                <span class="read-more">Read Full Guide &rarr;</span>
            </a>
            """
        )

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{SITE_TITLE}</title>
    <meta name="description" content="{SITE_DESC}">
    <style>
        :root {{ --bg: #0f172a; --card: #1e293b; --text: #f8fafc; --muted: #94a3b8; --accent: #38bdf8; }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
        .hero {{ padding: 4rem 1.5rem 3rem; text-align: center; background: radial-gradient(circle at top, #1e293b 0%, #0f172a 70%); border-bottom: 1px solid #334155; }}
        .hero h1 {{ font-size: 2.5rem; margin: 0 0 0.75rem; background: linear-gradient(90deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .hero p {{ color: var(--muted); max-width: 600px; margin: 0 auto; font-size: 1.1rem; }}
        main {{ max-width: 1040px; margin: 3rem auto; padding: 0 1.5rem 4rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 1.5rem; }}
        .card {{ background: var(--card); border: 1px solid #334155; border-radius: 16px; padding: 1.75rem; text-decoration: none; color: var(--text); display: flex; flex-direction: column; justify-content: space-between; transition: transform 0.2s, border-color 0.2s; }}
        .card:hover {{ transform: translateY(-4px); border-color: var(--accent); }}
        .card-meta {{ display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: var(--muted); margin-bottom: 0.75rem; }}
        .badge {{ background: rgba(56,189,248,0.15); color: var(--accent); padding: 0.2rem 0.65rem; border-radius: 999px; font-weight: 600; }}
        .card h2 {{ font-size: 1.3rem; margin: 0.25rem 0 0.75rem; color: #fff; line-height: 1.35; }}
        .card p {{ color: var(--muted); font-size: 0.95rem; margin: 0 0 1.25rem; }}
        .read-more {{ color: var(--accent); font-weight: 600; font-size: 0.9rem; }}
        footer {{ text-align: center; padding: 2rem; color: var(--muted); font-size: 0.85rem; border-top: 1px solid #334155; }}
    </style>
</head>
<body>
    <section class="hero">
        <h1>{SITE_TITLE}</h1>
        <p>{SITE_DESC}</p>
    </section>
    <main>
        <div class="grid">
            {''.join(cards_html)}
        </div>
    </main>
    <footer>
        &copy; {datetime.now().year} {SITE_TITLE}. Updated daily by Antigravity Autonomous Content Pipeline.
    </footer>
</body>
</html>"""

    index_file = DOCS_DIR / "index.html"
    with open(index_file, "w", encoding="utf-8") as f:
        f.write(index_html)
    log_message(f"Updated static site homepage: {index_file}")
    upload_to_gcs(index_file, "site/index.html", content_type="text/html; charset=utf-8")


def generate_article():
    selected_niche = random.choice(NICHES)
    niche_links = AFFILIATE_LINKS.get(selected_niche, [])
    affiliate_context = "\n".join(
        [f"- {item['name']}: {item['url']} ({item.get('description', '')})" for item in niche_links]
    )

    prompt = (
        f"Write an SEO-optimized, in-depth article in English (approx 900 words) "
        f"focusing on the niche: '{selected_niche}'.\n"
        f"Include an engaging <h1> title, clear <h2> and <h3> subheadings, practical tips, "
        f"and naturally recommend these affiliate resources with clickable HTML <a> links:\n"
        f"{affiliate_context}\n"
        f"Return clean HTML inside <body> tags only (do not wrap in markdown code fences)."
    )
    gen_config = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    if GCP_PROJECT_ID:
        try:
            log_message(f"Connecting to Google AI Pro via Vertex AI ({GCP_PROJECT_ID} / {AI_MODEL})...")
            vertex_client = genai.Client(
                vertexai=True,
                project=GCP_PROJECT_ID,
                location=GCP_LOCATION,
            )
            response = vertex_client.models.generate_content(
                model=AI_MODEL,
                contents=prompt,
                config=gen_config,
            )
            if response and response.text:
                log_message(f"Article generated successfully via Vertex AI ({AI_MODEL})!")
                return response.text, selected_niche
        except Exception as e:
            log_message(f"Vertex AI generation warning: {e}. Trying API Key fallback...")

    if GEMINI_API_KEY and GEMINI_API_KEY != "your_actual_gemini_api_key_here":
        for model_name in [AI_MODEL, FALLBACK_MODEL]:
            try:
                log_message(f"Connecting to Gemini API ({model_name})...")
                api_client = genai.Client(api_key=GEMINI_API_KEY)
                response = api_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=gen_config,
                )
                if response and response.text:
                    log_message(f"Article generated successfully via API Key ({model_name})!")
                    return response.text, selected_niche
            except Exception as e:
                log_message(f"API Key generation error ({model_name}): {e}")

    return None, selected_niche


def load_manifest() -> list:
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_manifest(manifest: list):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def push_to_github_pages(commit_msg: str):
    if not AUTO_PUSH_PAGES:
        return
    try:
        subprocess.run(["git", "add", "docs/"], cwd=PROJECT_DIR, check=True, capture_output=True)
        status = subprocess.run(["git", "status", "--porcelain", "docs/"], cwd=PROJECT_DIR, capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=PROJECT_DIR, check=True, capture_output=True)
        remotes = config.get("system", {}).get("git_remotes", ["origin", "review"])
        for remote_name in remotes:
            res = subprocess.run(["git", "push", remote_name, "main"], cwd=PROJECT_DIR, capture_output=True, text=True)
            if res.returncode == 0:
                log_message(f"Published to GitHub Pages remote '{remote_name}'!")
            else:
                log_message(f"GitHub Pages push warning ({remote_name}): {res.stderr.strip()}")
    except Exception as e:
        log_message(f"GitHub Pages git push warning: {e}")


def publish_content(html_content: str, niche: str):
    if not html_content:
        log_message("No content to publish.")
        return False

    now = datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    date_str = now.strftime("%Y-%m-%d")
    title, excerpt, body_html = clean_html_and_extract_meta(html_content, niche)

    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or f"post-{timestamp_str}"
    filename = f"{now.strftime('%Y-%m-%d')}-{slug}.html"
    article_path = ARTICLES_DIR / filename

    full_page_html = wrap_article_page(title, excerpt, body_html, niche, date_str)
    with open(article_path, "w", encoding="utf-8") as f:
        f.write(full_page_html)
    log_message(f"Saved published article to {article_path}")

    manifest = load_manifest()
    manifest = [m for m in manifest if m.get("filename") != filename]
    manifest.insert(
        0,
        {
            "title": title,
            "excerpt": excerpt,
            "niche": niche,
            "date": date_str,
            "filename": filename,
        },
    )
    save_manifest(manifest)
    rebuild_site_index(manifest)

    articles_prefix = config.get("gcp", {}).get("gcs_articles_prefix", "articles")
    upload_to_gcs(article_path, f"{articles_prefix}/{filename}", content_type="text/html; charset=utf-8")

    push_to_github_pages(f"Publish article: {title}")

    if TARGET_API_URL and "your-blog-site.com" not in TARGET_API_URL:
        headers = {"Authorization": f"Bearer {TARGET_API_TOKEN}", "Content-Type": "application/json"}
        payload = {"title": title, "content": full_page_html, "status": DEFAULT_STATUS}
        try:
            response = requests.post(TARGET_API_URL, json=payload, headers=headers, timeout=30)
            if response.status_code in [200, 201]:
                log_message("Published successfully via external API!")
            else:
                log_message(f"External API publish failed: {response.status_code} - {response.text}")
        except Exception as e:
            log_message(f"External API connection error: {e}")

    return True


def migrate_existing_drafts():
    manifest = load_manifest()
    if manifest:
        return
    drafts = sorted(PROJECT_DIR.glob("draft_post_*.html"))
    for draft in drafts:
        raw = draft.read_text(encoding="utf-8")
        niche = "Smart Home Automation" if "smart home" in raw.lower() else "Developer Productivity Hacks"
        title, excerpt, body_html = clean_html_and_extract_meta(raw, niche)
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
        filename = f"{date_str}-{slug}.html"
        article_path = ARTICLES_DIR / filename
        full_page_html = wrap_article_page(title, excerpt, body_html, niche, date_str)
        article_path.write_text(full_page_html, encoding="utf-8")
        manifest.insert(0, {"title": title, "excerpt": excerpt, "niche": niche, "date": date_str, "filename": filename})
    if manifest:
        save_manifest(manifest)
        rebuild_site_index(manifest)


if __name__ == "__main__":
    log_message("=== Autonomous Pipeline Execution Started ===")
    migrate_existing_drafts()
    article, selected_niche = generate_article()
    success = publish_content(article, selected_niche)
    log_message("=== Pipeline Execution Finished ===")
    logs_prefix = config.get("gcp", {}).get("gcs_logs_prefix", "logs")
    upload_to_gcs(LOG_PATH, f"{logs_prefix}/pipeline.log", content_type="text/plain; charset=utf-8")
