# 경기도 스마트 여행 플래너 — FastAPI AI Server

> **팀명**: 머지크루  **팀원**: 김영훈, 김지태, 노송현, 소제우, 손상진, 한상인  
> **배포도메인**: https://sstour.cloud/

Spring Boot 백엔드와 OpenAI GPT-4o 사이에서 동작하는 **FastAPI 중간 서버**입니다.
사용자가 선택한 지역·기간·테마 조건을 기반으로 GPT-4o에게 프롬프트를 전달하고, 동선 최적화된 여행 일정을 생성하여 반환합니다.

---

## 목차

- [프로젝트 소개](#프로젝트-소개)
- [기술 스택](#기술-스택)
- [시스템 흐름](#시스템-흐름)
- [주요 기능](#주요-기능)
- [API 엔드포인트](#api-엔드포인트)
- [시작하기](#시작하기)
- [환경 변수](#환경-변수)

---

## 프로젝트 소개

FastAPI 서버는 Spring Boot 백엔드로부터 여행 조건을 수신하고,
**Pandas**로 장소 데이터를 처리한 뒤 **GPT-4o**에 프롬프트를 전달합니다.
GPT-4o의 응답을 구조화하여 Spring Boot로 반환하는 역할을 합니다.

| 구분 | 내용 |
|------|------|
| 서버 주소 | `localhost:8090` |
| AI 모델 | OpenAI GPT-4o |

---

## 기술 스택

| 분류 | 기술 | 버전 |
|------|------|------|
| Language | Python | 3.11+ |
| Framework | FastAPI | 0.136.1 |
| ASGI 서버 | Uvicorn | 0.46.0 |
| AI | OpenAI API (GPT-4o) | 2.36.0 |
| 유효성 검증 | Pydantic | 2.13.4 |
| HTTP 클라이언트 | httpx | 0.28.1 |
| HTTP 클라이언트 | requests | 2.33.1 |
| 환경 변수 | python-dotenv | 1.2.2 |
| 웹 프레임워크 기반 | Starlette | 1.0.0 |

---

## 시스템 흐름

```
[React Frontend]
      │  지역 / 기간 / 테마 선택
      ▼
[Spring Boot]
      │  GET /ai/travel/plan 호출
      ▼
[FastAPI :8090]
      │
      ├─ 1. Spring Boot에 장소 목록 요청
      │      GET /api/ai/travel/list (region, themes)
      │
      ├─ 2. GPT-4o 프롬프트 구성 및 일정 생성 요청
      │
      ├─ 3. 응답 후처리
      │      - 유효하지 않은 placeId 제거
      │      - 이미지 없는 장소 교체
      │      - 동선 클러스터링 (중심 좌표 기준 15km 초과 장소 교체)
      │      - 슬롯 타입별 순서 재정렬
      │
      └─ 4. 결과 반환
      ▼
[Spring Boot] → [React Frontend]
```

---

## 주요 기능

### AI 여행 일정 생성
- 지역·여행 기간·테마 조건을 기반으로 GPT-4o가 동선 최적화된 일정 자동 생성

**지원 여행 기간**
- 당일 여행 / 1박 2일 / 2박 3일

**지원 테마** (최소 1개 ~ 최대 3개)
- 축제/행사, 체험, 식도락, 역사, 레저, 테마파크

### 응답 후처리
- 유효하지 않은 placeId 제거
- 이미지 없는 장소를 동일 카테고리·필터 내 이미지 있는 장소로 교체
- Haversine 공식 기반 동선 클러스터링 (중심 좌표 기준 15km 초과 장소 자동 교체)
- 슬롯 타입(테마·먹거리·카페·볼거리·숙소)별 순서 재정렬
  
### 로깅
- 날짜별 로그 파일 생성 (`logs/fastapi.log.YYYY-MM-DD`)
- 매일 자정 교체, 30일치 보관

---

## API 엔드포인트

### `GET /ai/travel/plan`

Spring Boot에서 AI 일정 생성 요청 시 호출됩니다.

**Query Parameters**

| 파라미터 | 설명 |
|---------|------|
| `region` | 여행 지역명 |
| `days` | 여행 일수 |
| `start_date` | 여행 시작일 |
| `end_date` | 여행 종료일 |
| `themes` | 선택 테마 목록 |

**Response**

```json
{
  "success": true,
  "data": "일차별 장소 목록"
}
```

---

## 시작하기

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

# 5. 서버 실행
uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

---

## 환경 변수

```env
OPENAI_API_KEY=your_openai_api_key
```

### `requirements.txt`

```txt
fastapi==0.136.1
uvicorn==0.46.0
openai==2.36.0
pandas==3.0.2
numpy==2.4.4
pydantic==2.13.4
pydantic_core==2.46.4
httpx==0.28.1
requests==2.33.1
python-dotenv==1.2.2
starlette==1.0.0
python-dateutil==2.9.0.post0
tzdata==2026.2
anyio==4.13.0
certifi==2026.4.22
charset-normalizer==3.4.7
click==8.3.3
colorama==0.4.6
distro==1.9.0
h11==0.16.0
httpcore==1.0.9
idna==3.14
jiter==0.14.0
six==1.17.0
sniffio==1.3.1
tqdm==4.67.3
typing_extensions==4.15.0
urllib3==2.7.0
```

---

> **관련 레포지토리**
> - [Frontend (React)](https://github.com/mojitt/sst-front)
> - [Backend (Spring)](https://github.com/mojitt/sst-back)
