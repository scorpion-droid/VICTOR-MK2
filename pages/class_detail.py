import json
import streamlit as st
import pandas as pd
import gspread
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities import Hasher
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Class Detail", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_resource(ttl=0)
def get_gspread_client():
    try:
        creds_dict = dict(st.secrets["gserviceaccount"])
        sheet_id = creds_dict.get("spreadsheet_id")
        if "spreadsheet_id" in creds_dict:
            del creds_dict["spreadsheet_id"]
        gc = gspread.service_account_from_dict(creds_dict)
        return gc, sheet_id
    except Exception:
        return None, None

gc, SPREADSHEET_ID = get_gspread_client()

USER_COLS = ["username", "password", "first_name", "last_name", "email", "role", "class_code", "classes", "password_hint"]
HISTORY_COLS = ["username", "date", "equation", "status", "message", "error_type"]

def load_users_df():
    try:
        if gc and SPREADSHEET_ID:
            sh = gc.open_by_key(SPREADSHEET_ID)
            worksheet = sh.worksheet("Users")
            records = worksheet.get_all_records()
            return pd.DataFrame(records) if records else pd.DataFrame(columns=USER_COLS)
        return conn.read(worksheet="Users", ttl=0)
    except Exception:
        return pd.DataFrame(columns=USER_COLS)

def load_history_df():
    try:
        if gc and SPREADSHEET_ID:
            sh = gc.open_by_key(SPREADSHEET_ID)
            worksheet = sh.worksheet("History")
            records = worksheet.get_all_records()
            return pd.DataFrame(records) if records else pd.DataFrame(columns=HISTORY_COLS)
        return conn.read(worksheet="History", ttl=0)
    except Exception:
        return pd.DataFrame(columns=HISTORY_COLS)

def normalize_auth_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    normalized = df.copy()
    for col in normalized.columns:
        if normalized[col].dtype == "object":
            normalized[col] = normalized[col].fillna("").astype(str).str.strip()
    if "username" in normalized.columns:
        normalized["username"] = normalized["username"].str.lower()
    if "class_code" in normalized.columns:
        normalized["class_code"] = normalized["class_code"].str.lower()
    return normalized

def build_credentials(source_df: pd.DataFrame) -> dict:
    credentials = {"usernames": {}}
    source_df = normalize_auth_df(source_df)
    for _, row in source_df.dropna(subset=["username"]).iterrows():
        username = str(row["username"]).strip().lower()
        password = str(row.get("password", "")).strip()
        if not username or not password:
            continue
        classes_dict = {}
        if pd.notna(row.get("classes")) and str(row["classes"]).strip():
            try:
                classes_dict = json.loads(str(row["classes"]))
            except Exception:
                classes_dict = {}
        credentials["usernames"][username] = {
            "password": password,
            "first_name": str(row["first_name"]).strip() if pd.notna(row["first_name"]) else "",
            "last_name": str(row["last_name"]).strip() if pd.notna(row["last_name"]) else "",
            "email": str(row["email"]).strip() if pd.notna(row["email"]) else "",
            "role": str(row["role"]).strip() if pd.notna(row["role"]) else "student",
            "class_code": str(row["class_code"]).strip().lower() if pd.notna(row["class_code"]) else "unassigned",
            "password_hint": str(row["password_hint"]).strip() if pd.notna(row.get("password_hint")) else "",
            "classes": classes_dict,
        }
    return credentials

def summarize_history(history_df: pd.DataFrame) -> dict:
    buckets = {
        "Sign Error": 0,
        "Distribution Error": 0,
        "Arithmetic Error": 0,
        "Variable Mismatch": 0,
        "Inequality Error": 0,
        "Exponent/Power Error": 0,
        "Radical Error": 0,
        "Geometry/Formula Error": 0,
         "Equation Setup Error": 0,
        "OCR/Formatting Error": 0,
        "Conceptual/Other": 0,
    }
    if history_df.empty or "error_type" not in history_df.columns:
        return buckets
    for value in history_df.loc[history_df["status"] == "Failed", "error_type"].fillna("Conceptual/Other"):
        buckets[value if value in buckets else "Conceptual/Other"] += 1
    return buckets

def render_analytics_panel(title: str, history_df: pd.DataFrame, empty_message: str) -> None:
    st.subheader(title)
    if history_df.empty:
        st.info(empty_message)
        return
    total_scans = len(history_df)
    passed_scans = int((history_df["status"] == "Passed").sum())
    failed_scans = int((history_df["status"] == "Failed").sum())
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Checks", total_scans)
    with c2:
        st.metric("Pass Rate", f"{int((passed_scans / total_scans) * 100)}%" if total_scans else "N/A")
    with c3:
        st.metric("Failed Checks", failed_scans)

    error_counts = summarize_history(history_df)
    if sum(error_counts.values()) == 0:
        st.success("No failed checks yet. Nice work.")
        return

    col_chart, col_insights = st.columns([3, 2])
    with col_chart:
        st.bar_chart(error_counts)
    with col_insights:
        top_error = max(error_counts, key=error_counts.get)
        total_errors = sum(error_counts.values())
        st.metric("Top Error Type", top_error, delta=f"{int((error_counts[top_error] / total_errors) * 100)}% of mistakes")

