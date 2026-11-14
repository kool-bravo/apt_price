import os
from datetime import datetime
import requests
from supabase import Client, create_client

# 1. 환경 변수에서 Supabase 접속 정보 불러오기 (GitHub Secrets에서 주입됨)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
  raise ValueError("Supabase URL 또는 Key 환경 변수가 설정되지 않았습니다.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def main():
  print("아파트 시세 데이터 수집을 시작합니다...")

  # 2. Supabase 'apartments' 테이블에서 수집 대상 단지 목록 가져오기
  try:
    response = supabase.table("apartments").select("*").execute()
    apartments = response.data
  except Exception as e:
    print(f"apartments 테이블 조회 실패: {e}")
    return

  if not apartments:
    print(
        "등록된 아파트 단지가 없습니다. Supabase apartments 테이블을"
        " 확인해주세요."
    )
    return

  print(f"총 {len(apartments)}개의 단지 정보를 불러왔습니다.")

  # 3. 각 단지별로 네이버 부동산 API 호출 및 시세 수집
  for apt in apartments:
    complex_no = apt.get("naver_complex_no")
    if not complex_no:
      continue

    url = f"https://new.land.naver.com/api/complexes/{complex_no}/overview"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": f"https://new.land.naver.com/complexes/{complex_no}",
    }

    try:
      print(f"단지 번호 {complex_no} 수집 중...")
      # 타임아웃 10초 설정으로 무한 대기 방지
      res = requests.get(url, headers=headers, timeout=10)

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

      # 4. Supabase 'price_logs' 테이블에 데이터 저장
      # (created_at은 DB 기본값인 now()가 자동으로 들어가므로 생략)
      log_data = {
          "complex_no": str(complex_no),
          "min_price": min_price,
          "max_price": max_price,
      }

      insert_res = supabase.table("price_logs").insert(log_data).execute()
      print(f"단지 번호 {complex_no} DB 저장 성공!")

    except requests.exceptions.Timeout:
      print(f"요청 시간 초과 (Timeout): 단지 번호 {complex_no}")
      continue
    except Exception as e:
      print(f"단지 {complex_no} 처리 중 에러 발생: {e}")
      continue


if __name__ == "__main__":
  main()