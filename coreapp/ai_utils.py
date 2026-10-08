import json
import os
import re
import requests
from .models import AIConfig

GROQ_MODEL = "openai/gpt-oss-120b"


def get_ai_config(tipe):
    """Return the requested config, falling back to the other analysis config."""
    config = AIConfig.objects.filter(tipe=tipe).first()
    if config:
        return config
    return AIConfig.objects.filter(tipe="kmeans" if tipe == "ahc" else "ahc").first()


def request_ai_completion(prompt, tipe, timeout=60):
    """Send a prompt through the configured Gemini or Groq provider."""
    config = get_ai_config(tipe)
    provider = (getattr(config, "provider", "gemini") or "gemini").lower()
    db_key = config.api_key.strip() if config and config.api_key else ""
    env_name = "GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY"
    api_key = db_key or os.environ.get(env_name, "").strip()

    if not api_key:
        raise ValueError(f"API Key {provider.title()} tidak ditemukan di database maupun .env")

    if provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"

        system_prompt = (
            "You are a helpful assistant that ONLY responds with valid JSON. "
            "Never write any explanation, markdown, or text outside the JSON. "
            "Output pure JSON only. Never use placeholder values such as '...', 'N/A', "
            "or '...'; every field must contain a concrete answer based on the user data."
        )

        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.05,
            "max_tokens": 2500,          # dinaikkan biar tidak terpotong
            # JANGAN pakai response_format dulu (sering gagal di struktur kompleks)
            # "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    else:
        # Gemini
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 2500,
            },
        }
        headers = {
            "X-goog-api-key": api_key,
            "Content-Type": "application/json",
        }

    response = requests.post(url, headers=headers, json=payload, timeout=timeout)

    try:
        response_data = response.json()
    except ValueError:
        response_data = {}

    if response.status_code != 200:
        error_msg = (
            response_data.get("error", {}).get("message")
            or response_data.get("error", {}).get("status")
            or f"Provider AI gagal (HTTP {response.status_code})"
        )

        # Tangkap error JSON validation dari Groq
        if "Failed to validate JSON" in str(error_msg) or "failed_generation" in str(response_data):
            # Ambil failed_generation kalau ada (berguna untuk debug)
            failed = response_data.get("error", {}).get("failed_generation") or ""
            raise RuntimeError(
                "Model gagal menghasilkan JSON valid.\n"
                f"Detail: {error_msg}\n"
                f"Failed generation preview: {str(failed)[:300]}"
            )

        if response.status_code == 429:
            raise RuntimeError(
                "Batas token / rate limit tercapai. Silakan tunggu beberapa detik lalu coba lagi."
            )

        raise RuntimeError(str(error_msg))

    if provider == "groq":
        choices = response_data.get("choices") or []
        if not choices:
            raise RuntimeError("Groq tidak memberikan jawaban (choices kosong).")

        message = choices[0].get("message") or {}
        content = (
            message.get("content")
            or message.get("reasoning")
            or choices[0].get("text")
            or ""
        )

        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )

        content = str(content).strip()
        if not content:
            raise RuntimeError(
                "Groq mengembalikan jawaban kosong. Coba naikkan max_tokens atau sederhanakan prompt."
            )
        return content

    # Gemini
    candidates = response_data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini tidak memberikan jawaban (candidates kosong).")

    try:
        text = candidates[0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Struktur respons Gemini tidak dikenali.")

    text = str(text).strip()
    if not text:
        raise RuntimeError("Gemini mengembalikan jawaban kosong.")
    return text


def parse_ai_json(raw_text: str):
    """
    Parse JSON dari jawaban AI (Groq / Gemini).
    Sangat robust terhadap markdown, teks tambahan, dll.
    """
    if raw_text is None:
        raise ValueError("Provider AI mengembalikan None.")

    cleaned = str(raw_text).strip()
    if not cleaned:
        raise ValueError("Provider AI mengembalikan jawaban kosong.")

    # Hapus markdown code fence
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

    # Coba parse langsung
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Cari object/array dengan regex
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: ambil dari { sampai }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass

    # Gagal → tampilkan preview
    preview = cleaned[:600].replace("\n", " ")
    raise ValueError(
        f"Gagal memproses jawaban AI. Format tidak sesuai.\n"
        f"Preview jawaban AI:\n{preview}"
    )