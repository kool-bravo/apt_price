import os, sys, requests, xml.etree.ElementTree as ET
from datetime import date
from supabase import create_client

SERVICE_KEY = os.environ["DATA_GO_KR_KEY"]
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

def fetch_month(lawd_cd, ym):
    rows, page = [], 1
    while True:
        r = requests.get(URL, params={
            "serviceKey": SERVICE_KEY, "LAWD_CD": lawd_cd,
            "DEAL_YMD": ym, "pageNo": page, "numOfRows": 1000}, timeout=30)
        r.raise_for_status()
        items = ET.fromstring(r.content).findall(".//item")
        for it in items:
            g = lambda k: (it.findtext(k) or "").strip()
            rows.append({
                "dong": g("umdNm"), "apt_name": g("aptNm"),
                "area_m2": float(g("excluUseAr") or 0),
                "floor": int(g("floor") or 0),
                "price_man": int(g("dealAmount").replace(",", "") or 0),
                "deal_date": f"{g('dealYear')}-{int(g('dealMonth')):02d}-{int(g('dealDay')):02d}",
                "canceled": g("cdealType") == "O",
            })
        if len(items) < 1000:
            return rows
        page += 1

def months_back(n):
    t = date.today()
    for i in range(n):
        m = t.month - 1 - i
        y = t.year + m // 12
        yield f"{y}{m % 12 + 1:02d}"

def list_names(sgg, dong, ym):
    """단지명 확인용: python fetch_trades.py --list 11710 잠실동 202610"""
    print(sorted({r["apt_name"] for r in fetch_month(sgg, ym) if r["dong"] == dong}))

def main(n_months=3):
    apts = sb.table("apartments").select(
        "id,dong,sgg_code,trade_apt_name,target_pyeong").execute().data
    apts = [a for a in apts if a.get("sgg_code") and a.get("trade_apt_name")]
    by_sgg = {}
    for a in apts:
        by_sgg.setdefault(a["sgg_code"], []).append(a)

    out = {}
    for sgg, group in by_sgg.items():
        for ym in months_back(n_months):
            for r in fetch_month(sgg, ym):
                if r["canceled"]:
                    continue
                for a in group:
                    # 전용 84.97㎡ -> 84, 59.98㎡ -> 59 로 target_pyeong와 매칭
                    if (r["apt_name"] == a["trade_apt_name"] and r["dong"] == a["dong"]
                            and int(r["area_m2"]) == a["target_pyeong"]):
                        key = f'{a["id"]}|{r["deal_date"]}|{r["floor"]}|{r["area_m2"]}|{r["price_man"]}'
                        out[key] = {"trade_key": key, "apartment_id": a["id"],
                                    "deal_date": r["deal_date"], "floor": r["floor"],
                                    "area_m2": r["area_m2"], "price_man": r["price_man"]}
    if out:
        sb.table("real_trades").upsert(list(out.values()), on_conflict="trade_key").execute()
    print(f"saved {len(out)} trades")

if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--list":
        list_names(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        main()