def render_history_card(date_text: str, steps_text: str, message_text: str, passed: bool) -> None:
    with st.container(border=True):
        left, right = st.columns([1, 4])
        with left:
            st.success("PASSED") if passed else st.error("ERROR")
        with right:
            st.markdown(f"**Date:** {date_text}")
            st.markdown("**Steps Detected:**")
            st.markdown(steps_text.replace("\n", "  \n"))
            st.markdown("**Feedback:**")
            st.markdown(message_text)

users_df = load_users_df()
credentials = build_credentials(users_df)

config_cookie = {
    "cookie": {
        "name": "victor_auth_cookie_v2",
        "key": "school_secure_key_123",
        "expiry_days": 30,
    }
}

authenticator = stauth.Authenticate(
    credentials,
    config_cookie["cookie"]["name"],
    config_cookie["cookie"]["key"],
    config_cookie["cookie"]["expiry_days"],
)

if not st.session_state.get("authentication_status"):
    st.warning("Please log in first.")
    if st.button("Back to Login"):
        st.switch_page("app.py")
    st.stop()

username = st.session_state.get("username", "")
user_profile = credentials["usernames"].get(username, {})

if user_profile.get("role") != "teacher":
    st.warning("This page is for teachers only.")
    if st.button("Back to Dashboard"):
        st.switch_page("app.py")
    st.stop()

teacher_classes = user_profile.get("classes", {})
selected_code = st.session_state.get("selected_class_code")
if not selected_code or selected_code not in teacher_classes:
    st.warning("Pick a classroom from the teacher dashboard first.")
    if st.button("Back to Dashboard"):
        st.switch_page("app.py")
    st.stop()

    history_df = load_history_df()
student_accounts = {
    u: data for u, data in credentials["usernames"].items()
    if data.get("role") == "student" and data.get("class_code") == selected_code
}
class_history_df = history_df[history_df["username"].isin(student_accounts.keys())] if not history_df.empty else pd.DataFrame(columns=HISTORY_COLS)

teacher_tabs = st.sidebar.radio("View", ["Overview", "Student Roster & Live Logs", "Concept Analysis"], index=0)

st.title(f"{teacher_classes[selected_code]} ({selected_code})")
st.caption("Detailed class view")

if st.button("Back to Dashboard"):
    st.switch_page("app.py")

if teacher_tabs == "Overview":
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Students", len(student_accounts))
    with c2:
        st.metric("Uploads", len(class_history_df))
    st.write("Students needing attention:")
    attention_names = []
    for s_user, s_data in student_accounts.items():
        s_history_df = class_history_df[class_history_df["username"] == s_user]
        if not s_history_df.empty and (s_history_df["status"] == "Failed").sum() >= (s_history_df["status"] == "Passed").sum():
            attention_names.append(s_data.get("first_name", s_user))
    st.write(", ".join(attention_names) if attention_names else "None so far.")
    st.write("Class Summary (AI):")
    if class_history_df.empty:
        st.info("No uploads yet for this class.")
    else:
        total_passed = int((class_history_df["status"] == "Passed").sum())
        total_failed = int((class_history_df["status"] == "Failed").sum())
        st.success(f"{total_passed} passed, {total_failed} failed. {len(attention_names)} student(s) may need extra support.")

elif teacher_tabs == "Student Roster & Live Logs":
    if not student_accounts:
        st.info("No students have entered this classroom code yet.")
    else:
        for s_user, s_data in student_accounts.items():
            s_history_df = class_history_df[class_history_df["username"] == s_user]
            with st.expander(f"{s_data['first_name']} (@{s_user}) — {len(s_history_df)} submissions"):
                if s_history_df.empty:
                    st.caption("This student hasn't checked any equations yet.")
                else:
                    for _, item in s_history_df.iloc[::-1].iterrows():
                        render_history_card(
                            date_text=str(item["date"]),
                            steps_text=str(item["equation"]),
                            message_text=str(item["message"]),
                            passed=item["status"] == "Passed",
                        )

else:
    render_analytics_panel(
        "Classroom Misconception Breakdown",
        class_history_df,
        "Zero student errors recorded in this section yet! Everything balances perfectly."
    )

st.sidebar.markdown("---")
if st.sidebar.button("Logout", use_container_width=True):
    st.session_state["authentication_status"] = False
    for key in ("username", "name", "email", "roles"):
        st.session_state.pop(key, None)
    st.switch_page("app.py")