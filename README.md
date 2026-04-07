# MiSTer AI 실시간 자막 번역

레트로 게임의 **일본어 자막을 실시간으로 한국어로 번역**해 MiSTer OSD에 표시합니다.
폰 카메라로 TV 화면을 찍으면 Claude 또는 OpenAI가 번역 → WiFi로 MiSTer에 전송 → 게임 화면 위에 자막이 뜹니다.

![구조도](https://i.imgur.com/placeholder.png)

---

## 동작 원리

```
[폰 브라우저]                    [MiSTer FPGA]
카메라 프레임 캡처
    ↓
POST /translate (base64)  →  subtitle_server.py (:18765)
                                    ↓
                            Claude / OpenAI Vision API
                                    ↓
                            /tmp/mister_subtitle.sock
                                    ↓
                            Main_MiSTer subtitle_poll()
                                    ↓
                            Info() → OSD 자막 5초 표시
```

- **폰**: 카메라 프레임을 1.5초마다 캡처해 MiSTer로 전송만 함
- **MiSTer**: AI API 호출 + OSD 표시 모두 처리 (API Key가 MiSTer에만 보관)
- **AI 제공자**: Claude Haiku 또는 OpenAI GPT-4o-mini 선택 가능

---

## 파일 구조

```
mister-ai-subtitle/
├── mister-src/          ← Main_MiSTer에 추가할 C++ 소스
│   ├── subtitle.h
│   └── subtitle.cpp
├── mister-daemon/       ← MiSTer SD카드에 복사할 Python 서버
│   └── subtitle_server.py
└── phone-app/           ← 폰 브라우저에서 여는 웹앱 (서버가 자동 서빙)
    ├── index.html
    ├── app.js
    └── manifest.json
```

---

## 설치

### 1단계 — Main_MiSTer 빌드 (C++ 패치)

`mister-src/` 안의 파일 2개를 Main_MiSTer 소스 루트에 복사합니다.

```bash
cp mister-src/subtitle.h   /path/to/Main_MiSTer/
cp mister-src/subtitle.cpp /path/to/Main_MiSTer/
```

`main.cpp`에 3줄 추가합니다:

```cpp
// 상단 include 목록에 추가
#include "subtitle.h"

// subtitle_init() — offload_start() 바로 아래에 추가
subtitle_init();

// subtitle_poll() — 메인 루프 안, OsdUpdate() 앞에 추가
subtitle_poll();
```

그 후 평소대로 빌드하고 MiSTer에 올립니다.

> **참고**: `Info()` 함수는 `menu.cpp`에 이미 구현되어 있습니다.

---

### 2단계 — Python 서버 설치

MiSTer SD카드에 복사:

```
/media/fat/Scripts/subtitle_server.py
```

`phone-app/` 폴더도 같이 복사 (서버가 정적 파일 서빙):

```
/media/fat/Scripts/phone-app/index.html
/media/fat/Scripts/phone-app/app.js
/media/fat/Scripts/phone-app/manifest.json
```

> 실제 배포 경로는 `subtitle_server.py` 상단의 `CONFIG_FILE`, `STATIC_DIR` 경로를 참고하세요.

---

### 3단계 — 부팅 시 자동 시작

MiSTer의 `/media/fat/linux/user-startup.sh`에 추가:

```bash
python3 /media/fat/Scripts/subtitle_server.py &
```

---

### 4단계 — API Key 설정

MiSTer와 폰이 같은 WiFi에 연결된 상태에서:

1. 폰 브라우저에서 `http://[MiSTer IP]:18765` 접속
2. **설정 탭** 열기
3. MiSTer IP 입력 → **확인** 버튼
4. 사용할 AI 선택 (`🟣 Claude` 또는 `🟢 OpenAI`)
5. 해당 API Key 입력 → **저장**

API Key는 MiSTer에만 저장됩니다 (`/media/fat/Scripts/subtitle_config.json`).

---

## 사용법

1. MiSTer와 폰이 같은 WiFi
2. MiSTer 부팅 → 서버 자동 시작
3. 폰 브라우저에서 `http://[MiSTer IP]:18765` 접속
4. **카메라 탭** → ▶ 시작
5. 카메라를 TV 화면에 향하기
6. 일본어 감지 시 MiSTer OSD에 한국어 자막 5초 표시

---

## AI 제공자 비교

| | Claude Haiku | OpenAI GPT-4o-mini |
|---|---|---|
| 모델 | claude-haiku-4-5-20251001 | gpt-4o-mini |
| 비용 (컷당) | ~$0.001 | ~$0.001 |
| 1시간 (1.5초 간격) | ~$7~10 | ~$7~10 |
| API 키 발급 | [console.anthropic.com](https://console.anthropic.com) | [platform.openai.com](https://platform.openai.com) |

---

## 요구 사항

- MiSTer FPGA (ARM Linux, Python 3.6+)
- 같은 WiFi의 스마트폰 (Chrome/Safari)
- Anthropic 또는 OpenAI API Key

---

## 라이선스

MIT
