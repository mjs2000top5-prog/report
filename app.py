import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime, timedelta, date

st.set_page_config(
    page_title="위멤버스 실적 관리",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

.main-title {
    font-size: 2rem; font-weight: 700;
    background: linear-gradient(135deg, #1A3A8F, #0066FF);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.1rem;
}
.subtitle { color: #64748b; font-size: 0.9rem; margin-bottom: 1.5rem; }

.sheet-card {
    background: #f8faff; border: 1px solid #e2e8f0;
    border-left: 4px solid #0066FF; border-radius: 8px;
    padding: 0.8rem 1rem; margin: 0.3rem 0;
}
.sheet-card p { margin: 0; color: #64748b; font-size: 0.82rem; }

.success-box {
    background: #f0fdf4; border: 1px solid #86efac;
    border-radius: 8px; padding: 1rem; margin: 1rem 0; color: #166534;
}
.kpi-card {
    background: #f8faff; border: 1px solid #e2e8f0;
    border-radius: 12px; padding: 1.1rem 1rem; text-align: center;
}
.kpi-label { color: #64748b; font-size: 0.8rem; margin-bottom: 0.3rem; }
.kpi-value { color: #1A3A8F; font-size: 1.9rem; font-weight: 700; line-height: 1.1; }
.kpi-sub   { color: #94a3b8; font-size: 0.76rem; margin-top: 0.2rem; }
.kpi-good  { color: #16a34a; font-weight: 600; }
.kpi-bad   { color: #dc2626; font-weight: 600; }
.week-badge {
    display: inline-block;
    background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 8px; padding: 0.5rem 1rem;
    color: #1e40af; font-size: 0.86rem; font-weight: 500;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 상수
# ══════════════════════════════════════════════════════════
SPREADSHEET_ID = "1k2FcMog8G75apAxUAJsCuHE10hQHSmImFofX1ZTSYwk"

SHEET_CONFIG = {
    "위멤버스":  {"cols": ["D","E","I","S"],  "col_idx": [3,4,8,18],  "icon": "📗"},
    "경리나라T": {"cols": ["D","E","I","V"],  "col_idx": [3,4,8,21],  "icon": "📘"},
    "경리나라":  {"cols": ["D","E","P","W"],  "col_idx": [3,4,15,22], "icon": "📙"},
}

WM_PRODUCTS = ["위멤버스 스탠다드", "위멤버스 프리미엄"]
QUARTERS    = {m: f"{(m-1)//3+1}분기" for m in range(1, 13)}
MONTH_NAMES = {m: f"{m}월" for m in range(1, 13)}


# ══════════════════════════════════════════════════════════
# Google Sheets 연결
# ══════════════════════════════════════════════════════════
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


def get_worksheet(sheet_name: str):
    return get_client().open_by_key(SPREADSHEET_ID).worksheet(sheet_name)


# ══════════════════════════════════════════════════════════
# 업로드 유틸
# ══════════════════════════════════════════════════════════
def extract_columns(df: pd.DataFrame, col_indices: list) -> pd.DataFrame:
    valid = [i for i in col_indices if i < len(df.columns)]
    return df.iloc[:, valid]


def df_to_sheet_values(df: pd.DataFrame) -> list:
    rows = []
    for _, row in df.iterrows():
        processed = []
        for val in row:
            try:
                if pd.isna(val):
                    processed.append(""); continue
            except (TypeError, ValueError):
                pass
            if isinstance(val, (pd.Timestamp, datetime)):
                processed.append(str(val.date()))
            elif isinstance(val, np.integer):
                processed.append(int(val))
            elif isinstance(val, np.floating):
                processed.append(float(val))
            else:
                processed.append(val if isinstance(val, (int, float)) else str(val))
        rows.append(processed)
    return rows


def upload_to_sheet(sheet_name: str, df: pd.DataFrame, col_indices: list) -> int:
    ws = get_worksheet(sheet_name)
    extracted = extract_columns(df, col_indices)
    header = extracted.iloc[0].tolist() if len(extracted) > 0 else []
    data   = df_to_sheet_values(extracted.iloc[1:])
    ws.clear()
    all_vals = [header] + data if header else data
    if all_vals:
        ws.update("A1", all_vals, value_input_option="USER_ENTERED")
    return len(data)


# ══════════════════════════════════════════════════════════
# 보고서 유틸
# ══════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def load_wemembers() -> pd.DataFrame:
    ws      = get_worksheet("위멤버스")
    records = ws.get_all_values()
    if not records or len(records) < 2:
        return pd.DataFrame()
    df = pd.DataFrame(records[1:], columns=["사업자번호","상호명","상품명","가입일"])
    df = df[df["가입일"].str.strip() != ""]
    df["가입일"] = pd.to_datetime(df["가입일"], errors="coerce").dt.date
    df = df.dropna(subset=["가입일"])
    df["연도"] = df["가입일"].apply(lambda d: d.year)
    df["월"]   = df["가입일"].apply(lambda d: d.month)
    df["분기"] = df["월"].map(QUARTERS)
    return df


def get_week_range(ref: date):
    days_since_thu = (ref.weekday() - 3) % 7
    thu = ref - timedelta(days=days_since_thu)
    return thu, thu + timedelta(days=6)


def assign_week(d: date, year: int, month: int) -> str:
    first = date(year, month, 1)
    shift = (3 - first.weekday()) % 7
    first_thu = first + timedelta(days=shift)
    if first_thu.month != month:
        first_thu += timedelta(weeks=1)
    for w in range(1, 7):
        thu = first_thu + timedelta(weeks=w-1)
        if thu <= d <= thu + timedelta(days=6):
            return f"{w}주차"
    return "기타"


def get_target(year: int, month: int) -> int:
    return st.session_state.get("monthly_targets", {}).get(f"{year}_{month}", 0)


def save_target(year: int, month: int, val: int):
    if "monthly_targets" not in st.session_state:
        st.session_state["monthly_targets"] = {}
    st.session_state["monthly_targets"][f"{year}_{month}"] = val


# ══════════════════════════════════════════════════════════
# 헤더
# ══════════════════════════════════════════════════════════
st.markdown('<div class="main-title">📊 위멤버스 실적 관리</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">데이터 업로드 · 월별 보고서 · 목표 관리</div>', unsafe_allow_html=True)

# 메인 탭
TAB_UPLOAD, TAB_MONTHLY, TAB_TARGET = st.tabs([
    "📤 데이터 업로드",
    "📅 월별 실적",
    "🎯 목표 관리",
])


# ══════════════════════════════════════════════════════════
# 탭 1 — 데이터 업로드
# ══════════════════════════════════════════════════════════
with TAB_UPLOAD:
    st.subheader("① 업로드할 시트 선택")
    st.caption("여러 시트를 동시에 선택할 수 있습니다.")

    c1, c2, c3 = st.columns(3)
    sheet_checks = {}
    for col_w, (sname, cfg) in zip([c1, c2, c3], SHEET_CONFIG.items()):
        with col_w:
            sheet_checks[sname] = st.checkbox(
                f"{cfg['icon']} **{sname}**", value=True, key=f"ck_{sname}"
            )
            st.markdown(
                f"<div class='sheet-card'><p>업로드 열: {', '.join(cfg['cols'])}</p></div>",
                unsafe_allow_html=True,
            )

    selected = [s for s, v in sheet_checks.items() if v]
    if not selected:
        st.warning("⚠️ 업로드할 시트를 1개 이상 선택해주세요.")

    st.divider()
    st.subheader("② 엑셀 파일 업로드")
    uploaded = st.file_uploader(
        "엑셀 파일 선택 (.xlsx / .xls)", type=["xlsx","xls"],
        help="다운로드 받은 실적 엑셀 파일을 드래그하거나 클릭해 업로드하세요."
    )

    if uploaded:
        try:
            df_raw = pd.read_excel(uploaded, header=0)
            st.success(f"✅ **{uploaded.name}** 로드 완료 ({len(df_raw):,}행 × {len(df_raw.columns)}열)")

            with st.expander("📋 원본 데이터 미리보기 (상위 5행)"):
                st.dataframe(df_raw.head(), use_container_width=True)

            if selected:
                st.subheader("선택된 시트 미리보기")
                preview_tabs = st.tabs([f"{SHEET_CONFIG[s]['icon']} {s}" for s in selected])
                for pt, sname in zip(preview_tabs, selected):
                    with pt:
                        cfg     = SHEET_CONFIG[sname]
                        preview = extract_columns(df_raw, cfg["col_idx"])
                        st.caption(f"열 {', '.join(cfg['cols'])} — {max(0, len(preview)-1):,}건")
                        st.dataframe(preview.head(10), use_container_width=True)

            st.divider()

            btn_label = f"🚀 업로드 ({', '.join(selected)})" if selected else "🚀 업로드"
            if selected and st.button(btn_label, use_container_width=True, key="upload_btn"):
                try:
                    results  = {}
                    total    = len(selected)
                    progress = st.progress(0, text="업로드 중...")
                    for i, sname in enumerate(selected):
                        progress.progress(i / total, text=f"📤 {sname} 업로드 중...")
                        cfg            = SHEET_CONFIG[sname]
                        results[sname] = upload_to_sheet(sname, df_raw, cfg["col_idx"])
                    progress.progress(1.0, text="완료!")
                    st.cache_data.clear()   # 보고서 캐시 초기화

                    st.markdown('<div class="success-box">', unsafe_allow_html=True)
                    st.markdown("### ✅ 업로드 완료!")
                    for sname, cnt in results.items():
                        st.markdown(f"- **{SHEET_CONFIG[sname]['icon']} {sname}**: {cnt:,}건")
                    st.markdown(
                        f"[📊 Google Sheets에서 확인하기](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)"
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"❌ 업로드 실패: {e}")
        except Exception as e:
            st.error(f"❌ 파일 읽기 실패: {e}")


# ══════════════════════════════════════════════════════════
# 보고서 공통 — 데이터 로드
# ══════════════════════════════════════════════════════════
def load_report_data():
    try:
        df = load_wemembers()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return None, None
    if df.empty:
        st.info("📭 위멤버스 시트에 데이터가 없습니다. 먼저 [데이터 업로드] 탭에서 업로드해주세요.")
        return None, None
    df_wm = df[df["상품명"].isin(WM_PRODUCTS)].copy()
    available_years = sorted(df_wm["연도"].unique(), reverse=True)
    return df_wm, available_years


# ══════════════════════════════════════════════════════════
# 탭 2 — 주간 실적
# ══════════════════════════════════════════════════════════
    df_wm, available_years = load_report_data()
    if df_wm is not None:
        col_yr, _ = st.columns([2, 8])
        with col_yr:
            sel_year = st.selectbox("연도", available_years, key="yr_monthly")

        df_year = df_wm[df_wm["연도"] == sel_year]

        # ── 연간 목표 입력 (사이드 인라인) ──────────────────
        annual_target = sum(get_target(sel_year, m) for m in range(1, 13))
        total_actual  = len(df_year)
        annual_rate   = round(total_actual / annual_target * 100, 1) if annual_target > 0 else 0

        # ── 🏆 위멤버스 연간 성과 ────────────────────────────
        st.markdown("### 🏆 위멤버스 연간 성과")
        a1, a2, a3 = st.columns(3)
        with a1:
            rate_cls = "kpi-good" if annual_rate >= 100 else ("kpi-bad" if annual_rate < 50 else "")
            st.markdown(f"""<div class="kpi-card">
              <div class="kpi-label">누적 달성률</div>
              <div class="kpi-value"><span class="{rate_cls}">{annual_rate}%</span></div>
            </div>""", unsafe_allow_html=True)
        with a2:
            st.markdown(f"""<div class="kpi-card">
              <div class="kpi-label">누적 실적</div>
              <div class="kpi-value">{total_actual}건</div>
            </div>""", unsafe_allow_html=True)
        with a3:
            st.markdown(f"""<div class="kpi-card">
              <div class="kpi-label">연간 목표</div>
              <div class="kpi-value">{"미설정" if annual_target == 0 else f"{annual_target}건"}</div>
            </div>""", unsafe_allow_html=True)

        st.divider()

        # ── 📅 월별 상세 실적 테이블 ─────────────────────────
        st.markdown("### 📅 월별 상세 실적 (최신월 증감 포함)")

        # 상품별 월별 피벗
        std_monthly  = df_year[df_year["상품명"] == "위멤버스 스탠다드"].groupby("월").size()
        prem_monthly = df_year[df_year["상품명"] == "위멤버스 프리미엄"].groupby("월").size()

        # 현재까지 실적 있는 월만
        active_months = sorted(df_year["월"].unique())

        rows_monthly = []
        prev_std, prev_prem = None, None
        for m in active_months:
            std_cnt  = int(std_monthly.get(m, 0))
            prem_cnt = int(prem_monthly.get(m, 0))
            total_m  = std_cnt + prem_cnt
            target_m = get_target(sel_year, m)
            rate_m   = round(total_m / target_m * 100, 1) if target_m > 0 else None

            # 증감 표시 (최신월에만)
            is_latest = (m == max(active_months))
            if is_latest and prev_std is not None:
                std_diff  = std_cnt  - prev_std
                prem_diff = prem_cnt - prev_prem
                std_label  = f"{std_cnt}(▲{std_diff})"  if std_diff > 0 else \
                             (f"{std_cnt}(▼{abs(std_diff)})" if std_diff < 0 else str(std_cnt))
                prem_label = f"{prem_cnt}(▲{prem_diff})" if prem_diff > 0 else \
                             (f"{prem_cnt}(▼{abs(prem_diff)})" if prem_diff < 0 else str(prem_cnt))
            else:
                std_label  = str(std_cnt)
                prem_label = str(prem_cnt)

            rows_monthly.append({
                "월":             m,
                "위멤버스 스탠다드": std_label,
                "위멤버스 프리미엄": prem_label,
                "실적합계":        total_m,
                "목표":           target_m if target_m > 0 else "-",
                "달성률":         f"{rate_m}%" if rate_m is not None else "-",
            })
            prev_std, prev_prem = std_cnt, prem_cnt

        df_monthly_table = pd.DataFrame(rows_monthly)
        st.dataframe(df_monthly_table, use_container_width=True, hide_index=True)

        st.divider()

        # ── 📊 분기별 실적 테이블 ────────────────────────────
        st.markdown("### 📊 분기별 실적")

        q_order = ["1분기","2분기","3분기","4분기"]
        rows_q  = []
        for qi, q in enumerate(q_order, 1):
            months_in_q = [m for m in range(1,13) if QUARTERS[m] == q]
            df_q      = df_year[df_year["월"].isin(months_in_q)]
            std_q     = int((df_q["상품명"] == "위멤버스 스탠다드").sum())
            prem_q    = int((df_q["상품명"] == "위멤버스 프리미엄").sum())
            total_q   = std_q + prem_q
            target_q  = sum(get_target(sel_year, m) for m in months_in_q)
            rate_q    = round(total_q / target_q * 100, 1) if target_q > 0 else None
            rows_q.append({
                "분기":           qi,
                "위멤버스 스탠다드": std_q,
                "위멤버스 프리미엄": prem_q,
                "목표":           target_q if target_q > 0 else "-",
                "실적합계":        total_q,
                "달성률":         f"{rate_q}%" if rate_q is not None else "-",
            })

        df_q_table = pd.DataFrame(rows_q)
        st.dataframe(df_q_table, use_container_width=True, hide_index=True)

        st.divider()

        # ── 월별 바 차트 + 목표선 ───────────────────────────
        st.markdown("### 📈 월별 신규 추이")
        base = pd.DataFrame({"월": range(1,13)})
        base["월명"] = base["월"].map(MONTH_NAMES)
        base["목표"] = base["월"].apply(lambda m: get_target(sel_year, m))
        base = base.merge(df_year.groupby("월").size().reset_index(name="신규건수"),
                          on="월", how="left").fillna(0)
        base["신규건수"] = base["신규건수"].astype(int)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=base["월명"], y=base["신규건수"],
                             name="신규건수", marker_color="#0066FF",
                             text=base["신규건수"], textposition="outside"))
        if base["목표"].sum() > 0:
            fig.add_trace(go.Scatter(x=base["월명"], y=base["목표"],
                                     name="목표", mode="lines+markers",
                                     line=dict(color="#f97316", width=2, dash="dash"),
                                     marker=dict(size=7)))
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          font_family="Noto Sans KR", height=320,
                          legend=dict(orientation="h", y=1.08),
                          margin=dict(t=30,b=10))
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════
# 탭 4 — 분기별 실적
# ══════════════════════════════════════════════════════════
with TAB_TARGET:
    df_wm, available_years = load_report_data()
    if df_wm is not None:
        sel_year = st.selectbox("연도", available_years, key="yr_target")
        st.subheader(f"🎯 {sel_year}년 월별 목표 설정")
        st.caption("목표를 입력하고 저장하면 월별·분기별 달성률에 즉시 반영됩니다.")

        with st.form("target_form"):
            rows_of_cols = [st.columns(4) for _ in range(3)]
            new_targets  = {}
            for i, month in enumerate(range(1, 13)):
                cw = rows_of_cols[i // 4][i % 4]
                with cw:
                    new_targets[month] = st.number_input(
                        MONTH_NAMES[month], min_value=0, max_value=9999,
                        value=get_target(sel_year, month), step=1,
                        key=f"tgt_{sel_year}_{month}",
                    )
            if st.form_submit_button("💾 목표 저장", use_container_width=True):
                for m, v in new_targets.items():
                    save_target(sel_year, m, int(v))
                st.success("✅ 목표가 저장되었습니다!")
                st.rerun()

        st.divider()
        st.subheader("현재 목표 vs 실적")
        df_year = df_wm[df_wm["연도"] == sel_year]
        rows = []
        for m in range(1, 13):
            t = get_target(sel_year, m)
            a = len(df_year[df_year["월"] == m])
            rows.append({
                "월":    MONTH_NAMES[m],
                "목표":  t if t > 0 else "-",
                "실적":  a,
                "달성률": f"{round(a/t*100,1)}%" if t > 0 else "-",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.info("💡 목표는 브라우저 세션 동안 유지됩니다. 새로고침 시 초기화됩니다.")
