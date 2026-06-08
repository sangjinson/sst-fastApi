# 경기도 스마트 여행 플래너 — FastAPI AI Server

> **팀명**: 식스센스 (SixSense) · GPT-4o 연동 AI 여행 일정 생성 서버
> **배포사이트**: https://sstour.cloud/

Spring Boot 백엔드와 OpenAI GPT-4o 사이에서 동작하는 **FastAPI 중간 서버**입니다.
사용자가 선택한 지역·기간·테마 조건을 기반으로 GPT-4o에게 프롬프트를 전달하고, 동선 최적화된 여행 일정을 생성하여 반환합니다.

---

## 목차

- [프로젝트 소개](#프로젝트-소개)
- [기술 스택](#기술-스택)
- [시스템 흐름](#시스템-흐름)
- [주요 기능](#주요-기능)
- [API 엔드포인트](#api-엔드포인트)
- [요청 / 응답 예시](#요청--응답-예시)
- [프로젝트 구조](#프로젝트-구조)
- [시작하기](#시작하기)
- [환경 변수](#환경-변수)

---

## 프로젝트 소개

FastAPI 서버는 Spring Boot 백엔드로부터 여행 조건을 수신하고,
**Pandas**로 경기도 장소 데이터를 전처리한 뒤 **GPT-4o**에 최적화된 프롬프트를 전달합니다.
GPT-4o의 응답을 구조화하여 Spring Boot로 반환하는 **AI 오케스트레이션 레이어** 역할을 합니다.

| 구분 | 내용 |
|------|------|
| 서버 포트 | `8090` (localhost, Spring → 내부 통신) |
| 외부 노출 | ❌ (NGINX를 통해 직접 노출하지 않음) |
| AI 모델 | OpenAI GPT-4o |

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| Language | Python 3.11+ |
| Framework | FastAPI |
| AI | OpenAI API (GPT-4o) |
| 데이터 처리 | Pandas |
| 서버 | Uvicorn (ASGI) |
| 유효성 검증 | Pydantic v2 |
| HTTP 클라이언트 | httpx (비동기) |
| 환경 변수 | python-dotenv |

---

## 시스템 흐름

```
[React Frontend]
      │  사용자 조건 선택
      │  (지역 / 기간 / 테마)
      ▼
[Spring Boot :8080]
      │  POST /api/schedules/generate
      │  조건 데이터 전달
      ▼
[FastAPI :8090]  ◄── 이 레포지토리
      │
      ├─ 1. Pydantic으로 요청 유효성 검증
      │
      ├─ 2. Pandas로 경기도 장소 데이터 필터링
      │      (지역 코드 & 테마 조건 매칭)
      │
      ├─ 3. GPT-4o 프롬프트 구성 및 API 호출
      │
      └─ 4. 응답 파싱 → 구조화된 JSON 반환
                │
                ▼
      [Spring Boot] → DB 저장 → [React] 화면 렌더링
```

---

## 주요 기능

### AI 여행 일정 생성
사용자의 선택 조건(지역, 여행 기간, 테마)을 기반으로 GPT-4o가 **동선 최적화된 일정**을 자동 생성합니다.

**지원 여행 기간**
- 당일 여행
- 1박 2일
- 2박 3일

**지원 테마** (최소 1개 ~ 최대 3개 선택)
- 축제/행사, 체험, 식도락, 역사, 레저, 테마파크

### Pandas 데이터 전처리
- 경기도 공공 API 기반 장소 데이터 로드 및 전처리
- 지역 코드·카테고리·테마 필터링으로 GPT-4o 컨텍스트 최적화
- 불필요한 토큰 소비 방지를 위한 데이터 경량화

### 구조화된 응답 반환
GPT-4o의 자연어 응답을 **일차별 타임라인 구조**의 JSON으로 파싱하여 Spring Boot에 반환합니다.

---

## API 엔드포인트

### `POST /generate-schedule`

Spring Boot 백엔드에서 AI 일정 생성 요청 시 호출됩니다.

**Request Body**

```json
{
  "region": "가평군",
  "region_code": 31820,
  "travel_type": "1박2일",
  "start_date": "2026-07-05",
  "end_date": "2026-07-06",
  "themes": ["레저", "식도락"]
}
```

**Response Body**

```json
{
  "schedule_title": "가평 레저 & 식도락 1박2일 여행",
  "region": "가평군",
  "total_days": 2,
  "days": [
    {
      "day": 1,
      "date": "2026-07-05",
      "places": [
        {
          "order": 1,
          "place_id": "126535",
          "place_name": "자라섬",
          "category": "볼거리",
          "address": "경기도 가평군 가평읍 달전리",
          "lat": "37.7983",
          "lng": "127.5104",
          "recommended_time": "10:00",
          "duration_minutes": 120,
          "description": "한국 최대 캠핑지로 유명한 섬으로 자전거 라이딩과 수상 레저 활동을 즐길 수 있습니다."
        }
      ]
    }
  ]
}
```

---

### `GET /health`

서버 상태 확인용 헬스체크 엔드포인트입니다.

```json
{
  "status": "ok",
  "model": "gpt-4o",
  "version": "1.0.0"
}
```

---

## 요청 / 응답 예시

### 당일 여행 요청 예시

```bash
curl -X POST http://localhost:8090/generate-schedule \
  -H "Content-Type: application/json" \
  -d '{
    "region": "수원시",
    "region_code": 31030,
    "travel_type": "당일여행",
    "start_date": "2026-08-10",
    "end_date": "2026-08-10",
    "themes": ["역사", "식도락"]
  }'
```

---

## 프로젝트 구조

```
gyeonggi-travel-fastapi/
├── main.py                  # FastAPI 앱 진입점
├── requirements.txt
├── .env.example
│
├── routers/
│   └── schedule.py          # /generate-schedule 라우터
│
├── services/
│   ├── gpt_service.py       # GPT-4o API 호출 & 프롬프트 관리
│   └── data_service.py      # Pandas 장소 데이터 필터링
│
├── schemas/
│   ├── request.py           # Pydantic 요청 모델
│   └── response.py          # Pydantic 응답 모델
│
├── data/
│   └── gyeonggi_places.csv  # 경기도 장소 데이터 (공공 API 기반)
│
└── utils/
    ├── prompt_builder.py    # GPT 프롬프트 템플릿 관리
    └── response_parser.py   # GPT 응답 JSON 파싱
```

---

## 시작하기

### 사전 요구사항

- Python 3.11+
- OpenAI API Key

### 설치 및 실행

```bash
# 1. 레포지토리 클론
git clone https://github.com/your-org/gyeonggi-travel-fastapi.git
cd gyeonggi-travel-fastapi

# 2. 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# 3. 패키지 설치
pip install -r requirements.txt

# 4. 환경 변수 파일 생성
cp .env.example .env
# .env 파일에 OPENAI_API_KEY 입력

# 5. 서버 실행
uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

서버 실행 후 `http://localhost:8090/docs` 에서 Swagger UI를 확인할 수 있습니다.

### 서비스 환경 (배포)

```bash
# 백그라운드 실행 (프로덕션)
nohup uvicorn main:app --host 0.0.0.0 --port 8090 &

# 또는 systemd 서비스로 등록 권장
```

---

## 환경 변수

`.env` 파일에 아래 값들을 설정하세요.

```env
# OpenAI
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o
OPENAI_MAX_TOKENS=2000
OPENAI_TEMPERATURE=0.7

# 서버 설정
APP_HOST=0.0.0.0
APP_PORT=8090

# 데이터 경로
PLACES_DATA_PATH=./data/gyeonggi_places.csv
```

### `requirements.txt`

```txt
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
openai>=1.30.0
pandas>=2.2.0
pydantic>=2.0.0
python-dotenv>=1.0.0
httpx>=0.27.0
```

---

## Spring Boot 연동 설정

Spring Boot 백엔드의 `application.yml`에 FastAPI 서버 주소를 설정합니다.

```yaml
fastapi:
  base-url: http://localhost:8090
  endpoints:
    generate-schedule: /generate-schedule
```

Spring Boot에서는 `RestTemplate` 또는 `WebClient`를 사용하여 FastAPI를 호출합니다.

```java
// 예시: FastAPI 클라이언트 코드
@Service
public class FastApiClient {

    private final RestTemplate restTemplate;

    @Value("${fastapi.base-url}")
    private String fastApiBaseUrl;

    public ScheduleResponse generateSchedule(ScheduleRequest request) {
        String url = fastApiBaseUrl + "/generate-schedule";
        return restTemplate.postForObject(url, request, ScheduleResponse.class);
    }
}
```

---

> **관련 레포지토리**
> - [Frontend (React)](https://github.com/mojitt/sst-front)
> - [Backend (Spring)](https://github.com/mojitt/sst-back)
