Python
import os
import requests
from datetime import datetime
from supabase import create_client, Client

# 1. 환경 변수에서 Supabase 접속 정보 불러오기 (GitHub Secrets에서 주입받음)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_naver_market_data(complex_no):
    """
    네이버 부동산 모바일/웹 API를 호출하여 해당 단지의 호가 및 매물 정보를 가져오는 함수
    (네이버는 User-Agent 헤더가 없으면 차단하므로 브라우저인 것처럼 위장해야 합니다)
    """
    url = f"https://new.land.naver.com/api/complexes/{complex_no}/overview"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://new.land.naver.com/complexes/{complex_no}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"[오류] 네이버 API 응답 실패 (Code: {response.status_code}) 단지번호: {complex_no}")
            return None, None, None
            
        data = response.json()
        # 네이버 단지 오버뷰 구조에서 필요한 값 추출 (단지 기본 정보 및 매물 통계)
        # ※ 네이버 API 구조에 따라 키값은 미세 조정될 수 있습니다.
        complex_summary = data.get("complexSummary", {})
        
        # 예시로 최저 호가, 최고 호가, 총 매물 수를 파싱한다고 가정
        # (실제 네이버 API 응답 JSON 구조에 맞춰 세부 필드는 조정 필요)
        min_price = complex_summary.get("lowPrice", 0) * 10000  억/만원 단위 변환 처리
        max_price = complex_summary.get("highPrice", 0) * 10000
        total_listings = complex_summary.get("totalArticleCount", 0)
        
        return min_price, max_price, total_listings
    except Exception as e:
        print(f"[예외 발생] 단지번호 {complex_no}: {e}")
        return None, None, None

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== 아파트 호가 수집 스크립트 시작 ({today}) ===")
    
    # 2. Supabase에서 등록된 대장 아파트 목록 가져오기
    response = supabase.table("apartments").select("*").execute()
    apartments = response.data
    
    if not apartments:
        print("등록된 아파트가 없습니다. apartments 테이블을 확인하세요.")
        return

    for apt in apartments:
        apt_id = apt["id"]
        name = apt["name"]
        complex_no = apt["naver_complex_no"]
        
        if not complex_no:
            print(f"[{name}] 네이버 단지 번호가 등록되지 않았습니다.")
            continue
            
        print(f"수집 중: {name} (단지번호: {complex_no})")
        
        # 3. 네이버에서 호가 데이터 가져오기
        min_p, max_p, listings = fetch_naver_market_data(complex_no)
        
        if min_p is not None:
            # 4. Supabase price_logs 테이블에 INSERT (이미 오늘 데이터가 있으면 UPSERT 처리 가능)
            log_data = {
                "apartment_id": apt_id,
                "recorded_date": today,
                "min_asking_price": min_p,
                "max_asking_price": max_p,
                "total_listings": listings
            }
            
            # DB에 저장 (unique 제약 조건에 걸리면 업데이트 하도록 upsert 사용)
            supabase.table("price_logs").upsert(log_data, on_conflict="apartment_id,recorded_date").execute()
            print(f" -> 저장 완료! (최저호가: {min_p}, 매물수: {listings})")
            
    print("=== 모든 수집 작업 완료 ===")

if __name__ == "__main__":
    main()