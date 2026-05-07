import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import json

st.set_page_config(
    page_title="위멤버스 보고서",
    page_icon="📈",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.main-title {
    font-size: 2rem; font-weight: 700;
    background: linear-gradient(135deg, #1A3A8F, #0066FF);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
}
.kpi-card {
    background: #f8faff; border: 1px solid #e2e8f0;
    border-radius: 12px; padding: 1.2rem 1rem; text-align: center;
}
.kpi-label { color: #64748b; font-size: 0.8rem; margin-bottom: 0.3rem; }
.kpi-value { color: #1A3A8F; font-size: 2rem; font-weight: 700; line-height: 1.1; }
.kpi-sub   { color: #94a3b8; font-size: 0.78rem; margin-top: 0.2rem; }
.kpi-good  { color: #16a34a; font-size: 0.85rem; font-weight: 600; }
.kpi-bad   { color: #dc2626; font-size: 0.85rem; font-weight: 600; }
.week-range { 
    background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 8px; padding: 0.6rem 1rem;
    color: #1e40af; font-size: 0.88rem; font-weight: 500;
    display: inline-block; margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

SPREADSHEET_ID = "1k2FcMog8G75apAxUAJsCuHE10hQHSmImFofX1ZTSYwk"
COLORS = {"위멤버스": "#0066FF", "경리나라T": "#1A3A8F", "경리나라": "#06b6d4"}

# 상품명 분류
WM_PRODUCTS    = ["위멤버스 스탠다드", "위멤버스 프리미엄"]
OTHER_PRODUCTS = ["링크패스", "세모리포트"]

QUARTERS = {1: "1분기", 2: "1분기", 3: "1분기",
            4: "2분기", 5: "2분기", 6: "2분기",
            7: "3분기", 8: "3분기", 9: "3분기",
            10: "4분기", 11: "4분기", 12: "4분기"}

MONTH_NAMES = {1:"1월",2:"2월",3:"3월",4:"4월",5:"5월",6:"6월",
               7:"7월",8:"8월",9:"9월",10:"10월",11:"11월",12:"12월"}


# ── 주차 계산 (목~수) ────────────────────────────────────────
def get_week_range(ref_date: date) -> tuple:
    """목요일 시작 기준 해당 주의 목요일~수요일 반환"""
    weekday = ref_date.weekday()  # 월=0, 목=3, 수=2
    days_since_thu = (weekday - 3) % 7
    thu = ref_date - timedelta(days=days_since_thu)
    wed = thu + timedelta(days=6)
    return thu, wed


def get_week_label(thu: date, wed: date) -> str:
    return f"{thu.strftime('%Y.%m.%d')} (목) ~ {wed.strftime('%Y.%m.%d')} (수)"


def assign_week_period(row_date: date, year: int, month: int) -> str:
    """날짜를 해당 월의 몇 번째 주차로 분류 (목~수 기준)"""
    # 해당 월의 첫 번째 목요일 찾기
    first_day = date(year, month, 1)
    days_to_thu = (3 - first_day.weekday()) % 7
    first_thu = first_day + timedelta(days=days_to_thu)
    if first_thu.month != month:
        first_thu += timedelta(weeks=1)

    for week_num in range(1, 7):
        thu = first_thu + timedelta(weeks=week_num - 1)
        wed = thu + timedelta(days=6)
        if thu <= row_date <= wed:
            return f"{week_num}주차"
    return "기타"


# ── Google Sheets 연결 ──────────────────────────────────────
@st.cache_resource
def get_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=scopes
    )
    return gspread.authorize(creds)


@st.cache_data(ttl=300)
def load_wemembers() -> pd.DataFrame:
    client = get_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet("위멤버스")
    records = ws.get_all_values()
    if not records or len(records) < 2:
        return pd.DataFrame()
    # 헤더 없이 올라온 경우 대비: 컬럼명 직접 지정
    # 업로드된 열: D(사업자번호), E(상호명), I(상품명), S(가입일) → 0,1,2,3
    df = pd.DataFrame(records[1:], columns=["사업자번호", "상호명", "상품명", "가입일"])
    df = df[df["가입일"].str.strip() != ""]
    df["가입일"] = pd.to_datetime(df["가입일"], errors="coerce")
    df = df.dropna(subset=["가입일"])
    df["가입일"] = df["가입일"].dt.date
    df["연도"] = df["가입일"].apply(lambda d: d.year)
    df["월"]   = df["가입일"].apply(lambda d: d.month)
    df["분기"] = df["월"].map(QUARTERS)
    return df


# ── 목표 저장/불러오기 (session_state) ──────────────────────
def get_target_key(year: int, month: int) -> str:
    return f"target_{year}_{month}"


def load_targets() -> dict:
    if "monthly_targets" not in st.session_state:
        st.session_state["monthly_targets"] = {}
    return st.session_state["monthly_targets"]


def save_target(year: int, month: int, value: int):
    if "monthly_targets" not in st.session_state:
        st.session_state["monthly_targets"] = {}
    st.session_state["monthly_targets"][get_target_key(year, month)] = value


def get_target(year: int, month: int) -> int:
    targets = load_targets()
    return targets.get(get_target_key(year, month), 0)


# ════════════════════════════════════════════════════════════
# UI 시작
# ════════════════════════════════════════════════════════════
st.markdown('<div class="main-title">📈 위멤버스 실적 보고서</div>', unsafe_allow_html=True)

col_refresh, col_space = st.columns([1, 9])
with col_refresh:
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()

# ── 데이터 로드 ────────────────────────────────────────────
try:
    df = load_wemembers()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

if df.empty:
    st.info("📭 위멤버스 시트에 데이터가 없습니다. 먼저 업로드해주세요.")
    st.stop()

# 위멤버스 상품만 필터
df_wm = df[df["상품명"].isin(WM_PRODUCTS)].copy()

# ── 기간 선택 ──────────────────────────────────────────────
st.divider()
available_years = sorted(df_wm["연도"].unique(), reverse=True)
sel_year = st.selectbox("📅 연도 선택", available_years, index=0)

tab_weekly, tab_monthly, tab_quarterly, tab_target = st.tabs([
    "📆 주간 실적", "📅 월별 실적", "📊 분기별 실적", "🎯 목표 관리"
])


# ════════════════════════════════════════════════════════════
# 탭 1: 주간 실적
# ════════════════════════════════════════════════════════════
with tab_weekly:
    today = date.today()
    thu, wed = get_week_range(today)

    st.markdown(
        f'<div class="week-range">📌 현재 보고 기준 주간: {get_week_label(thu, wed)}</div>',
        unsafe_allow_html=True,
    )

    df_year = df_wm[df_wm["연도"] == sel_year]

    # 이번 주 데이터
    df_thisweek = df_year[
        (df_year["가입일"] >= thu) & (df_year["가입일"] <= wed)
    ]

    # 지난 주
    last_thu = thu - timedelta(weeks=1)
    last_wed = wed - timedelta(weeks=1)
    df_lastweek = df_year[
        (df_year["가입일"] >= last_thu) & (df_year["가입일"] <= last_wed)
    ]

    c1, c2, c3 = st.columns(3)
    this_cnt = len(df_thisweek)
    last_cnt = len(df_lastweek)
    diff = this_cnt - last_cnt

    with c1:
        st.markdown(f"""
        <div class="kpi-card">
          <div class="kpi-label">이번 주 신규</div>
          <div class="kpi-value">{this_cnt}건</div>
          <div class="kpi-sub">{thu.strftime('%m.%d')} ~ {wed.strftime('%m.%d')}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="kpi-card">
          <div class="kpi-label">지난 주 신규</div>
          <div class="kpi-value">{last_cnt}건</div>
          <div class="kpi-sub">{last_thu.strftime('%m.%d')} ~ {last_wed.strftime('%m.%d')}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        diff_cls = "kpi-good" if diff >= 0 else "kpi-bad"
        diff_str = f"+{diff}" if diff >= 0 else str(diff)
        st.markdown(f"""
        <div class="kpi-card">
          <div class="kpi-label">전주 대비</div>
          <div class="kpi-value"><span class="{diff_cls}">{diff_str}건</span></div>
          <div class="kpi-sub">전주 대비 증감</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # 이번 주 상품별 분류
    if not df_thisweek.empty:
        st.subheader("이번 주 상품별 현황")
        prod_cnt = df_thisweek.groupby("상품명").size().reset_index(name="건수")
        fig = px.bar(prod_cnt, x="상품명", y="건수",
                     color="상품명",
                     color_discrete_sequence=["#0066FF", "#1A3A8F"],
                     height=300, text="건수")
        fig.update_traces(textposition="outside")
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          font_family="Noto Sans KR", showlegend=False,
                          margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📋 이번 주 신규 고객 목록"):
            st.dataframe(
                df_thisweek[["상호명", "상품명", "가입일"]].reset_index(drop=True),
                use_container_width=True,
            )
    else:
        st.info("이번 주 신규 데이터가 없습니다.")

    # 최근 8주 트렌드
    st.subheader("최근 8주 주간 트렌드")
    week_data = []
    for i in range(7, -1, -1):
        w_thu = thu - timedelta(weeks=i)
        w_wed = wed - timedelta(weeks=i)
        cnt = len(df_year[(df_year["가입일"] >= w_thu) & (df_year["가입일"] <= w_wed)])
        week_data.append({"주간": f"{w_thu.strftime('%m.%d')}~{w_wed.strftime('%m.%d')}", "건수": cnt})
    df_weeks = pd.DataFrame(week_data)
    fig2 = px.line(df_weeks, x="주간", y="건수", markers=True,
                   color_discrete_sequence=["#0066FF"], height=300)
    fig2.update_traces(line_width=2.5, marker_size=8)
    fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                       font_family="Noto Sans KR", margin=dict(t=20, b=20))
    st.plotly_chart(fig2, use_container_width=True)


# ════════════════════════════════════════════════════════════
# 탭 2: 월별 실적
# ════════════════════════════════════════════════════════════
with tab_monthly:
    df_year = df_wm[df_wm["연도"] == sel_year]

    # 월별 집계
    monthly = df_year.groupby("월").size().reset_index(name="신규건수")
    monthly["월명"] = monthly["월"].map(MONTH_NAMES)
    monthly["목표"] = monthly["월"].apply(lambda m: get_target(sel_year, m))
    monthly["달성률"] = monthly.apply(
        lambda r: round(r["신규건수"] / r["목표"] * 100, 1) if r["목표"] > 0 else None, axis=1
    )

    # 현재 월 주차별 분류
    sel_month = st.selectbox("월 선택 (주차 상세)", list(MONTH_NAMES.keys()),
                             index=min(date.today().month - 1, 11),
                             format_func=lambda m: MONTH_NAMES[m])

    df_month = df_year[df_year["월"] == sel_month].copy()
    target_val = get_target(sel_year, sel_month)

    # KPI 카드
    total_month = len(df_month)
    rate = round(total_month / target_val * 100, 1) if target_val > 0 else None

    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(f"""
        <div class="kpi-card">
          <div class="kpi-label">{sel_year}년 {MONTH_NAMES[sel_month]} 신규</div>
          <div class="kpi-value">{total_month}건</div>
        </div>""", unsafe_allow_html=True)
    with k2:
        target_disp = f"{target_val}건" if target_val > 0 else "미설정"
        st.markdown(f"""
        <div class="kpi-card">
          <div class="kpi-label">월 목표</div>
          <div class="kpi-value">{target_disp}</div>
        </div>""", unsafe_allow_html=True)
    with k3:
        if rate is not None:
            rate_cls = "kpi-good" if rate >= 100 else ("kpi-bad" if rate < 70 else "")
            rate_html = f'<span class="{rate_cls}">{rate}%</span>'
        else:
            rate_html = '<span style="color:#94a3b8">-</span>'
        st.markdown(f"""
        <div class="kpi-card">
          <div class="kpi-label">목표 달성률</div>
          <div class="kpi-value">{rate_html}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # 주차별 분류
    if not df_month.empty:
        df_month["주차"] = df_month["가입일"].apply(
            lambda d: assign_week_period(d, sel_year, sel_month)
        )
        week_cnt = df_month.groupby("주차").size().reset_index(name="건수")
        week_order = [f"{i}주차" for i in range(1, 7)] + ["기타"]
        week_cnt["주차"] = pd.Categorical(week_cnt["주차"], categories=week_order, ordered=True)
        week_cnt = week_cnt.sort_values("주차")

        st.subheader(f"{MONTH_NAMES[sel_month]} 주차별 신규 현황")
        fig = px.bar(week_cnt, x="주차", y="건수",
                     color_discrete_sequence=["#0066FF"],
                     height=280, text="건수")
        fig.update_traces(textposition="outside")
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          font_family="Noto Sans KR", showlegend=False,
                          margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # 연간 월별 추이
    st.subheader(f"{sel_year}년 월별 신규 현황")
    all_months = pd.DataFrame({"월": list(range(1, 13))})
    all_months["월명"] = all_months["월"].map(MONTH_NAMES)
    all_months["목표"] = all_months["월"].apply(lambda m: get_target(sel_year, m))
    merged = all_months.merge(
        df_year.groupby("월").size().reset_index(name="신규건수"),
        on="월", how="left"
    ).fillna(0)
    merged["신규건수"] = merged["신규건수"].astype(int)

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=merged["월명"], y=merged["신규건수"],
        name="신규건수", marker_color="#0066FF", text=merged["신규건수"],
        textposition="outside",
    ))
    if merged["목표"].sum() > 0:
        fig2.add_trace(go.Scatter(
            x=merged["월명"], y=merged["목표"],
            name="목표", mode="lines+markers",
            line=dict(color="#f97316", width=2, dash="dash"),
            marker=dict(size=7),
        ))
    fig2.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        font_family="Noto Sans KR", height=350,
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=30, b=20),
    )
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("📋 월별 실적 상세 테이블"):
        show_df = merged[["월명", "신규건수", "목표"]].copy()
        show_df["달성률"] = show_df.apply(
            lambda r: f"{round(r['신규건수']/r['목표']*100,1)}%" if r["목표"] > 0 else "-", axis=1
        )
        st.dataframe(show_df.rename(columns={"월명": "월"}), use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════
# 탭 3: 분기별 실적
# ════════════════════════════════════════════════════════════
with tab_quarterly:
    df_year = df_wm[df_wm["연도"] == sel_year]

    quarterly = df_year.groupby("분기").size().reset_index(name="신규건수")
    q_order = ["1분기", "2분기", "3분기", "4분기"]
    quarterly["분기"] = pd.Categorical(quarterly["분기"], categories=q_order, ordered=True)
    quarterly = quarterly.sort_values("분기")

    st.subheader(f"{sel_year}년 분기별 신규 현황")

    q_cols = st.columns(4)
    for col_w, q in zip(q_cols, q_order):
        row = quarterly[quarterly["분기"] == q]
        cnt = int(row["신규건수"].values[0]) if not row.empty else 0
        with col_w:
            st.markdown(f"""
            <div class="kpi-card">
              <div class="kpi-label">{q}</div>
              <div class="kpi-value">{cnt}건</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")

    fig = px.bar(quarterly, x="분기", y="신규건수",
                 color_discrete_sequence=["#1A3A8F"],
                 height=320, text="신규건수")
    fig.update_traces(textposition="outside")
    fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                      font_family="Noto Sans KR", showlegend=False,
                      margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # 분기 × 상품별 히트맵
    st.subheader("분기 × 상품별 현황")
    pivot = df_year.pivot_table(
        index="상품명", columns="분기", values="사업자번호",
        aggfunc="count", fill_value=0
    )
    pivot = pivot.reindex(columns=[q for q in q_order if q in pivot.columns])
    fig2 = px.imshow(pivot, text_auto=True,
                     color_continuous_scale=[[0, "#eff6ff"], [1, "#0066FF"]],
                     height=250, aspect="auto")
    fig2.update_layout(font_family="Noto Sans KR",
                       coloraxis_showscale=False,
                       margin=dict(t=20, b=20))
    st.plotly_chart(fig2, use_container_width=True)


# ════════════════════════════════════════════════════════════
# 탭 4: 목표 관리
# ════════════════════════════════════════════════════════════
with tab_target:
    st.subheader(f"🎯 {sel_year}년 월별 목표 설정")
    st.caption("목표를 입력하고 저장하면 월별·분기별 달성률에 반영됩니다.")

    targets = load_targets()

    with st.form("target_form"):
        cols_a = st.columns(4)
        cols_b = st.columns(4)
        new_targets = {}

        for i, month in enumerate(range(1, 13)):
            col_w = cols_a[i % 4] if i < 4 else (cols_b[i % 4] if i < 8 else None)
            # 3행 처리
            if i >= 8:
                if i == 8:
                    cols_c = st.columns(4)
                col_w = cols_c[i % 4]

            current = get_target(sel_year, month)
            with col_w:
                new_targets[month] = st.number_input(
                    MONTH_NAMES[month],
                    min_value=0, max_value=9999,
                    value=current, step=1,
                    key=f"input_{sel_year}_{month}",
                )

        submitted = st.form_submit_button("💾 목표 저장", use_container_width=True)
        if submitted:
            for month, val in new_targets.items():
                save_target(sel_year, month, int(val))
            st.success("✅ 목표가 저장되었습니다!")
            st.rerun()

    # 현재 목표 요약
    st.divider()
    st.subheader("현재 설정된 목표")
    summary_rows = []
    df_year = df_wm[df_wm["연도"] == sel_year]
    for month in range(1, 13):
        target = get_target(sel_year, month)
        actual = len(df_year[df_year["월"] == month])
        rate_str = f"{round(actual/target*100,1)}%" if target > 0 else "-"
        summary_rows.append({
            "월": MONTH_NAMES[month],
            "목표": target if target > 0 else "-",
            "실적": actual,
            "달성률": rate_str,
        })
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.info("💡 목표는 브라우저 세션 동안 유지됩니다. 페이지를 새로고침하면 초기화되니 매주 설정해주세요.")

st.divider()
st.markdown("← 좌측 사이드바 상단의 **app** 메뉴를 클릭하세요")
