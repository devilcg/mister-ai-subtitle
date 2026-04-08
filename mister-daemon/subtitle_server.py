#!/usr/bin/env python3
"""
MiSTer Subtitle Server
======================
- GET  /              → 폰 웹앱 서빙
- GET  /app.js        → 웹앱 JS 서빙
- POST /translate     → 이미지(base64) 수신 → AI API → 번역 → OSD + 응답
- GET  /config        → 현재 설정 확인
- POST /config        → 설정 저장 (provider, API Keys)

MiSTer 시작 시 자동 실행 (/media/fat/linux/user-startup.sh 에 추가):
  python3 /media/fat/Scripts/subtitle_server.py &
"""

import socket
import os
import json
import mimetypes
import ssl
import subprocess
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# MiSTer ARM Linux는 CA 번들이 없는 경우가 있으므로 SSL 검증 비활성화
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

CERT_FILE = Path("/media/fat/Scripts/subtitle_cert.pem")
KEY_FILE  = Path("/media/fat/Scripts/subtitle_key.pem")

def ensure_cert():
    if not CERT_FILE.exists() or not KEY_FILE.exists():
        print("[ssl] 자체 서명 인증서 생성 중...")
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(KEY_FILE),
            "-out", str(CERT_FILE),
            "-days", "3650", "-nodes",
            "-subj", "/CN=MiSTer"
        ], check=True, capture_output=True)
        print("[ssl] 인증서 생성 완료")

UNIX_SOCK   = "/tmp/mister_subtitle.sock"
HTTP_PORT   = 18765
CONFIG_FILE = Path("/media/fat/Scripts/subtitle_config.json")

_HERE      = Path(__file__).parent
STATIC_DIR = _HERE / "phone-app"
if not STATIC_DIR.exists():
    STATIC_DIR = _HERE.parent / "phone-app"


# ── 설정 로드/저장 ────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {"provider": "claude", "claude_api_key": "", "openai_api_key": ""}

def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ── MiSTer OSD 소켓 전송 ──────────────────────────────────────────────────────

def send_to_osd(text: str) -> bool:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(UNIX_SOCK)
        sock.sendall(text.encode("utf-8"))
        sock.close()
        return True
    except Exception as e:
        print(f"[osd] 소켓 전송 실패: {e}")
        return False


# ── 공통 프롬프트 ─────────────────────────────────────────────────────────────

TRANSLATE_PROMPT = """이 이미지는 레트로 게임 화면입니다.
화면에서 일본어 텍스트(대화, 메뉴, 자막 등)를 찾아 한국어로 번역하세요.

규칙:
1. 일본어 텍스트가 없으면 {"found":false} 만 반환
2. 있으면 {"found":true,"original":"원문","translation":"한국어 번역"} 반환
3. 캐릭터 이름은 음역 유지 (예: 루피, 나루토)
4. JSON만 반환, 설명 없음"""


# ── Claude API 호출 ───────────────────────────────────────────────────────────

def call_claude(api_key: str, image_b64: str) -> dict:
    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 256,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64
                }},
                {"type": "text", "text": TRANSLATE_PROMPT},
            ]
        }]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
        body = json.loads(resp.read())

    text = body["content"][0]["text"].strip()
    return _parse_json_result(text)


# ── OpenAI API 호출 ───────────────────────────────────────────────────────────

def call_openai(api_key: str, image_b64: str) -> dict:
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 256,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{image_b64}",
                    "detail": "low"
                }},
                {"type": "text", "text": TRANSLATE_PROMPT},
            ]
        }]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
        body = json.loads(resp.read())

    text = body["choices"][0]["message"]["content"].strip()
    return _parse_json_result(text)


# ── 공통 JSON 파싱 ────────────────────────────────────────────────────────────

def _parse_json_result(text: str) -> dict:
    match_start = text.find("{")
    match_end   = text.rfind("}") + 1
    if match_start == -1:
        return {"found": False}
    return json.loads(text[match_start:match_end])


# ── AI 번역 디스패처 ──────────────────────────────────────────────────────────

