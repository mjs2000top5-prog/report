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
.subtitle { color: #64748b; font-size: 0.9rem; margin-bottom: 1rem; }

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

.section-title {
    font-size: 1.15rem; font-weight: 700; color: #1e293b;
    margin: 1.4rem 0 0.8rem;
}
.annual-kpi {
    background: white; border: 1px solid #e2e8f0;
    border-radius: 10px; padding: 1rem 1.2rem;
}
.annual-kpi .label { color: #64748b; font-size: 0.8rem; margin-bottom: 0.3rem; }
.annual-kpi .value { color: #1A3A8F; font-size: 2.2rem; font-weight: 700; }
.text-good { color: #16a34a !important; }
.text-bad  { color: #dc2626 !important; }
.text-warn { color: #d97706 !important; }

.report-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-bottom: 0.5rem; }
.report-table th {
    background: #f1f5f9; color: #475569; font-weight: 600;
    padding: 0.6rem 0.8rem; text-align: right; border-bottom: 2px solid #e2e8f0;
}
.report-table th:first-child { text-align: left; }
.report-table td {
    padding: 0.55rem 0.8rem; text-align: right;
    border-bottom: 1px solid #f1f5f9; color: #334155;
}
.report-table td:first-child { text-align: left; font-weight: 500; color: #1e293b; }
.report-table tr:last-child td { border-bottom: none; }
.report-table tr:hover td { background: #f8faff; }
.badge-up   { color: #16a34a; font-size: 0.78rem; }
.badge-down { color: #dc2626; font-size: 0.78rem; }

.week-badge {
    display: inline-block;
    background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 8px; padding: 0.4rem 0.9rem;
    color: #1e40af; font-size: 0.84rem; font-weight: 500;
    margin-bottom: 0.8rem;
}
.divider-soft { border: none; border-top: 1px solid #e2e8f0; margin: 1.5rem 0; }
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
CURRENT_YEAR = date.today().year
# 목표 관리용 연도: 2026부터 현재+3년까지
TARGET_YEARS = list(range(2026, CURRENT_YEAR + 4))


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
    ws        = get_worksheet(sheet_name)
    extracted = extract_columns(df, col_indices)
    header    = extracted.iloc[0].tolist() if len(extracted) > 0 else []
    data      = df_to_sheet_values(extracted.iloc[1:])
    ws.clear()
    all_vals  = [header] + data if header else data
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


def get_target(year: int, month: int) -> int:
    return st.session_state.get("monthly_targets", {}).get(f"{year}_{month}", 0)


def save_target(year: int, month: int, val: int):
    if "monthly_targets" not in st.session_state:
        st.session_state["monthly_targets"] = {}
    st.session_state["monthly_targets"][f"{year}_{month}"] = val


def load_report_data():
    try:
        df = load_wemembers()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return None, None
    if df.empty:
        st.info("📭 위멤버스 시트에 데이터가 없습니다. [데이터 업로드] 탭에서 먼저 업로드해주세요.")
        return None, None
    df_wm = df[df["상품명"].isin(WM_PRODUCTS)].copy()
    return df_wm, sorted(df_wm["연도"].unique(), reverse=True)


def rate_color(rate):
    if rate is None: return ""
    if rate >= 100:  return "text-good"
    if rate < 70:    return "text-bad"
    return "text-warn"


# ══════════════════════════════════════════════════════════
# 헤더
# ══════════════════════════════════════════════════════════
st.markdown('<div class="main-title">📊 위멤버스 실적 관리</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">데이터 업로드 · 실적 보고서 · 목표 관리</div>', unsafe_allow_html=True)

TAB_UPLOAD, TAB_REPORT, TAB_TARGET = st.tabs([
    "📤 데이터 업로드",
    "📋 실적 보고서",
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
                        results[sname] = upload_to_sheet(sname, df_raw, SHEET_CONFIG[sname]["col_idx"])
                    progress.progress(1.0, text="완료!")
                    st.cache_data.clear()

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
# 탭 2 — 실적 보고서 (연간성과 + 월별 + 분기별 + 주간)
# ══════════════════════════════════════════════════════════
with TAB_REPORT:
    df_wm, available_years = load_report_data()
    if df_wm is not None:

        col_yr, col_refresh, _ = st.columns([2, 1, 7])
        with col_yr:
            sel_year = st.selectbox("연도", available_years, key="yr_report")
        with col_refresh:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("🔄", help="데이터 새로고침"):
                st.cache_data.clear()
                st.rerun()

        df_year       = df_wm[df_wm["연도"] == sel_year]
        annual_target = sum(get_target(sel_year, m) for m in range(1, 13))
        total_actual  = len(df_year)
        annual_rate   = round(total_actual / annual_target * 100, 1) if annual_target > 0 else 0

        # ────────────────────────────────────────────────
        # 🏆 연간 성과
        # ────────────────────────────────────────────────
        st.markdown('<div class="section-title">🏆 위멤버스 연간 성과</div>', unsafe_allow_html=True)
        a1, a2, a3 = st.columns(3)
        rate_cls = rate_color(annual_rate)
        with a1:
            st.markdown(f"""<div class="annual-kpi">
              <div class="label">누적 달성률</div>
              <div class="value {rate_cls}">{annual_rate}%</div>
            </div>""", unsafe_allow_html=True)
        with a2:
            st.markdown(f"""<div class="annual-kpi">
              <div class="label">누적 실적</div>
              <div class="value">{total_actual}건</div>
            </div>""", unsafe_allow_html=True)
        with a3:
            st.markdown(f"""<div class="annual-kpi">
              <div class="label">연간 목표</div>
              <div class="value">{"미설정" if annual_target == 0 else f"{annual_target}건"}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown('<hr class="divider-soft">', unsafe_allow_html=True)

        # ────────────────────────────────────────────────
        # 📅 월별 상세 실적
        # ────────────────────────────────────────────────
        st.markdown('<div class="section-title">📅 월별 상세 실적 (최신월 증감 포함)</div>', unsafe_allow_html=True)

        std_monthly   = df_year[df_year["상품명"] == "위멤버스 스탠다드"].groupby("월").size()
        prem_monthly  = df_year[df_year["상품명"] == "위멤버스 프리미엄"].groupby("월").size()
        active_months = sorted(df_year["월"].unique())

        thead = """<table class="report-table"><thead><tr>
          <th>월</th><th>위멤버스 스탠다드</th><th>위멤버스 프리미엄</th>
          <th>실적합계</th><th>목표</th><th>달성률</th>
        </tr></thead><tbody>"""
        tbody = ""
        for m in active_months:
            std_cnt  = int(std_monthly.get(m, 0))
            prem_cnt = int(prem_monthly.get(m, 0))
            total_m  = std_cnt + prem_cnt
            target_m = get_target(sel_year, m)
            rate_m   = round(total_m / target_m * 100, 1) if target_m > 0 else None

            tbody += f"""<tr>
              <td>{m}</td><td>{std_cnt}</td><td>{prem_cnt}</td>
              <td><strong>{total_m}</strong></td>
              <td>{target_m if target_m > 0 else "-"}</td>
              <td class="{rate_color(rate_m)}"><strong>{f"{rate_m}%" if rate_m is not None else "-"}</strong></td>
            </tr>"""

        st.markdown(thead + tbody + "</tbody></table>", unsafe_allow_html=True)

        st.markdown('<hr class="divider-soft">', unsafe_allow_html=True)

        # ────────────────────────────────────────────────
        # 📊 분기별 실적
        # ────────────────────────────────────────────────
        st.markdown('<div class="section-title">📊 분기별 실적</div>', unsafe_allow_html=True)

        q_order = ["1분기","2분기","3분기","4분기"]
        q_thead = """<table class="report-table"><thead><tr>
          <th>분기</th><th>위멤버스 스탠다드</th><th>위멤버스 프리미엄</th>
          <th>목표</th><th>실적합계</th><th>달성률</th>
        </tr></thead><tbody>"""
        q_tbody = ""
        for qi, q in enumerate(q_order, 1):
            months_in_q = [m for m in range(1,13) if QUARTERS[m] == q]
            df_q     = df_year[df_year["월"].isin(months_in_q)]
            if df_q.empty: continue
            std_q    = int((df_q["상품명"] == "위멤버스 스탠다드").sum())
            prem_q   = int((df_q["상품명"] == "위멤버스 프리미엄").sum())
            total_q  = std_q + prem_q
            target_q = sum(get_target(sel_year, m) for m in months_in_q)
            rate_q   = round(total_q / target_q * 100, 1) if target_q > 0 else None
            q_tbody += f"""<tr>
              <td>{qi}</td><td>{std_q}</td><td>{prem_q}</td>
              <td>{target_q if target_q > 0 else "-"}</td>
              <td><strong>{total_q}</strong></td>
              <td class="{rate_color(rate_q)}"><strong>{f"{rate_q}%" if rate_q is not None else "-"}</strong></td>
            </tr>"""

        st.markdown(q_thead + q_tbody + "</tbody></table>", unsafe_allow_html=True)

        st.markdown('<hr class="divider-soft">', unsafe_allow_html=True)

        # ────────────────────────────────────────────────
        # 📆 주간 실적
        # ────────────────────────────────────────────────
        st.markdown('<div class="section-title">📆 주간 실적</div>', unsafe_allow_html=True)

        today    = date.today()
        thu, wed = get_week_range(today)
        st.markdown(
            f'<div class="week-badge">📌 현재 보고 기준 주간: '
            f'{thu.strftime("%Y.%m.%d")} (목) ~ {wed.strftime("%Y.%m.%d")} (수)</div>',
            unsafe_allow_html=True,
        )

        last_thu = thu - timedelta(weeks=1)
        last_wed = wed - timedelta(weeks=1)
        df_this  = df_year[(df_year["가입일"] >= thu)      & (df_year["가입일"] <= wed)]
        df_last  = df_year[(df_year["가입일"] >= last_thu) & (df_year["가입일"] <= last_wed)]
        diff     = len(df_this) - len(df_last)
        diff_cls = "text-good" if diff >= 0 else "text-bad"
        diff_str = f"+{diff}" if diff >= 0 else str(diff)

        w1, w2, w3 = st.columns(3)
        with w1:
            st.markdown(f"""<div class="annual-kpi">
              <div class="label">이번 주 신규</div>
              <div class="value">{len(df_this)}건</div>
              <div style="color:#94a3b8;font-size:0.76rem;margin-top:0.2rem">
                {thu.strftime('%m.%d')} ~ {wed.strftime('%m.%d')}</div>
            </div>""", unsafe_allow_html=True)
        with w2:
            st.markdown(f"""<div class="annual-kpi">
              <div class="label">지난 주 신규</div>
              <div class="value">{len(df_last)}건</div>
              <div style="color:#94a3b8;font-size:0.76rem;margin-top:0.2rem">
                {last_thu.strftime('%m.%d')} ~ {last_wed.strftime('%m.%d')}</div>
            </div>""", unsafe_allow_html=True)
        with w3:
            st.markdown(f"""<div class="annual-kpi">
              <div class="label">전주 대비</div>
              <div class="value {diff_cls}">{diff_str}건</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("")

        if not df_this.empty:
            prod_cnt = df_this.groupby("상품명").size().reset_index(name="건수")
            w_thead  = """<table class="report-table">
              <thead><tr><th>상품명</th><th>건수</th></tr></thead><tbody>"""
            w_tbody  = "".join(
                f"<tr><td>{r['상품명']}</td><td>{r['건수']}</td></tr>"
                for _, r in prod_cnt.iterrows()
            )
            w_tbody += f"<tr><td><strong>합계</strong></td><td><strong>{len(df_this)}</strong></td></tr>"
            st.markdown(w_thead + w_tbody + "</tbody></table>", unsafe_allow_html=True)
            st.markdown("")
            with st.expander("📋 이번 주 신규 고객 목록"):
                st.dataframe(
                    df_this[["상호명","상품명","가입일"]].reset_index(drop=True),
                    use_container_width=True,
                )
        else:
            st.info("이번 주 신규 데이터가 없습니다.")

        st.markdown('<hr class="divider-soft">', unsafe_allow_html=True)

        # ────────────────────────────────────────────────
        # 📈 월별 추이 차트
        # ────────────────────────────────────────────────
        st.markdown('<div class="section-title">📈 월별 신규 추이</div>', unsafe_allow_html=True)
        base = pd.DataFrame({"월": range(1,13)})
        base["월명"] = base["월"].map(MONTH_NAMES)
        base["목표"] = base["월"].apply(lambda m: get_target(sel_year, m))
        base = base.merge(
            df_year.groupby("월").size().reset_index(name="신규건수"),
            on="월", how="left"
        ).fillna(0)
        base["신규건수"] = base["신규건수"].astype(int)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=base["월명"], y=base["신규건수"],
            name="신규건수", marker_color="#0066FF",
            text=base["신규건수"], textposition="outside",
        ))
        if base["목표"].sum() > 0:
            fig.add_trace(go.Scatter(
                x=base["월명"], y=base["목표"],
                name="목표", mode="lines+markers",
                line=dict(color="#f97316", width=2, dash="dash"),
                marker=dict(size=7),
            ))
        fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            font_family="Noto Sans KR", height=320,
            legend=dict(orientation="h", y=1.08),
            margin=dict(t=30, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        # 최근 8주 트렌드
        st.markdown('<div class="section-title">📈 최근 8주 트렌드</div>', unsafe_allow_html=True)
        week_rows = []
        for i in range(7, -1, -1):
            w_thu = thu - timedelta(weeks=i)
            w_wed = wed - timedelta(weeks=i)
            cnt   = len(df_wm[(df_wm["가입일"] >= w_thu) & (df_wm["가입일"] <= w_wed)])
            week_rows.append({
                "주간": f"{w_thu.strftime('%m.%d')}~{w_wed.strftime('%m.%d')}",
                "건수": cnt,
            })
        df_wk = pd.DataFrame(week_rows)
        fig2  = px.line(df_wk, x="주간", y="건수", markers=True,
                        color_discrete_sequence=["#0066FF"], height=260)
        fig2.update_traces(line_width=2.5, marker_size=8)
        fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                           font_family="Noto Sans KR", margin=dict(t=10, b=10))
        st.plotly_chart(fig2, use_container_width=True)


# ══════════════════════════════════════════════════════════
# 탭 3 — 목표 관리
# ══════════════════════════════════════════════════════════
with TAB_TARGET:
    st.subheader("🎯 월별 목표 설정")
    st.caption("연도를 선택하고 월별 목표를 입력하세요. 2026년 이후 미래 연도도 미리 설정할 수 있습니다.")

    # 연도 선택: 데이터 연도와 무관하게 TARGET_YEARS 전체 표시
    target_year_options = TARGET_YEARS
    default_idx = target_year_options.index(CURRENT_YEAR) if CURRENT_YEAR in target_year_options else 0
    sel_target_year = st.selectbox(
        "연도 선택",
        target_year_options,
        index=default_idx,
        format_func=lambda y: f"{y}년" + (" (올해)" if y == CURRENT_YEAR else
                                           " (내년)" if y == CURRENT_YEAR + 1 else ""),
        key="yr_target",
    )

    st.markdown(f"**{sel_target_year}년** 월별 목표를 입력하세요.")

    with st.form("target_form"):
        rows_of_cols = [st.columns(4) for _ in range(3)]
        new_targets  = {}
        for i, month in enumerate(range(1, 13)):
            with rows_of_cols[i // 4][i % 4]:
                new_targets[month] = st.number_input(
                    MONTH_NAMES[month], min_value=0, max_value=9999,
                    value=get_target(sel_target_year, month), step=1,
                    key=f"tgt_{sel_target_year}_{month}",
                )
        if st.form_submit_button("💾 목표 저장", use_container_width=True):
            for m, v in new_targets.items():
                save_target(sel_target_year, m, int(v))
            st.success(f"✅ {sel_target_year}년 목표가 저장되었습니다!")
            st.rerun()

    st.divider()

    # 목표 vs 실적 요약 테이블
    st.markdown('<div class="section-title">📋 목표 vs 실적 요약</div>', unsafe_allow_html=True)

    # 실적 데이터 로드 (없어도 목표 테이블은 표시)
    try:
        df_all = load_wemembers()
        df_target_year = df_all[
            (df_all["상품명"].isin(WM_PRODUCTS)) & (df_all["연도"] == sel_target_year)
        ] if not df_all.empty else pd.DataFrame()
    except:
        df_target_year = pd.DataFrame()

    t_thead = """<table class="report-table"><thead><tr>
      <th>월</th><th>목표</th><th>실적</th><th>달성률</th>
    </tr></thead><tbody>"""
    t_tbody = ""
    for m in range(1, 13):
        t = get_target(sel_target_year, m)
        a = len(df_target_year[df_target_year["월"] == m]) if not df_target_year.empty else 0
        r = round(a/t*100, 1) if t > 0 else None
        t_tbody += f"""<tr>
          <td>{MONTH_NAMES[m]}</td>
          <td>{t if t > 0 else "-"}</td>
          <td>{a}</td>
          <td class="{rate_color(r)}"><strong>{f"{r}%" if r is not None else "-"}</strong></td>
        </tr>"""

    st.markdown(t_thead + t_tbody + "</tbody></table>", unsafe_allow_html=True)
    st.markdown("")
    st.info("💡 목표는 브라우저 세션 동안 유지됩니다. 새로고침 시 초기화됩니다.")
