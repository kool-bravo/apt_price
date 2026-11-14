from datetime import datetime
import os
from dotenv import load_dotenv
import requests
from supabase import Client, create_client

# .env 파일에서 환경 변수 불러오기 (라즈베리파이/로컬 실행용)
load_dotenv()

# 1. 환경 변수에서 Supabase 접속 정보 불러오기
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
  raise ValueError("Supabase URL 또는 Key 환경 변수가 설정되지 않았습니다.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def main():
  print("아파트 시세 데이터 수집을 시작합니다...")

  # 2. Supabase 'apartments' 테이블에서 단지 목록 가져오기
  try:
    response = supabase.table("apartments").select("*").execute()
    apartments = response.data
  except Exception as e:
    print(f"apartments 테이블 조회 실패: {e}")
    return

  if not apartments:
    print("등록된 아파트 단지가 없습니다. apartments 테이블을 확인해주세요.")
    return

  print(f"총 {len(apartments)}개의 단지 정보를 불러왔습니다.")

  today_date = datetime.now().strftime("%Y-%m-%d")

  # 3. 세션(Session) 객체 생성 및 네이버 메인 쿠키 사전 획득 (차단 우회)
  session = requests.Session()
  base_headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
  }

  try:
    print("네이버 부동산 세션 초기화 및 쿠키 획득 중...")
    session.get("https://new.land.naver.com", headers=base_headers, timeout=10)
  except Exception as e:
    print(f"세션 초기화 중 예외 발생 (계속 진행합니다): {e}")

  # 4. 각 단지별로 네이버 부동산 API 호출 및 시세 수집
  for apt in apartments:
    apt_id = apt.get("id")  # apartments 테이블의 고유 id
    complex_no = apt.get("naver_complex_no")  # 네이버 단지 번호

    if not complex_no:
      continue

    url = f"https://new.land.naver.com/api/complexes/{complex_no}/overview"

    # 401 에러 방지를 위한 상세 브라우저 모방 헤더
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": f"https://new.land.naver.com/complexes/{complex_no}",
        "Host": "new.land.naver.com",
        "Sec-Ch-Ua": (
            '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"'
        ),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
      print(
          f"단지명: {apt.get('name')} (ID: {apt_id}, 네이버번호:"
          f" {complex_no}) 수집 중..."
      )
      res = session.get(url, headers=headers, timeout=10)

      if res.status_code != 200:
        print(
            f"네이버 API 응답 실패 (Code: {res.status_code}) 단지번호:"
            f" {complex_no}"
        )
        continue

      data = res.json()
      complex_summary = data.get("complexSummary", {})

      # 호가 데이터 추출 및 단위 변환
      min_price = complex_summary.get("lowPrice", 0) * 10000
      max_price = complex_summary.get("highPrice", 0) * 10000
      total_listings = complex_summary.get("totalCount", 0)

      # 5. price_logs 테이블 구조에 맞춘 데이터 삽입
      log_data = {
          "apartment_id": apt_id,
          "recorded_date": today_date,
          "min_asking_price": min_price,
          "max_asking_price": max_price,
          "total_listings": total_listings,
      }

      supabase.table("price_logs").insert(log_data).execute()
      print(f"[{apt.get('name')}] DB 저장 성공!")

    except requests.exceptions.Timeout:
      print(f"요청 시간 초과 (Timeout): 단지 번호 {complex_no}")
      continue
    except Exception as e:
      print(f"단지 {complex_no} 처리 중 에러 발생: {e}")
      continue


if __name__ == "__main__":
  main()