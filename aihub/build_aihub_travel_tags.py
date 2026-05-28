import pandas as pd
import json

from collections import defaultdict, Counter

from openai import OpenAI
from dotenv import load_dotenv

import os


# 환경변수 로드
load_dotenv()


# OpenAI Client 생성
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


# 압축 해제된 AIHub CSV 폴더 경로
DATASET_DIR = "ai_hub_csv_dataset"


# 결과 저장 파일명
OUTPUT_FILE = "travel_sample_itinerary.json"


# llm 분석용 데이터 저장 객체
analysis_data = {}


# CSV에서 특정 keyword가 포함된 컬럼명을 찾는 함수
def find_column(df, keyword):

    for col in df.columns:

        if keyword.upper() in col.upper():

            return col

    return None


# 폴더 내부 CSV 파일 목록 조회
csv_files = os.listdir(
    DATASET_DIR
)


# 필요한 CSV 파일 변수
companion_file = None
visit_file = None


# CSV 파일 자동 탐색
for file_name in csv_files:

    # 동반자정보 CSV
    if "동반자정보" in file_name:

        companion_file = file_name

    # 방문지정보 CSV
    elif "방문지정보" in file_name:

        visit_file = file_name


# 필수 CSV 존재 여부 확인
if companion_file is None:

    raise Exception(
        "동반자정보 CSV 없음"
    )

if visit_file is None:

    raise Exception(
        "방문지정보 CSV 없음"
    )


# CSV 전체 경로 생성
companion_path = os.path.join(
    DATASET_DIR,
    companion_file
)

visit_path = os.path.join(
    DATASET_DIR,
    visit_file
)


# CSV 로드
print()
print("CSV 로딩 시작")
print()

companion_df = pd.read_csv(
    companion_path,
    encoding="utf-8"
)

visit_df = pd.read_csv(
    visit_path,
    encoding="utf-8"
)

print("CSV 로딩 완료")
print()


# 필요한 컬럼명 자동 탐색
travel_id_col = find_column(
    companion_df,
    "TRAVEL_ID"
)

companion_col = find_column(
    companion_df,
    "COMPANION"
)

visit_name_col = find_column(
    visit_df,
    "VISIT_AREA_NM"
)


# 필수 컬럼 존재 여부 확인
if travel_id_col is None:

    raise Exception(
        "TRAVEL_ID 컬럼 없음"
    )

if companion_col is None:

    raise Exception(
        "COMPANION 컬럼 없음"
    )

if visit_name_col is None:

    raise Exception(
        "VISIT_AREA_NM 컬럼 없음"
    )


# 컬럼명 출력
print("travel_id_col :", travel_id_col)
print("companion_col :", companion_col)
print("visit_name_col :", visit_name_col)
print()


# 동반자 유형별 여행 ID 저장
raw_companion_travel_ids = defaultdict(set)

print("동반자 데이터 분석 시작")
print()

for _, row in companion_df.iterrows():

    try:

        travel_id = row[
            travel_id_col
        ]

        raw_companion = str(
            row[companion_col]
        ).strip()

        # 빈값 제거
        if raw_companion == "":

            continue

        raw_companion_travel_ids[
            raw_companion
        ].add(
            travel_id
        )

    except Exception:

        pass

print("동반자 데이터 분석 완료")
print()


# 여행 ID별 방문 장소 저장
travel_places = defaultdict(list)

print("방문지 데이터 분석 시작")
print()

for _, row in visit_df.iterrows():

    try:

        travel_id = row[
            travel_id_col
        ]

        place_name = str(
            row[visit_name_col]
        ).strip()

        # 빈값 제거
        if place_name == "":

            continue

        travel_places[
            travel_id
        ].append(
            place_name
        )

    except Exception:

        pass

print("방문지 데이터 분석 완료")
print()


# 동반자 유형별 대표 장소 통계 생성
print("대표 장소 통계 생성 시작")
print()

