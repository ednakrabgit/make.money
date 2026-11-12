import os
import yaml
import requests
import random
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
MAX_OUTPUT_TOKENS = config["ai_engine"].get("max_output_tokens", 2000)

NICHES = config["content_settings"]["niches"]
DEFAULT_STATUS = config["content_settings"]["default_post_status"]
LOG_PATH = PROJECT_DIR / config["logging"]["log_path"]
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


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


def generate_article():
    selected_niche = random.choice(NICHES)
    prompt = (
        f"Write an SEO-optimized, in-depth article in English (approx 900 words) "
        f"focusing on the niche: '{selected_niche}'. "
        f"Include an engaging title, clear subheadings, and a natural recommendation section "
        f"with placeholder affiliate links. Format output in clean HTML."
    )
    gen_config = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    # 1. Primary: Vertex AI on GCP project (supports gemini-2.5-pro with GCP credits)
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
                return response.text
        except Exception as e:
            log_message(f"Vertex AI generation warning: {e}. Trying API Key fallback...")

    # 2. Fallback: Gemini Developer API Key
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
                    return response.text
            except Exception as e:
                log_message(f"API Key generation error ({model_name}): {e}")

    return None


def publish_content(html_content):
    if not html_content:
        log_message("No content to publish.")
        return False

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = PROJECT_DIR / f"draft_post_{timestamp_str}.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    log_message(f"Saved local draft to {output_file}")

    # Upload generated HTML draft to GCS
    articles_prefix = config.get("gcp", {}).get("gcs_articles_prefix", "articles")
    upload_to_gcs(
        output_file,
        f"{articles_prefix}/{output_file.name}",
        content_type="text/html; charset=utf-8",
    )

    if not TARGET_API_URL or "your-blog-site.com" in TARGET_API_URL:
        log_message("Target blog API not configured yet; using local + GCS storage.")
        return True

    headers = {
        "Authorization": f"Bearer {TARGET_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "title": f"Automated Insight - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": html_content,
        "status": DEFAULT_STATUS,
    }
    try:
        response = requests.post(TARGET_API_URL, json=payload, headers=headers, timeout=30)
        if response.status_code in [200, 201]:
            log_message("Published successfully via API!")
            return True
        else:
            log_message(f"Publish failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        log_message(f"API connection error: {e}")
        return False


if __name__ == "__main__":
    log_message("=== Autonomous Pipeline Execution Started ===")
    article = generate_article()
    success = publish_content(article)
    log_message("=== Pipeline Execution Finished ===")
    logs_prefix = config.get("gcp", {}).get("gcs_logs_prefix", "logs")
    upload_to_gcs(LOG_PATH, f"{logs_prefix}/pipeline.log", content_type="text/plain; charset=utf-8")
