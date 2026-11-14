import os
import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import create_client, Client

# 페이지 기본 설정
st.set_page_config(page_title="서울 대장 아파트 호가 트래커", layout="wide")
st.title("🏙️ 서울 구별 대장 아파트 호가 & 매물 흐름 대시보드")
st.markdown("주요 상급지(선행지표)와 인접 지역의 호가 변동 시차 및 매물 추이를 비교합니다.")

# Supabase 연결 (Streamlit Cloud의 Secrets 또는 로컬 환경변수 사용)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_PUBLISHABLE_KEY", os.environ.get("SUPABASE_PUBLISHABLE_KEY"))

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# 데이터 불러오기 (캐싱 10분)
@st.cache_data(ttl=600)
def load_data():
    apt_res = supabase.table("apartments").select("*").execute()
    log_res = supabase.table("price_logs").select("*").order("recorded_date", desc=False).execute()
    
    df_apt = pd.DataFrame(apt_res.data)
    df_log = pd.DataFrame(log_res.data)
    
    if df_apt.empty or df_log.empty:
        return pd.DataFrame()
        
    # 테이블 조인
    df = pd.merge(df_log, df_apt, left_on="apartment_id", right_on="id", suffixes=("", "_apt"))
    df["display_name"] = "[" + df["district"] + "] " + df["name"]
    df["min_price_eok"] = df["min_asking_price"] / 10000.0  # 만원 -> 억 원 변환
    return df

df = load_data()

if df.empty:
    st.warning("아직 수집된 호가 데이터가 없습니다. Supabase의 apartments 테이블에 단지를 등록하고 수집 스크립트를 실행해 주세요.")
    st.stop()

# --- 사이드바 필터 ---
st.sidebar.header("🔍 비교 단지 선택")
all_apts = sorted(df["display_name"].unique())
selected_apts = st.sidebar.multiselect(
    "시차 흐름을 비교할 아파트를 선택하세요 (2개 이상 권장)",
    options=all_apts,
    default=all_apts[:4] if len(all_apts) >= 4 else all_apts
)

chart_mode = st.sidebar.radio(
    "차트 기준 선택",
    ["실제 최저 호가 (억 원)", "기준일 대비 변동액 (억 원)", "기준일 대비 변동률 (%)"]
)

filtered_df = df[df["display_name"].isin(selected_apts)].copy()

# 기준일(첫 수집일) 대비 변동액 / 변동률 계산
filtered_df["base_price"] = filtered_df.groupby("display_name")["min_price_eok"].transform("first")
filtered_df["diff_eok"] = filtered_df["min_price_eok"] - filtered_df["base_price"]
filtered_df["diff_pct"] = (filtered_df["diff_eok"] / filtered_df["base_price"]) * 100

# --- 1. 시계열 호가 전이 비교 차트 ---
st.subheader("📈 호가 전이 흐름 비교 차트")

y_col = "min_price_eok"
y_label = "최저 호가 (억 원)"
if chart_mode == "기준일 대비 변동액 (억 원)":
    y_col = "diff_eok"
    y_label = "기준일 대비 변동액 (억 원)"
elif chart_mode == "기준일 대비 변동률 (%)":
    y_col = "diff_pct"
    y_label = "기준일 대비 변동률 (%)"

fig_price = px.line(
    filtered_df,
    x="recorded_date",
    y=y_col,
    color="display_name",
    markers=True,
    labels={"recorded_date": "날짜", y_col: y_label, "display_name": "단지명"},
    height=450
)
fig_price.update_layout(hovermode="x unified", legend_title_text="단지")
st.plotly_chart(fig_price, use_container_width=True)

# --- 2. 매물 수 증감 추이 차트 (선행 신호 포착) ---
st.subheader("📦 매물 수량 변화 (호가 하락 전 매물 적체 확인)")
fig_listing = px.bar(
    filtered_df,
    x="recorded_date",
    y="total_listings",
    color="display_name",
    barmode="group",
    labels={"recorded_date": "날짜", "total_listings": "총 매물 수(개)", "display_name": "단지명"},
    height=350
)
st.plotly_chart(fig_listing, use_container_width=True)

# --- 3. 블로그 포스팅용 요약 표 ---
st.subheader("📋 최신 호가 및 매물 요약표 (블로그 정리용)")
latest_date = filtered_df["recorded_date"].max()
latest_df = filtered_df[filtered_df["recorded_date"] == latest_date][
    ["district", "dong", "name", "target_pyeong", "min_price_eok", "diff_eok", "total_listings"]
].copy()
latest_df.columns = ["자치구", "법정동", "단지명", "평형(㎡)", "최저호가(억)", "기준일대비(억)", "매물수(개)"]
st.dataframe(latest_df.sort_values(by="최저호가(억)", ascending=False), use_container_width=True, hide_index=True)