# 🎮 MiSTer RPG 일본어 자막 실시간 AI 번역

**일본어만 나오는 RPG, 이제 못 하는 척 그만.** 폰 카메라를 TV에 대면 AI가 즉시 한국어로 번역해 MiSTer OSD에 자막을 띄워줍니다.

별도 PC 불필요. 별도 앱 설치 불필요. WiFi만 있으면 됩니다.

---

## 동작 원리

```
[폰 브라우저]                    [MiSTer FPGA]
카메라 프레임 캡처
    ↓
POST /translate (base64)  →  subtitle_server.py (:18765)
                                    ↓
                            Claude / OpenAI Vision API
                            (API Key는 MiSTer에만 저장)
                                    ↓
                            /tmp/mister_subtitle.sock
                                    ↓
                            subtitle_poll() in main loop
                                    ↓
                            Info() → OSD 자막 5초 표시
```

- **폰**: 카메라 프레임만 전송 (API Key 없음, CORS 문제 없음)
- **MiSTer**: AI API 호출 + OSD 표시 모두 처리
- **AI 제공자**: Claude Haiku 또는 OpenAI GPT-4o-mini 선택 가능

---

## 파일 구조

```
mister-ai-subtitle/
├── mister-src/              ← Main_MiSTer에 추가할 C++ 소스
│   ├── subtitle.h
│   └── subtitle.cpp
├── mister-daemon/           ← MiSTer SD카드에 복사할 Python 서버
│   └── subtitle_server.py
└── phone-app/               ← 폰 브라우저 웹앱 (서버가 자동 서빙)
    ├── index.html
    ├── app.js
    └── manifest.json
```

---

## 설치

### 0단계 — 한글 OSD 빌드 설치 (필수)

OSD에 한국어 자막을 표시하려면 한글 폰트가 적용된 Main_MiSTer 빌드가 필요합니다.

👉 **[devilcg/Main_MiSTer](https://github.com/devilcg/Main_MiSTer)** — 한글 OSD 지원 포크

릴리즈 페이지에서 `MiSTer` 바이너리를 받아 SD카드에 적용하거나, 직접 빌드하세요.

---

### 1단계 — Main_MiSTer 빌드 (C++ 패치)

`mister-src/` 파일 2개를 Main_MiSTer 소스 루트에 복사합니다:

```bash
cp mister-src/subtitle.h   /path/to/Main_MiSTer/
cp mister-src/subtitle.cpp /path/to/Main_MiSTer/
```

`main.cpp`에 3줄 추가합니다:

```cpp
// ① 상단 include 목록에 추가
#include "subtitle.h"

// ② subtitle_init() — offload_start() 바로 아래
subtitle_init();

// ③ subtitle_poll() — 메인 루프 안, OsdUpdate() 앞
subtitle_poll();
```

평소대로 빌드 후 MiSTer에 올립니다.

> `Info()` 함수는 `menu.cpp`에 이미 있습니다. 게임 실행 중(OSD 닫힌 상태)에만 자막이 표시되며, OSD 메뉴를 열면 자막은 숨겨집니다.

---

### 2단계 — 파일 복사

SD카드 경로에 복사:

```
/media/fat/Scripts/subtitle_server.py
/media/fat/Scripts/phone-app/index.html
/media/fat/Scripts/phone-app/app.js
/media/fat/Scripts/phone-app/manifest.json
```

---

### 3단계 — 부팅 시 자동 시작

`/media/fat/linux/user-startup.sh`에 추가:

```bash
python3 /media/fat/Scripts/subtitle_server.py &
```

---

### 4단계 — API Key 설정

MiSTer와 폰이 같은 WiFi에 연결된 상태에서:

1. 폰 브라우저에서 `http://[MiSTer IP]:18765` 접속
2. **설정 탭** 열기
3. MiSTer IP 입력 → **확인** 버튼으로 연결 테스트
4. AI 선택 (`🟣 Claude` 또는 `🟢 OpenAI`)
5. 해당 API Key 입력 → **저장**

API Key는 MiSTer 내부(`/media/fat/Scripts/subtitle_config.json`)에만 저장됩니다.

---

## 사용법

1. MiSTer 부팅 → 서버 자동 시작
2. 폰 브라우저에서 `http://[MiSTer IP]:18765` 접속
3. **카메라 탭** → ▶ 시작
4. 카메라를 TV 화면에 향하기
5. 일본어 감지 시 MiSTer OSD에 한국어 자막 5초 표시

---

## AI 제공자 비교

| | Claude Haiku | OpenAI GPT-4o-mini |
|---|---|---|
| 모델 | claude-haiku-4-5-20251001 | gpt-4o-mini |
| 비용 (컷당) | ~$0.001 | ~$0.001 |
| 1시간 (1.5초 간격) | ~$7~10 | ~$7~10 |
| API 키 발급 | [console.anthropic.com](https://console.anthropic.com) | [platform.openai.com](https://platform.openai.com) |

---

## 트러블슈팅

**자막이 안 보여요**
- OSD 메뉴가 열려 있으면 자막이 표시되지 않습니다 (정상 동작)
- MiSTer IP가 올바른지, 서버가 실행 중인지 확인

**SSL 오류 (`CERTIFICATE_VERIFY_FAILED`)**
- `subtitle_server.py`는 MiSTer ARM Linux의 CA 번들 부재를 자동으로 우회합니다

**번역 없이 `found: false` 만 반환**
- 이미지가 너무 어둡거나 텍스트가 작을 수 있습니다
- 캡처 간격을 늘려보세요 (설정 탭 → 2.5초 / 4초)

---

## 요구 사항

- MiSTer FPGA (ARM Linux, Python 3 기본 포함)
- **[MiSTer 한글 OSD](https://github.com/devilcg/Main_MiSTer)** — 한국어 자막을 OSD에 표시하려면 한글 폰트 지원 빌드가 필요합니다
- 같은 WiFi의 스마트폰 (Chrome / Safari)
- Anthropic 또는 OpenAI API Key

---

## 라이선스

MIT