def call_ai(cfg: dict, image_b64: str) -> dict:
    provider = cfg.get("provider", "claude")
    if provider == "openai":
        api_key = cfg.get("openai_api_key", "")
        if not api_key:
            raise ValueError("OpenAI API Key 미설정")
        return call_openai(api_key, image_b64)
    else:
        api_key = cfg.get("claude_api_key", "")
        if not api_key:
            raise ValueError("Claude API Key 미설정")
        return call_claude(api_key, image_b64)


# ── 정적 파일 서빙 ────────────────────────────────────────────────────────────

def serve_static(handler, rel_path: str):
    target = (STATIC_DIR / rel_path).resolve()
    try:
        target.relative_to(STATIC_DIR.resolve())
    except ValueError:
        handler.send_response(403)
        handler.end_headers()
        return

    if not target.exists() or not target.is_file():
        handler.send_response(404)
        handler.end_headers()
        handler.wfile.write(b"Not found")
        return

    mime, _ = mimetypes.guess_type(str(target))
    data = target.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", mime or "application/octet-stream")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(data)


# ── HTTP 핸들러 ───────────────────────────────────────────────────────────────

def _mask(key: str) -> str:
    return (key[:8] + "...") if key else ""

class SubtitleHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[HTTP] {args[0]} {args[1]}")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            serve_static(self, "index.html")
        elif path in ("/app.js", "/manifest.json"):
            serve_static(self, path.lstrip("/"))
        elif path == "/config":
            cfg = load_config()
            safe = {
                "provider":       cfg.get("provider", "claude"),
                "claude_api_key": _mask(cfg.get("claude_api_key", "")),
                "openai_api_key": _mask(cfg.get("openai_api_key", "")),
            }
            self._json(200, safe)
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        try:
            data = json.loads(body)
        except Exception:
            self._json(400, {"error": "invalid json"})
            return

        # ── POST /config ──
        if self.path == "/config":
            cfg = load_config()
            if "provider" in data:
                cfg["provider"] = data["provider"]
            if "claude_api_key" in data and data["claude_api_key"].strip():
                cfg["claude_api_key"] = data["claude_api_key"].strip()
            if "openai_api_key" in data and data["openai_api_key"].strip():
                cfg["openai_api_key"] = data["openai_api_key"].strip()
            save_config(cfg)
            print(f"[config] 저장됨 — provider={cfg['provider']}")
            self._json(200, {"ok": True, "provider": cfg["provider"]})
            return

        # ── POST /translate ──
        if self.path == "/translate":
            image_b64 = data.get("image", "").strip()
            if not image_b64:
                self._json(400, {"error": "image required"})
                return

            cfg = load_config()

            try:
                result = call_ai(cfg, image_b64)
            except ValueError as e:
                self._json(503, {"error": str(e)})
                return
            except urllib.error.HTTPError as e:
                err = e.read().decode("utf-8", errors="replace")
                print(f"[ai] API 오류 {e.code}: {err}")
                self._json(502, {"error": f"AI API {e.code}"})
                return
            except Exception as e:
                print(f"[ai] 오류: {e}")
                self._json(502, {"error": str(e)})
                return

            if result.get("found"):
                translation = result.get("translation", "")
                send_to_osd(translation)
                print(f"[subtitle] {result.get('original','')} → {translation}")
                self._json(200, result)
            else:
                self._json(200, {"found": False})
            return

        self.send_response(404)
        self.end_headers()

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "?.?.?.?"

    cfg = load_config()
    provider = cfg.get("provider", "claude")
    claude_key = "설정됨" if cfg.get("claude_api_key") else "미설정"
    openai_key = "설정됨" if cfg.get("openai_api_key") else "미설정"

    ensure_cert()

    print(f"\n=== MiSTer Subtitle Server ===")
    print(f"  폰 웹앱  : https://{ip}:{HTTP_PORT}/")
    print(f"  Provider : {provider}")
    print(f"  Claude   : {claude_key}")
    print(f"  OpenAI   : {openai_key}")
    print(f"  정적파일 : {STATIC_DIR}")
    print(f"  ※ 처음 접속 시 '안전하지 않음' 경고 → 고급 → 계속 선택")
    print(f"==============================\n")

    httpd = HTTPServer(("0.0.0.0", HTTP_PORT), SubtitleHandler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
