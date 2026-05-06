import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import io
from datetime import datetime

st.set_page_config(
    page_title="위멤버스 실적 업로드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 스타일 ──────────────────────────────────────────────────
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
.subtitle { color: #64748b; font-size: 0.95rem; margin-bottom: 2rem; }

.sheet-card {
    background: #f8faff;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #0066FF;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
}
.sheet-card h4 { margin: 0 0 0.3rem; color: #1A3A8F; font-size: 1rem; }
.sheet-card p  { margin: 0; color: #64748b; font-size: 0.82rem; }

.sheet-card-selected {
    background: #eff6ff;
    border: 1px solid #93c5fd;
    border-left: 4px solid #0066FF;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
}

.success-box {
    background: #f0fdf4; border: 1px solid #86efac;
    border-radius: 8px; padding: 1rem; margin: 1rem 0;
    color: #166534;
}
.stButton > button {
    background: linear-gradient(135deg, #1A3A8F, #0066FF);
    color: white; border: none; border-radius: 8px;
    padding: 0.6rem 2rem; font-weight: 600;
    font-family: 'Noto Sans KR', sans-serif;
    width: 100%;
}
.stButton > button:hover { opacity: 0.88; }
</style>
""", unsafe_allow_html=True)


# ── 상수 ──────────────────────────────────────────────────
SPREADSHEET_ID = "1k2FcMog8G75apAxUAJsCuHE10hQHSmImFofX1ZTSYwk"

SHEET_CONFIG = {
    "위멤버스":  {"cols": ["D", "E", "I", "S"],  "col_idx": [3, 4, 8, 18], "icon": "📗"},
    "경리나라T": {"cols": ["D", "E", "I", "V"],  "col_idx": [3, 4, 8, 21], "icon": "📘"},
    "경리나라":  {"cols": ["D", "E", "I", "W"],  "col_idx": [3, 4, 8, 22], "icon": "📙"},
}


# ── Google Sheets 연결 ──────────────────────────────────────
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(dict(creds_dict), scopes=scopes)
    return gspread.authorize(creds)


def get_worksheet(client, sheet_name: str):
    sh = client.open_by_key(SPREADSHEET_ID)
    return sh.worksheet(sheet_name)


# ── 데이터 처리 ─────────────────────────────────────────────
def extract_columns(df: pd.DataFrame, col_indices: list) -> pd.DataFrame:
    valid = [i for i in col_indices if i < len(df.columns)]
    return df.iloc[:, valid]


def df_to_sheet_values(df: pd.DataFrame) -> list:
    import numpy as np
    rows = []
    for _, row in df.iterrows():
        processed = []
        for val in row:
            try:
                if pd.isna(val):
                    processed.append("")
                    continue
            except (TypeError, ValueError):
                pass
            if isinstance(val, (pd.Timestamp, datetime)):
                processed.append(str(val.date()))
            elif isinstance(val, (np.integer,)):
                processed.append(int(val))
            elif isinstance(val, (np.floating,)):
                processed.append(float(val))
            elif isinstance(val, float):
                processed.append(val)
            elif isinstance(val, int):
                processed.append(val)
            else:
                processed.append(str(val))
        rows.append(processed)
    return rows


def upload_to_sheet(client, sheet_name: str, df: pd.DataFrame, col_indices: list):
    ws = get_worksheet(client, sheet_name)
    extracted = extract_columns(df, col_indices)
    header_row = extracted.iloc[0].tolist() if len(extracted) > 0 else []
    data_rows  = df_to_sheet_values(extracted.iloc[1:])
    ws.clear()
    all_values = [header_row] + data_rows if header_row else data_rows
    if all_values:
        ws.update("A1", all_values, value_input_option="USER_ENTERED")
    return len(data_rows)


# ── UI ─────────────────────────────────────────────────────
st.markdown('<div class="main-title">📊 실적 데이터 업로드</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">엑셀 파일을 업로드하면 Google Sheets에 자동 반영됩니다</div>', unsafe_allow_html=True)

# ── 시트 선택 ──────────────────────────────────────────────
st.subheader("① 업로드할 시트 선택")
st.caption("여러 시트를 동시에 선택할 수 있습니다.")

col1, col2, col3 = st.columns(3)
sheet_checks = {}
for col_widget, (sheet_name, cfg) in zip([col1, col2, col3], SHEET_CONFIG.items()):
    with col_widget:
        checked = st.checkbox(
            f"{cfg['icon']} **{sheet_name}**",
            value=True,
            key=f"check_{sheet_name}",
        )
        sheet_checks[sheet_name] = checked
        st.markdown(
            f"<div class='sheet-card'><p>업로드 열: {', '.join(cfg['cols'])}</p></div>",
            unsafe_allow_html=True,
        )

selected_sheets = [name for name, checked in sheet_checks.items() if checked]

if not selected_sheets:
    st.warning("⚠️ 업로드할 시트를 1개 이상 선택해주세요.")

st.divider()

# ── 파일 업로드 ────────────────────────────────────────────
st.subheader("② 엑셀 파일 업로드")
uploaded_file = st.file_uploader(
    "엑셀 파일 선택 (.xlsx / .xls)",
    type=["xlsx", "xls"],
    help="다운로드 받은 실적 엑셀 파일을 드래그하거나 클릭하여 업로드하세요.",
)

if uploaded_file:
    try:
        df_raw = pd.read_excel(uploaded_file, header=0)
        st.success(f"✅ 파일 로드 완료 — **{uploaded_file.name}** ({len(df_raw):,}행 × {len(df_raw.columns)}열)")

        with st.expander("📋 원본 데이터 미리보기 (상위 5행)"):
            st.dataframe(df_raw.head(), use_container_width=True)

        # 선택된 시트만 미리보기
        if selected_sheets:
            st.subheader("선택된 시트 데이터 미리보기")
            tab_labels = [f"{SHEET_CONFIG[s]['icon']} {s}" for s in selected_sheets]
            tabs = st.tabs(tab_labels)
            for tab, sheet_name in zip(tabs, selected_sheets):
                with tab:
                    cfg = SHEET_CONFIG[sheet_name]
                    preview = extract_columns(df_raw, cfg["col_idx"])
                    st.caption(f"열 {', '.join(cfg['cols'])} — {max(0, len(preview)-1):,}건")
                    st.dataframe(preview.head(10), use_container_width=True)

        st.divider()

        # ── 업로드 버튼 ────────────────────────────────────
        btn_label = f"🚀 선택된 시트 업로드 ({', '.join(selected_sheets)})" if selected_sheets else "🚀 업로드"
        if selected_sheets and st.button(btn_label, use_container_width=True):
            try:
                client = get_gspread_client()
                results = {}
                total = len(selected_sheets)
                progress = st.progress(0, text="업로드 중...")

                for i, sheet_name in enumerate(selected_sheets):
                    progress.progress(i / total, text=f"📤 {sheet_name} 시트 업로드 중...")
                    cfg = SHEET_CONFIG[sheet_name]
                    count = upload_to_sheet(client, sheet_name, df_raw, cfg["col_idx"])
                    results[sheet_name] = count

                progress.progress(1.0, text="완료!")

                st.markdown('<div class="success-box">', unsafe_allow_html=True)
                st.markdown("### ✅ 업로드 완료!")
                for sheet_name, count in results.items():
                    st.markdown(f"- **{SHEET_CONFIG[sheet_name]['icon']} {sheet_name}**: {count:,}건")
                st.markdown(
                    f"[📊 Google Sheets에서 확인하기](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)",
                    unsafe_allow_html=True
                )
                st.markdown('</div>', unsafe_allow_html=True)

            except Exception as e:
                st.error(f"❌ 업로드 실패: {e}")
                st.info("💡 Google 서비스 계정 설정을 확인해주세요. 사이드바의 설정 가이드를 참고하세요.")

    except Exception as e:
        st.error(f"❌ 파일 읽기 실패: {e}")


# ── 사이드바 ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ 설정 가이드")
    st.markdown("""
    **처음 배포 시 필요한 설정:**

    1. Google Cloud Console에서 서비스 계정 생성
    2. Sheets + Drive API 활성화
    3. 서비스 계정에 스프레드시트 편집 권한 부여
    4. Streamlit Cloud → App settings → Secrets에 아래 형식으로 추가:

    ```toml
    [gcp_service_account]
    type = "service_account"
    project_id = "your-project"
    private_key_id = "..."
    private_key = "..."
    client_email = "...@....iam.gserviceaccount.com"
    client_id = "..."
    auth_uri = "..."
    token_uri = "..."
    ```
    """)

    st.divider()
    st.markdown("### 📌 업로드 열 매핑")
    st.markdown("""
    | 시트 | 열 |
    |------|-----|
    | 위멤버스 | D, E, I, S |
    | 경리나라T | D, E, I, V |
    | 경리나라 | D, E, I, W |
    """)

    st.divider()
    st.markdown("### 📈 보고서 페이지")
    st.markdown("← 좌측 사이드바 상단의 **report** 메뉴를 클릭하세요")
