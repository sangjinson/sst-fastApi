from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from ai.ai_client import request_travel_plan
from api.data_client import fetch_place_list

import uvicorn
import json
import math
import logging
import os


# =========================================================
# 환경변수 로드
# =========================================================
load_dotenv()


# =========================================================
# 로그 설정
# =========================================================
os.makedirs("logs", exist_ok=True)

# 로그 포맷
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# 파일 핸들러 - 10MB 초과 시 최대 5개까지 롤링
file_handler = RotatingFileHandler(
    "/home/sst/logs/fastapi.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(formatter)

# 콘솔 핸들러
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# 앱 전용 로거
logger = logging.getLogger("fastapi_app")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# uvicorn 접속 로그 - 기존 핸들러 제거 후 재등록으로 중복 방지
for uvicorn_logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
    uvicorn_logger = logging.getLogger(uvicorn_logger_name)
    uvicorn_logger.setLevel(logging.INFO)
    uvicorn_logger.handlers.clear()       # 기존 핸들러 제거
    uvicorn_logger.propagate = False      # 부모 로거로 전파 차단
    uvicorn_logger.addHandler(file_handler)
    uvicorn_logger.addHandler(console_handler)

# 에러 로그 루트 레벨 캐치 - 중복 방지
root_logger = logging.getLogger()
root_logger.setLevel(logging.WARNING)
root_logger.handlers.clear()             # 기존 핸들러 제거
root_logger.addHandler(file_handler)


# =========================================================
# FastAPI 생성
# =========================================================
app = FastAPI()


# =========================================================
# CORS 설정
# =========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# 여행 일정 생성 API
# =========================================================
@app.get("/travel/plan")
async def create_travel_plan(
    region    : str,
    days      : int,
    start_date: str,
    end_date  : str,
    themes    : str,  # 쉼표 구분 문자열 ex) "테마파크,식도락"
):
    try:

        # -------------------------------------------------
        # themes 문자열 -> 리스트 변환
        # -------------------------------------------------
        logger.info(f"themes 수신값: {themes}")
        theme_list = [t.strip() for t in themes.split(',') if t.strip()]

        # -------------------------------------------------
        # Spring API에서 여행지 목록 조회
        # -------------------------------------------------
        try:
            place_list = fetch_place_list(region, themes)
        except Exception as e:
            logger.error(f"Spring API 호출 실패: {str(e)}", exc_info=True)
            return {"success": False, "message": str(e)}

        # -------------------------------------------------
        # 여행지 없을 경우
        # -------------------------------------------------
        if len(place_list) == 0:
            logger.warning(f"조건에 맞는 여행지가 없습니다. region={region}, themes={themes}")
            return {
                "success": False,
                "message": "조건에 맞는 여행지가 없습니다."
            }

        # -------------------------------------------------
        # placeId 기반 복원용 map 생성 (전체 데이터 유지)
        # -------------------------------------------------
        place_map = {
            place["id"]: place
            for place in place_list
        }

        # -------------------------------------------------
        # 사용 가능한 id 목록 추출
        # -------------------------------------------------
        valid_ids = [place["id"] for place in place_list]

        # -------------------------------------------------
        # GPT에 보낼 최소화된 장소 데이터 생성
        # -------------------------------------------------
        place_list_for_gpt = [
            {
                "id"      : place["id"],
                "name"    : place["name"],
                "category": place["placeCategoryName"],
                "filter"  : place["placeFilterName"],
                "hasImage": bool(place.get("imgUrl")),
                "themes"  : place.get("placeThemeName", "").split(",") if place.get("placeThemeName") else [],
                "lat"     : place.get("y", ""),
                "lng"     : place.get("x", ""),
            }
            for place in place_list
        ]

        # -------------------------------------------------
        # 필수 개수 계산
        # -------------------------------------------------
        if days == 1:
            required_food  = 2
            required_cafe  = 1
            required_accom = 0
        elif days == 2:
            required_food  = 3
            required_cafe  = 1
            required_accom = 1
        else:  # 2박3일
            required_food  = 3
            required_cafe  = 1
            required_accom = 2

        # 테마 개수: 단일=2개, 다중=각 1개
        required_theme = 2 if len(theme_list) == 1 else len(theme_list)

        # 식도락 선택 시 필요한 식도락 장소 최소 개수
        # 당일: 테마1+점심+테마2+저녁 = 4개
        # 1박이상: 아침+테마1+점심+테마2+저녁 = 5개/일 (마지막날 -1)
        if "식도락" in theme_list:
            # 하루 기준: 당일/마지막날=4개, 그외=5개
            required_food_theme = 4 if days == 1 else 5
        else:
            required_food_theme = 0

        # -------------------------------------------------
        # GPT Prompt 생성 (단순화)
        # -------------------------------------------------
        prompt = f"""
너는 전문 여행 플래너 AI이다.

반드시 VALID JSON만 출력해라.
설명 문장 금지. 마크다운 금지. ```json 금지.

사용자의 여행 조건:
- 지역: {region}
- 여행 기간: {days}일
- 여행 테마: {', '.join(theme_list)}

아래 여행지 정보만 사용하여 여행 일정을 생성해라.

여행지 정보:
{json.dumps(place_list_for_gpt, ensure_ascii=False)}

사용 가능한 placeId 목록:
{valid_ids}

규칙:
1. 반드시 제공된 장소만 사용, 목록에 없는 id 절대 사용 금지
2. 같은 장소 중복 금지
3. 각 장소의 lat/lng 좌표를 반드시 참고하여 하루 일정 내 장소들이 서로 가까운 위치에 있도록 배치
4. 하루 일정 내 장소 간 이동 거리를 최소화할 것 — 멀리 떨어진 장소를 같은 날에 배치하지 말 것
5. 1박이상 여행은 날짜별로 지역을 나눠서 배치 — 같은 날은 같은 권역 내 장소로만 구성
6. 대표이미지(hasImage=true)인 장소 우선 배치
7. 테마({', '.join(theme_list)}) 장소를 우선 선택
8. filter가 '캠핑'인 장소는 숙소로 사용 금지
9. 카페는 반드시 점심 식사 장소와 가까운 위치의 카페를 선택할 것 — 점심 후 도보 또는 단거리 이동 가능한 카페 우선

하루 필수 구성 (반드시 포함):
{"- 식도락 장소 (themes 배열에 식도락 포함, filter가 한식/일식/양식/중식): 최소 " + str(required_food_theme) + "개 — 식사(아침/점심/저녁) 및 테마 슬롯 모두 식도락 장소로 채움" if "식도락" in theme_list else ""}
{"- 식도락 외 테마 장소 (themes 배열에 " + ", ".join([t for t in theme_list if t != "식도락"]) + " 포함): 각 테마별 정확히 1개" if "식도락" in theme_list and len(theme_list) > 1 else "- 테마 장소 (themes 배열에 선택 테마 포함): " + ("정확히 2개" if len(theme_list) <= 2 else "각 테마별 정확히 1개, 총 3개")}
{"" if "식도락" in theme_list else "- 순수 식사 장소 (filter가 한식/일식/양식/중식, themes 배열 비어있는 장소): " + ("정확히 2개 (점심/저녁)" if days == 1 else "정확히 3개 (아침/점심/저녁) — 마지막날은 2개")}
- 카페 (filter가 '카페'): 정확히 1개
- 볼거리 (category가 '볼거리'): {"정확히 1개" if len(theme_list) <= 2 else "없음 — 테마 3개 선택 시 볼거리 슬롯 없음"}
- {"숙소 없음 (당일여행)" if days == 1 else f"숙소 (filter가 '호텔ㆍ모텔'/'콘도'/'펜션'/'게스트하우스'): 정확히 {required_accom}개 — 마지막날은 숙소 없음"}

응답 형식:
{{
  "schedule": [
    {{
      "day": 1,
      "plans": [
        {{
          "placeId": 1
        }}
      ]
    }}
  ]
}}
"""

        # -------------------------------------------------
        # GPT-4o에 여행 일정 생성 요청
        # -------------------------------------------------
        result_text = request_travel_plan(prompt)

        logger.info("========== GPT RESPONSE ==========")
        logger.info(result_text)

        # -------------------------------------------------
        # JSON 문자열 -> 객체 변환
        # -------------------------------------------------
        result_json = json.loads(result_text)

        # 이중 직렬화 대응
        if isinstance(result_json, str):
            result_json = json.loads(result_json)

        # -------------------------------------------------
        # 유효하지 않은 placeId 제거
        # -------------------------------------------------
        for day in result_json["schedule"]:
            day["plans"] = [
                plan for plan in day["plans"]
                if plan["placeId"] in place_map
            ]

        # -------------------------------------------------
        # 장소 분류 함수
        # 테마먹거리: 식도락처럼 테마이면서 동시에 음식점인 경우
        # -------------------------------------------------
        def classify(place_info, theme_list):
            filter_name   = place_info.get("placeFilterName", "")
            category_name = place_info.get("placeCategoryName", "")
            theme_name    = place_info.get("placeThemeName", "") or ""
            place_themes  = [t.strip() for t in theme_name.split(",") if t.strip()]

            is_food  = filter_name in ["한식", "일식", "양식", "중식", "간이음식"]
            is_theme = any(t in place_themes for t in theme_list)

            if filter_name in ["호텔ㆍ모텔", "호텔·모텔", "콘도", "펜션", "게스트하우스"]:
                return "숙소"
            if filter_name == "카페":
                return "카페"
            if is_food and is_theme:
                return "테마먹거리"  # 식도락 음식점: 테마 슬롯에 배치 + 먹거리 카운트 소모
            if is_theme:
                return "테마"
            if is_food:
                return "먹거리"
            if category_name == "볼거리":
                return "볼거리"
            return "기타"

        # -------------------------------------------------
        # 하루 일정 재정렬 함수
        #
        # 당일 (테마 1~2개): 테마1 - 점심 - 카페 - 볼거리 - 테마2 - 저녁
        # 당일 (테마 3개):   테마1 - 점심 - 카페 - 테마2 - 테마3 - 저녁
        # 1박이상 (테마 1~2개): 아침 - 테마1 - 점심 - 카페 - 볼거리 - 테마2 - 저녁 - 숙소
        # 1박이상 (테마 3개):   아침 - 테마1 - 점심 - 카페 - 테마2 - 테마3 - 저녁 - 숙소
        # 마지막날: 저녁, 숙소 제외
        # -------------------------------------------------
        def reorder_day(plans, theme_list, is_last_day):
            groups = {
                "테마": [], "테마먹거리": [], "먹거리": [],
                "카페": [], "볼거리": [], "숙소": [], "기타": []
            }
            for plan in plans:
                place_info = place_map.get(plan["placeId"], {})
                key = classify(place_info, theme_list)
                groups[key].append(plan)

            def pop(lst):
                return [lst.pop(0)] if lst else []

            has_food_theme = "식도락" in theme_list
            multi_theme    = len(theme_list) >= 3
            current_used   = {p["placeId"] for p in plans}

            # 카페 부족 시 공통 보충
            if not groups["카페"]:
                cafe_supps = [
                    {"placeId": p["id"]}
                    for p in place_list
                    if p.get("placeFilterName") == "카페"
                    and p["id"] not in current_used
                    and p.get("imgUrl")
                ]
                if cafe_supps:
                    groups["카페"].append(cafe_supps[0])
                    logger.info(f"[카페 보충] placeId={cafe_supps[0]['placeId']}")

            # 점심 장소 기준 가장 가까운 카페로 교체
            lunch_plan = None
            has_other_theme = len(groups["테마"]) > 0
            if has_food_theme:
                ft = groups["테마먹거리"]
                if days == 1:
                    lunch_idx = 0 if has_other_theme else 1  # 다른테마 있으면 [0], 단일이면 [1]
                else:
                    lunch_idx = 1 if has_other_theme else 2  # 단일 1박이상은 아침+테마1 다 식도락이라 [2]
                lunch_plan = ft[lunch_idx] if len(ft) > lunch_idx else (ft[-1] if ft else None)
            else:
                fp = groups["먹거리"]
                lunch_idx = 0 if days == 1 else 1  # 당일은 [0], 1박이상은 아침 다음 [1]
                lunch_plan = fp[lunch_idx] if len(fp) > lunch_idx else (fp[-1] if fp else None)

            if lunch_plan:
                lunch_info = place_map.get(lunch_plan["placeId"], {})
                lunch_lat  = float(lunch_info.get("y") or 0)
                lunch_lng  = float(lunch_info.get("x") or 0)

                if lunch_lat and lunch_lng:
                    all_cafes = [
                        p for p in place_list
                        if p.get("placeFilterName") == "카페"
                        and p["id"] not in current_used
                    ]
                    all_cafes.sort(key=lambda p: (
                        (float(p.get("y") or 0) - lunch_lat) ** 2 +
                        (float(p.get("x") or 0) - lunch_lng) ** 2
                    ))
                    if all_cafes:
                        nearest = {"placeId": all_cafes[0]["id"]}
                        if groups["카페"] and groups["카페"][0]["placeId"] != nearest["placeId"]:
                            logger.info(f"[카페 교체] {groups['카페'][0]['placeId']} -> {nearest['placeId']}")
                        groups["카페"] = [nearest]

            # 볼거리 부족 시 공통 보충 (테마 3개 미만일 때만)
            if not groups["볼거리"] and not multi_theme:
                sight_supps = [
                    {"placeId": p["id"]}
                    for p in place_list
                    if p.get("placeCategoryName") == "볼거리"
                    and p["id"] not in current_used
                    and p.get("imgUrl")
                ]
                if sight_supps:
                    groups["볼거리"].append(sight_supps[0])
                    logger.info(f"[볼거리 보충] placeId={sight_supps[0]['placeId']}")

            if has_food_theme:
                # 식도락 포함 시: 테마먹거리가 식사 슬롯도 담당
                food_theme_pool  = groups["테마먹거리"]  # 식도락 음식점
                other_theme_pool = groups["테마"]        # 다른 테마 장소

                # 식도락 장소 부족 시 place_list에서 자동 보충
                _needed = 4 if (days == 1 or is_last_day) else 5
                needed_food_theme = _needed - len(food_theme_pool)
                if needed_food_theme > 0:
                    supplements = [
                        {"placeId": p["id"]}
                        for p in place_list
                        if p.get("placeFilterName") in ["한식", "일식", "양식", "중식"]
                        and "식도락" in (p.get("placeThemeName") or "")
                        and p["id"] not in current_used
                        and p.get("imgUrl")
                    ]
                    food_theme_pool += supplements[:needed_food_theme]
                    for s in supplements[:needed_food_theme]:
                        logger.info(f"[식도락 보충] placeId={s['placeId']}")

                # 다른 테마 장소 부족 시 보충
                other_themes = [t for t in theme_list if t != "식도락"]
                needed_other = len(other_themes) - len(other_theme_pool)
                if needed_other > 0:
                    for ot in other_themes:
                        if not any(
                            ot in (place_map.get(p["placeId"], {}).get("placeThemeName") or "")
                            for p in other_theme_pool
                        ):
                            ot_supps = [
                                {"placeId": p["id"]}
                                for p in place_list
                                if ot in (p.get("placeThemeName") or "")
                                and p["id"] not in current_used
                                and p.get("imgUrl")
                            ]
                            if ot_supps:
                                other_theme_pool.append(ot_supps[0])
                                logger.info(f"[다른테마 보충] {ot} placeId={ot_supps[0]['placeId']}")
            else:
                # 식도락 미포함 시: 기존 방식
                food_theme_pool  = []
                other_theme_pool = groups["테마먹거리"] + groups["테마"]

            food_pool = groups["먹거리"]  # 순수 먹거리 (식도락 미포함 시 사용)

            ordered = []

            if has_food_theme:
                # ── 식도락 포함 케이스 ──
                # 식도락 단일: 식도락이 테마1/테마2 + 식사 슬롯 모두 담당
                # 식도락 + 다른테마: 다른테마가 앞 테마 슬롯, 식도락은 뒤 테마 슬롯 + 식사
                has_other_theme = len(other_theme_pool) > 0

                if days == 1:
                    if has_other_theme:
                        # 다른테마(테마1) - 식도락(점심) - 카페 - 볼거리 - 식도락(테마2) - 식도락(저녁)
                        # 다른테마1(테마1) - 식도락(점심) - 카페 - 다른테마2(테마2) - 식도락(테마3) - 식도락(저녁)
                        ordered += pop(other_theme_pool)  # 테마1 (다른테마)
                        ordered += pop(food_theme_pool)   # 점심 (식도락)
                        ordered += pop(groups["카페"])
                        if multi_theme:
                            ordered += pop(other_theme_pool)  # 테마2 (다른테마)
                            ordered += pop(food_theme_pool)   # 테마3 (식도락)
                        else:
                            ordered += pop(groups["볼거리"])
                            ordered += pop(food_theme_pool)   # 테마2 (식도락)
                        ordered += pop(food_theme_pool)   # 저녁 (식도락)
                    else:
                        # 식도락 단일: 식도락(테마1) - 식도락(점심) - 카페 - 볼거리 - 식도락(테마2) - 식도락(저녁)
                        ordered += pop(food_theme_pool)   # 테마1 (식도락)
                        ordered += pop(food_theme_pool)   # 점심 (식도락)
                        ordered += pop(groups["카페"])
                        ordered += pop(groups["볼거리"])
                        ordered += pop(food_theme_pool)   # 테마2 (식도락)
                        ordered += pop(food_theme_pool)   # 저녁 (식도락)
                else:
                    if has_other_theme:
                        # 식도락(아침) - 다른테마(테마1) - 식도락(점심) - 카페 - 볼거리 - 식도락(테마2) - 식도락(저녁) - 숙소
                        # 식도락(아침) - 다른테마1(테마1) - 식도락(점심) - 카페 - 다른테마2(테마2) - 식도락(테마3) - 식도락(저녁) - 숙소
                        ordered += pop(food_theme_pool)   # 아침 (식도락)
                        ordered += pop(other_theme_pool)  # 테마1 (다른테마)
                        ordered += pop(food_theme_pool)   # 점심 (식도락)
                        ordered += pop(groups["카페"])
                        if multi_theme:
                            ordered += pop(other_theme_pool)  # 테마2 (다른테마)
                            ordered += pop(food_theme_pool)   # 테마3 (식도락)
                        else:
                            ordered += pop(groups["볼거리"])
                            ordered += pop(food_theme_pool)   # 테마2 (식도락)
                        if not is_last_day:
                            ordered += pop(food_theme_pool)   # 저녁 (식도락)
                            ordered += groups["숙소"][:1]
                    else:
                        # 식도락 단일: 식도락(아침) - 식도락(테마1) - 식도락(점심) - 카페 - 볼거리 - 식도락(테마2) - 식도락(저녁) - 숙소
                        ordered += pop(food_theme_pool)   # 아침 (식도락)
                        ordered += pop(food_theme_pool)   # 테마1 (식도락)
                        ordered += pop(food_theme_pool)   # 점심 (식도락)
                        ordered += pop(groups["카페"])
                        ordered += pop(groups["볼거리"])
                        ordered += pop(food_theme_pool)   # 테마2 (식도락)
                        if not is_last_day:
                            ordered += pop(food_theme_pool)   # 저녁 (식도락)
                            ordered += groups["숙소"][:1]
            else:
                # ── 식도락 미포함 케이스 ──
                theme_pool = other_theme_pool

                # food_pool 부족 시 place_list에서 순수 먹거리 보충
                needed = (2 if days == 1 else (2 if is_last_day else 3)) - len(food_pool)
                if needed > 0:
                    supplements = [
                        {"placeId": p["id"]}
                        for p in place_list
                        if p.get("placeFilterName") in ["한식", "일식", "양식", "중식"]
                        and not any(t in (p.get("placeThemeName") or "") for t in theme_list)
                        and p["id"] not in current_used
                        and p.get("imgUrl")
                    ]
                    food_pool += supplements[:needed]
                    for s in supplements[:needed]:
                        logger.info(f"[먹거리 보충] placeId={s['placeId']}")

                if days == 1:
                    ordered += pop(theme_pool)        # 테마1
                    ordered += pop(food_pool)         # 점심
                    ordered += pop(groups["카페"])
                    if multi_theme:
                        ordered += pop(theme_pool)    # 테마2
                        ordered += pop(theme_pool)    # 테마3
                    else:
                        ordered += pop(groups["볼거리"])
                        ordered += pop(theme_pool)    # 테마2
                    ordered += pop(food_pool)         # 저녁
                else:
                    ordered += pop(food_pool)         # 아침
                    ordered += pop(theme_pool)        # 테마1
                    ordered += pop(food_pool)         # 점심
                    ordered += pop(groups["카페"])
                    if multi_theme:
                        ordered += pop(theme_pool)    # 테마2
                        ordered += pop(theme_pool)    # 테마3
                    else:
                        ordered += pop(groups["볼거리"])
                        ordered += pop(theme_pool)    # 테마2
                    if not is_last_day:
                        ordered += pop(food_pool)     # 저녁
                        ordered += groups["숙소"][:1]

            # 슬롯 초과 방지: 잔여 테마/먹거리는 버림
            remaining = groups["카페"] + groups["볼거리"] + groups["기타"]
            ordered += remaining

            return ordered

        # -------------------------------------------------
        # 후처리 1: 숙소 강제 제거
        # - 당일여행: 전체 숙소 제거
        # - 1박이상: 마지막날 숙소 제거
        # -------------------------------------------------
        total_days = len(result_json["schedule"])
        for day_idx, day in enumerate(result_json["schedule"]):
            is_last = (day_idx == total_days - 1)
            if days == 1 or is_last:
                day["plans"] = [
                    p for p in day["plans"]
                    if classify(place_map.get(p["placeId"], {}), theme_list) != "숙소"
                ]

            if len(theme_list) >= 3:
                day["plans"] = [
                    p for p in day["plans"]
                    if classify(place_map.get(p["placeId"], {}), theme_list) != "볼거리"
                ]

        # -------------------------------------------------
        # 후처리 2: 이미지 없는 장소 교체 (재정렬 전에 수행)
        # -------------------------------------------------
        used_ids = set()

        for day in result_json["schedule"]:
            for plan in day["plans"]:
                used_ids.add(plan["placeId"])

        image_places = {}
        for place in place_list:
            if place.get("imgUrl"):
                key = (place["placeCategoryName"], place["placeFilterName"])
                if key not in image_places:
                    image_places[key] = []
                image_places[key].append(place)

        for day in result_json["schedule"]:
            for plan in day["plans"]:
                place_id   = plan["placeId"]
                place_info = place_map.get(place_id)
                if place_info and not place_info.get("imgUrl"):
                    key         = (place_info["placeCategoryName"], place_info["placeFilterName"])
                    candidates  = image_places.get(key, [])
                    replacement = next(
                        (p for p in candidates if p["id"] not in used_ids),
                        None
                    )
                    if replacement:
                        used_ids.discard(place_id)
                        used_ids.add(replacement["id"])
                        plan["placeId"] = replacement["id"]
                        logger.info(f"[이미지 교체] {place_info['name']} -> {replacement['name']}")

        # -------------------------------------------------
        # 후처리 2.5: 하루 일정 내 동선 클러스터링
        # 중심 좌표에서 너무 멀리 떨어진 장소를 같은 슬롯 타입 중 가까운 장소로 교체
        # -------------------------------------------------
        def haversine(lat1, lng1, lat2, lng2):
            R = 6371  # 지구 반지름 km
            dlat = math.radians(lat2 - lat1)
            dlng = math.radians(lng2 - lng1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
            return R * 2 * math.asin(math.sqrt(a))

        MAX_DISTANCE_KM = 15  # 중심에서 최대 허용 거리

        for day in result_json["schedule"]:
            plans = day["plans"]
            if not plans:
                continue

            # 중심 좌표 계산
            coords = []
            for p in plans:
                info = place_map.get(p["placeId"], {})
                lat  = float(info.get("y") or 0)
                lng  = float(info.get("x") or 0)
                if lat and lng:
                    coords.append((lat, lng))

            if not coords:
                continue

            center_lat = sum(c[0] for c in coords) / len(coords)
            center_lng = sum(c[1] for c in coords) / len(coords)

            # 중심에서 너무 멀리 떨어진 장소 교체
            used_ids_day = {p["placeId"] for p in plans}
            for p in plans:
                info = place_map.get(p["placeId"], {})
                lat  = float(info.get("y") or 0)
                lng  = float(info.get("x") or 0)
                if not lat or not lng:
                    continue

                dist = haversine(center_lat, center_lng, lat, lng)
                if dist > MAX_DISTANCE_KM:
                    # 같은 슬롯 타입 중 중심에 가까운 장소로 교체
                    slot_type  = classify(info, theme_list)
                    candidates = [
                        pl for pl in place_list
                        if classify(pl, theme_list) == slot_type
                        and pl["id"] not in used_ids_day
                        and pl.get("imgUrl")
                        and float(pl.get("y") or 0)
                        and float(pl.get("x") or 0)
                    ]
                    candidates.sort(key=lambda pl: haversine(
                        center_lat, center_lng,
                        float(pl.get("y") or 0),
                        float(pl.get("x") or 0)
                    ))
                    if candidates:
                        logger.info(f"[동선 교체] {info.get('name')} ({dist:.1f}km) -> {candidates[0]['name']}")
                        used_ids_day.discard(p["placeId"])
                        used_ids_day.add(candidates[0]["id"])
                        p["placeId"] = candidates[0]["id"]

        # -------------------------------------------------
        # 후처리 3: 재정렬 적용 (이미지 교체 후)
        # -------------------------------------------------
        for day_idx, day in enumerate(result_json["schedule"]):
            is_last_day = (day_idx == days - 1)
            day["plans"] = reorder_day(day["plans"], theme_list, is_last_day)

        # -------------------------------------------------
        # placeId 기반 상세 정보 복원
        # -------------------------------------------------
        for day in result_json["schedule"]:
            for plan in day["plans"]:
                place_id = plan["placeId"]
                if place_id in place_map:
                    place_info        = place_map[place_id]
                    plan["placeName"] = place_info["name"]
                    plan["category"]  = place_info.get("placeCategoryName", "")
                    plan["overview"]  = place_info.get("overview", "")
                    plan["imgUrl"]    = place_info.get("imgUrl", "")
                    plan["lat"]       = place_info.get("y", "")
                    plan["lng"]       = place_info.get("x", "")
                    plan["addr"]      = place_info.get("addr", "")

        # -------------------------------------------------
        # 응답 반환
        # -------------------------------------------------
        return {
            "success": True,
            "data": result_json
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 오류: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"JSON Parse Error: {str(e)}"
        }

    except Exception as e:
        logger.error(f"일정 생성 중 오류 발생: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": str(e)
        }


# =========================================================
# 서버 실행
# =========================================================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="localhost",
        port=8090,
        reload=True
    )


# =========================================================
# 끝
# =========================================================