for raw_companion, ids in raw_companion_travel_ids.items():

    place_counter = Counter()

    # 여행별 장소 순회
    for travel_id in ids:

        places = travel_places.get(
            travel_id,
            []
        )

        # 장소 빈도 계산
        for place in places:

            place_counter[
                place
            ] += 1

    top_places = []

    # 상위 50개 장소 추출
    for place, count in place_counter.most_common(50):

        top_places.append({

            "place": place,

            "count": count
        })

    # GPT 분석용 데이터 저장
    analysis_data[raw_companion] = {

        "travel_count": len(ids),

        "top_places": top_places
    }

print("대표 장소 통계 생성 완료")
print()


# 중간 분석 데이터 저장
with open(
    "analysis_data.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        analysis_data,
        f,
        ensure_ascii=False,
        indent=2
    )

print("analysis_data.json 저장 완료")
print()


# GPT 분석용 프롬프트 생성
prompt = f"""
너는 여행 추천 일정 생성 AI다.

아래 데이터는 실제 여행 로그 기반 통계 데이터다.

동반자 유형별 대표 방문 장소를 참고하여:

1. semantic grouping 수행
2. 대표 여행 유형 생성
3. 실제 여행 패턴 기반
   1박2일 / 2박3일 예시 일정 생성

매우 중요:

1. 비슷한 동반자 유형은 하나로 통합
2. 대표 그룹 예시:
   - 커플
   - 가족
   - 친구
   - 혼자
   - 동료

3. 일정은 실제 여행 흐름처럼 구성
4. 이동 동선이 자연스럽게 구성
5. 장소명은 실제 top_places 기반 사용
6. 하루 최대 4~5개 장소만 사용
7. 중복 장소 최소화
8. JSON 외 텍스트 절대 금지

반드시 아래 JSON 구조 유지:

{{
  "커플": {{

    "1박2일": [
      {{
        "day": 1,
        "schedule": [
          {{
            "time": "12:00",
            "place": "행리단길",
            "theme": "카페"
          }},
          {{
            "time": "15:00",
            "place": "광교호수공원",
            "theme": "데이트"
          }},
          {{
            "time": "19:00",
            "place": "수원 맛집거리",
            "theme": "맛집"
          }}
        ]
      }},
      {{
        "day": 2,
        "schedule": [
          {{
            "time": "11:00",
            "place": "스타필드 수원",
            "theme": "쇼핑"
          }}
        ]
      }}
    ],

    "2박3일": [
      {{
        "day": 1,
        "schedule": [
          {{
            "time": "12:00",
            "place": "행리단길",
            "theme": "카페"
          }}
        ]
      }},
      {{
        "day": 2,
        "schedule": [
          {{
            "time": "14:00",
            "place": "광교호수공원",
            "theme": "데이트"
          }}
        ]
      }},
      {{
        "day": 3,
        "schedule": [
          {{
            "time": "11:00",
            "place": "스타필드 수원",
            "theme": "쇼핑"
          }}
        ]
      }}
    ]
  }}
}}

데이터:
{json.dumps(analysis_data, ensure_ascii=False)}
"""


# OpenAI API 요청
print("OpenAI 분석 요청 시작")
print()

response = client.chat.completions.create(

    model="gpt-5-mini",

    messages=[

        {
            "role": "system",
            "content": "너는 여행 추천 일정 생성 AI다."
        },

        {
            "role": "user",
            "content": prompt
        }
    ],

    response_format={
        "type": "json_object"
    },

    max_completion_tokens=6000
)

print("OpenAI 분석 완료")
print()


# GPT 응답 추출
content = response \
    .choices[0] \
    .message.content


# GPT 응답 JSON 변환
parsed = json.loads(
    content
)


# 최종 결과 JSON 저장
with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        parsed,
        f,
        ensure_ascii=False,
        indent=2
    )


# 실행 결과 출력
print()
print(f"{OUTPUT_FILE} 생성 완료")
print()

print(
    json.dumps(
        parsed,
        ensure_ascii=False,
        indent=2
    )
)