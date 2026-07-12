import streamlit as st
import json
import base64
import os
import random
import string
import datetime
import functools
import uuid
from PIL import Image
import pillow_heif
import pandas as pd
import gspread
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities import Hasher
from streamlit_gsheets import GSheetsConnection
from google import genai
from App.sanitiser import clean_image
from App.checker import detect_first_error

st.set_page_config(page_title="V.I.C.T.O.R", layout="centered")

# Initialize connections
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_resource(ttl=0)
def get_gspread_client():
    try:
        creds_dict = dict(st.secrets["gserviceaccount"])
        sheet_id = creds_dict.get("spreadsheet_id")
        # Strip out the non-standard gspread config key before passing to authorization
        if "spreadsheet_id" in creds_dict:
            del creds_dict["spreadsheet_id"]
        gc = gspread.service_account_from_dict(creds_dict)
        return gc, sheet_id
    except Exception as e:
        st.error(f"Gspread client error: {e}")
        return None, None

gc, SPREADSHEET_ID = get_gspread_client()

# Safe database readers using the public connection manager
def load_users_df():
    fallback = st.session_state.get("_last_good_users_df", pd.DataFrame(columns=USER_COLS))
    try:
        if gc and SPREADSHEET_ID:
            sh = gc.open_by_key(SPREADSHEET_ID)
            worksheet = sh.worksheet("Users")
            records = worksheet.get_all_records()
            df = pd.DataFrame(records) if records else pd.DataFrame(columns=USER_COLS)
        else:
            df = conn.read(worksheet="Users", ttl=0)
    except Exception:
        return fallback

    if df is not None and not df.empty:
        st.session_state["_last_good_users_df"] = df
        return df
    return fallback

def load_history_df():
    fallback = st.session_state.get("_last_good_history_df", pd.DataFrame(columns=HISTORY_COLS))
    try:
        if gc and SPREADSHEET_ID:
            sh = gc.open_by_key(SPREADSHEET_ID)
            worksheet = sh.worksheet("History")
            records = worksheet.get_all_records()
            df = pd.DataFrame(records) if records else pd.DataFrame(columns=HISTORY_COLS)
        else:
            df = conn.read(worksheet="History", ttl=0)
    except Exception:
        return fallback

    if df is not None and not df.empty:
        st.session_state["_last_good_history_df"] = df
        return df
    return fallback

def load_categories_df():
    fallback = st.session_state.get("_last_good_categories_df", pd.DataFrame(columns=CATEGORY_COLS))
    try:
        if gc and SPREADSHEET_ID:
            sh = gc.open_by_key(SPREADSHEET_ID)
            worksheet = sh.worksheet("Categories")
            records = worksheet.get_all_records()
            df = pd.DataFrame(records) if records else pd.DataFrame(columns=CATEGORY_COLS)
        else:
            df = conn.read(worksheet="Categories", ttl=0)
    except Exception:
        return fallback

    if df is not None and not df.empty:
        st.session_state["_last_good_categories_df"] = df
        return df
    return fallback

def load_sheet_df(worksheet_name: str, columns: list[str], cache_key: str) -> pd.DataFrame:
    fallback = st.session_state.get(cache_key, pd.DataFrame(columns=columns))
    try:
        if gc and SPREADSHEET_ID:
            sh = gc.open_by_key(SPREADSHEET_ID)
            worksheet = sh.worksheet(worksheet_name)
            records = worksheet.get_all_records()
            df = pd.DataFrame(records) if records else pd.DataFrame(columns=columns)
        else:
            df = conn.read(worksheet=worksheet_name, ttl=0)
    except Exception:
        return fallback

    if df is not None and not df.empty:
        st.session_state[cache_key] = df
        return df
    return fallback

def upsert_dataframe_to_worksheet(worksheet_name: str, df: pd.DataFrame, target_columns: list[str], dedup_subset: list[str]) -> bool:
    if not gc or not SPREADSHEET_ID:
        st.error("Database initialization failed. Cannot save.")
        return False
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(worksheet_name)

        existing_records = worksheet.get_all_records()
        existing_df = pd.DataFrame(existing_records) if existing_records else pd.DataFrame(columns=target_columns)

        working_df = df.copy()
        for col in target_columns:
            if col not in working_df.columns:
                working_df[col] = ""
            if col not in existing_df.columns:
                existing_df[col] = ""

        merged_df = pd.concat([existing_df[target_columns].fillna(""), working_df[target_columns].fillna("")], ignore_index=True)
        merged_df = merged_df.drop_duplicates(subset=dedup_subset, keep="last").fillna("")
        data_matrix = [target_columns] + merged_df.values.tolist()

        worksheet.clear()
        worksheet.update(data_matrix)
        return True
    except Exception as e:
        st.error(f"Failed writing data to sheet tab '{worksheet_name}': {e}")
        return False

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

# Bulletproof direct cell-matrix overwriter for saving modifications
def save_dataframe_to_worksheet(worksheet_name, df, target_columns):
    if not gc or not SPREADSHEET_ID:
        st.error("Database initialization failed. Cannot save.")
        return False
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(worksheet_name)

        existing_records = worksheet.get_all_records()
        existing_df = pd.DataFrame(existing_records) if existing_records else pd.DataFrame(columns=target_columns)

        for col in target_columns:
            if col not in df.columns:
                df[col] = ""
            if col not in existing_df.columns:
                existing_df[col] = ""

        cleaned_df = df[target_columns].fillna("")
        existing_df = existing_df[target_columns].fillna("")

        merged_df = pd.concat([existing_df, cleaned_df], ignore_index=True)
        merged_df = merged_df.drop_duplicates(subset=target_columns, keep="last").fillna("")
        data_matrix = [target_columns] + merged_df.values.tolist()

        worksheet.clear()
        worksheet.update(data_matrix)
        return True
    except Exception as e:
        st.error(f"Failed writing data to sheet tab '{worksheet_name}': {e}")
        return False

def replace_dataframe_in_worksheet(worksheet_name, df, target_columns):
    if not gc or not SPREADSHEET_ID:
        st.error("Database initialization failed. Cannot save.")
        return False
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(worksheet_name)

        working_df = df.copy()
        for col in target_columns:
            if col not in working_df.columns:
                working_df[col] = ""

        data_matrix = [target_columns] + working_df[target_columns].fillna("").astype(str).values.tolist()
        worksheet.clear()
        worksheet.update(data_matrix)
        return True
    except Exception as e:
        st.error(f"Failed replacing data in sheet tab '{worksheet_name}': {e}")
        return False

USER_COLS = ["username", "password", "first_name", "last_name", "email", "role", "class_code", "classes", "password_hint"]
HISTORY_COLS = ["username", "class_code", "date", "equation", "status", "message", "error_category", "topic"]
CATEGORY_COLS = ["class_code", "category_name", "description", "example_message", "first_seen", "last_seen", "times_seen"]
CLASS_ASSIGNMENT_COLS = [
    "assignment_id",
    "class_code",
    "topic",
    "title",
    "instructions",
    "due_date",
    "attachment_type",
    "attachment_link",
    "attachment_b64",
    "created_at",
    "created_by",
]
TARGETED_PRACTICE_COLS = [
    "assignment_id",
    "class_code",
    "username",
    "topic",
    "title",
    "instructions",
    "due_date",
    "attachment_type",
    "attachment_link",
    "attachment_b64",
    "created_at",
    "created_by",
]
TEACHER_COMMENT_COLS = [
    "comment_id",
    "class_code",
    "scope",
    "username",
    "topic",
    "message",
    "created_at",
    "created_by",
]
ASSIGNMENT_STATUS_COLS = [
    "assignment_id",
    "assignment_type",
    "class_code",
    "username",
    "status",
    "completed_at",
]

DEFAULT_TOPICS = [
    "Linear Equations",
    "Factorization",
    "Systems of Equations",
    "Area & Volume",
    "Inequalities",
]

def load_topics(class_code: str) -> list[str]:
    class_code = (class_code or "").strip().lower()
    cache = st.session_state.setdefault("_last_good_topics_by_class", {})
    try:
        if gc and SPREADSHEET_ID:
            sh = gc.open_by_key(SPREADSHEET_ID)
            worksheet = sh.worksheet("Topics")
            records = worksheet.get_all_records()
        else:
            topics_df = conn.read(worksheet="Topics", ttl=0)
            records = topics_df.to_dict("records")
        topics = [
            str(r.get("topic", "")).strip()
            for r in records
            if str(r.get("class_code", "")).strip().lower() == class_code and str(r.get("topic", "")).strip()
        ]
        if topics:
            cache[class_code] = topics
            return topics
        return DEFAULT_TOPICS
    except Exception:
        return cache.get(class_code, DEFAULT_TOPICS)

def add_topic(class_code: str, new_topic: str) -> bool:
    class_code = (class_code or "").strip().lower()
    existing_topics = load_topics(class_code)
    if new_topic.strip().lower() in [t.lower() for t in existing_topics]:
        st.warning(f"'{new_topic}' already exists as a topic for this class.")
        return False
    new_slug = _topic_slug(new_topic)
    if new_slug in [_topic_slug(t) for t in existing_topics]:
        st.warning(f"'{new_topic}' is too similar to an existing topic name. Try a more distinct name.")
        return False
    return save_dataframe_to_worksheet(
        "Topics",
        pd.DataFrame({"class_code": [class_code], "topic": [new_topic.strip()]}),
        ["class_code", "topic"],
    )

def normalize_category_name(category_name: str) -> str:
    normalized = " ".join(str(category_name or "").replace("_", " ").split()).strip()
    return normalized[:60] if normalized else "General Misconception"

def summarize_history(history_df: pd.DataFrame) -> dict:
    if history_df.empty:
        return {}

    working_df = history_df.copy()
    if "error_category" not in working_df.columns:
        working_df["error_category"] = "General Misconception"

    working_df["error_category"] = working_df["error_category"].fillna("").astype(str).str.strip()
    working_df.loc[working_df["error_category"] == "", "error_category"] = "General Misconception"

    failed_df = working_df[working_df["status"] == "Failed"]
    if failed_df.empty:
        return {}

    return failed_df["error_category"].value_counts().to_dict()

def get_categories_for_class(class_code: str) -> list[str]:
    class_code = (class_code or "").strip().lower()
    categories_df = load_categories_df()
    if categories_df.empty or "class_code" not in categories_df.columns or "category_name" not in categories_df.columns:
        return []

    working_df = categories_df.copy()
    working_df["class_code"] = working_df["class_code"].fillna("").astype(str).str.lower()
    working_df["category_name"] = working_df["category_name"].fillna("").astype(str).str.strip()

    return [
        category
        for category in working_df.loc[working_df["class_code"] == class_code, "category_name"].tolist()
        if category
    ]

def record_category_usage(
    class_code: str,
    category_name: str,
    description: str = "",
    example_message: str = "",
) -> bool:
    class_code = (class_code or "").strip().lower() or "unassigned"
    category_name = normalize_category_name(category_name)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")

    categories_df = load_categories_df()
    if categories_df.empty:
        categories_df = pd.DataFrame(columns=CATEGORY_COLS)

    working_df = categories_df.copy()
    for col in CATEGORY_COLS:
        if col not in working_df.columns:
            working_df[col] = ""

    working_df["class_code"] = working_df["class_code"].fillna("").astype(str).str.lower()
    working_df["category_name"] = working_df["category_name"].fillna("").astype(str).str.strip()

    match_mask = (
        (working_df["class_code"] == class_code)
        & (working_df["category_name"].str.lower() == category_name.lower())
    )

    if match_mask.any():
        idx = working_df.index[match_mask][0]
        current_seen = pd.to_numeric(working_df.at[idx, "times_seen"], errors="coerce")
        working_df.at[idx, "times_seen"] = int(current_seen) + 1 if pd.notna(current_seen) else 1
        working_df.at[idx, "last_seen"] = timestamp
        if description and not str(working_df.at[idx, "description"]).strip():
            working_df.at[idx, "description"] = description.strip()
        if example_message and not str(working_df.at[idx, "example_message"]).strip():
            working_df.at[idx, "example_message"] = example_message.strip()
    else:
        new_row = {
            "class_code": class_code,
            "category_name": category_name,
            "description": description.strip() if description else "",
            "example_message": example_message.strip() if example_message else "",
            "first_seen": timestamp,
            "last_seen": timestamp,
            "times_seen": 1,
        }
        working_df = pd.concat([working_df, pd.DataFrame([new_row])], ignore_index=True)

    working_df["times_seen"] = pd.to_numeric(working_df["times_seen"], errors="coerce").fillna(0).astype(int)
    working_df["class_code"] = working_df["class_code"].fillna("").astype(str).str.lower()
    working_df["category_name"] = working_df["category_name"].fillna("").astype(str).str.strip()

    return replace_dataframe_in_worksheet("Categories", working_df, CATEGORY_COLS)

def filter_history_for_class(history_df: pd.DataFrame, class_code: str, student_usernames: list[str]) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame(columns=HISTORY_COLS)

    class_code = (class_code or "").strip().lower()
    working_df = history_df.copy()

    class_mask = pd.Series(False, index=working_df.index)
    if "class_code" in working_df.columns:
        class_mask = working_df["class_code"].fillna("").astype(str).str.lower() == class_code

    username_mask = pd.Series(False, index=working_df.index)
    if "username" in working_df.columns:
        username_mask = working_df["username"].isin(student_usernames)

    combined = working_df[class_mask | username_mask]
    if combined.empty:
        return pd.DataFrame(columns=HISTORY_COLS)
    return combined.drop_duplicates()

def make_record_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def encode_uploaded_file(file_obj) -> tuple[str, str]:
    if file_obj is None:
        return "", ""
    file_name = getattr(file_obj, "name", "").lower()
    if file_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".heif")):
        try:
            raw_bytes = file_obj.getvalue()
        except Exception:
            return "", ""
        return "image", base64.b64encode(raw_bytes).decode("utf-8")
    return "", ""

def decode_image_b64(image_b64: str):
    if not image_b64:
        return None
    try:
        return base64.b64decode(image_b64.encode("utf-8"))
    except Exception:
        return None

def load_class_assignments_df() -> pd.DataFrame:
    return load_sheet_df("ClassAssignments", CLASS_ASSIGNMENT_COLS, "_last_good_class_assignments_df")

def load_targeted_practice_df() -> pd.DataFrame:
    return load_sheet_df("TargetedPractice", TARGETED_PRACTICE_COLS, "_last_good_targeted_practice_df")

def load_teacher_comments_df() -> pd.DataFrame:
    return load_sheet_df("TeacherComments", TEACHER_COMMENT_COLS, "_last_good_teacher_comments_df")

def load_assignment_status_df() -> pd.DataFrame:
    return load_sheet_df("AssignmentStatus", ASSIGNMENT_STATUS_COLS, "_last_good_assignment_status_df")

def _normalize_working_sheet(df: pd.DataFrame) -> pd.DataFrame:
    working_df = df.copy()
    if "class_code" in working_df.columns:
        working_df["class_code"] = working_df["class_code"].fillna("").astype(str).str.lower()
    if "username" in working_df.columns:
        working_df["username"] = working_df["username"].fillna("").astype(str).str.lower()
    return working_df

def get_assignment_completion_map() -> dict[tuple[str, str], dict]:
    status_df = load_assignment_status_df()
    if status_df.empty:
        return {}

    working_df = _normalize_working_sheet(status_df)
    completion_map: dict[tuple[str, str], dict] = {}
    for _, row in working_df.iterrows():
        assignment_id = str(row.get("assignment_id", "")).strip()
        username = str(row.get("username", "")).strip().lower()
        if not assignment_id or not username:
            continue
        completion_map[(assignment_id, username)] = row.to_dict()
    return completion_map

def get_teacher_assignments_for_class(class_code: str) -> pd.DataFrame:
    assignments_df = load_class_assignments_df()
    if assignments_df.empty:
        return pd.DataFrame(columns=CLASS_ASSIGNMENT_COLS)
    working_df = _normalize_working_sheet(assignments_df)
    return working_df[working_df["class_code"] == (class_code or "").strip().lower()]

def get_targeted_practice_for_student(class_code: str, username: str) -> pd.DataFrame:
    practice_df = load_targeted_practice_df()
    if practice_df.empty:
        return pd.DataFrame(columns=TARGETED_PRACTICE_COLS)
    working_df = _normalize_working_sheet(practice_df)
    class_code = (class_code or "").strip().lower()
    username = (username or "").strip().lower()
    return working_df[(working_df["class_code"] == class_code) & (working_df["username"] == username)]

def get_targeted_practice_for_class(class_code: str) -> pd.DataFrame:
    practice_df = load_targeted_practice_df()
    if practice_df.empty:
        return pd.DataFrame(columns=TARGETED_PRACTICE_COLS)
    working_df = _normalize_working_sheet(practice_df)
    return working_df[working_df["class_code"] == (class_code or "").strip().lower()]

def get_teacher_comments_for_student(class_code: str, username: str) -> pd.DataFrame:
    comments_df = load_teacher_comments_df()
    if comments_df.empty:
        return pd.DataFrame(columns=TEACHER_COMMENT_COLS)

    working_df = _normalize_working_sheet(comments_df)
    class_code = (class_code or "").strip().lower()
    username = (username or "").strip().lower()
    class_comments = working_df[
        (working_df["class_code"] == class_code)
        & (working_df["scope"] == "class")
    ]
    student_comments = working_df[
        (working_df["class_code"] == class_code)
        & (working_df["scope"] == "student")
        & (working_df["username"] == username)
    ]
    return pd.concat([class_comments, student_comments], ignore_index=True)

def get_teacher_comments_for_class(class_code: str) -> pd.DataFrame:
    comments_df = load_teacher_comments_df()
    if comments_df.empty:
        return pd.DataFrame(columns=TEACHER_COMMENT_COLS)
    working_df = _normalize_working_sheet(comments_df)
    class_code = (class_code or "").strip().lower()
    return working_df[working_df["class_code"] == class_code]

def save_class_assignment(row: dict) -> bool:
    df = pd.DataFrame([row])
    return upsert_dataframe_to_worksheet("ClassAssignments", df, CLASS_ASSIGNMENT_COLS, ["assignment_id"])

def save_targeted_practice(row: dict) -> bool:
    df = pd.DataFrame([row])
    return upsert_dataframe_to_worksheet("TargetedPractice", df, TARGETED_PRACTICE_COLS, ["assignment_id"])

def save_teacher_comment(row: dict) -> bool:
    df = pd.DataFrame([row])
    return upsert_dataframe_to_worksheet("TeacherComments", df, TEACHER_COMMENT_COLS, ["comment_id"])

def save_assignment_completion(row: dict) -> bool:
    df = pd.DataFrame([row])
    return upsert_dataframe_to_worksheet("AssignmentStatus", df, ASSIGNMENT_STATUS_COLS, ["assignment_id", "username"])

def summarize_topic_counts(history_df: pd.DataFrame) -> pd.DataFrame:
    if history_df.empty or "topic" not in history_df.columns:
        return pd.DataFrame(columns=["Passed", "Failed"])

    working_df = history_df.copy()
    working_df["topic"] = working_df["topic"].fillna("Unspecified").replace("", "Unspecified")

    counts = working_df.groupby(["topic", "status"]).size().unstack(fill_value=0)
    for col in ("Passed", "Failed"):
        if col not in counts.columns:
            counts[col] = 0
    return counts[["Passed", "Failed"]]

def filter_history_by_status(history_df: pd.DataFrame, status_filter: str) -> pd.DataFrame:
    if history_df.empty:
        return history_df.copy()
    status_filter = (status_filter or "All").strip().lower()
    if status_filter == "passed":
        return history_df[history_df["status"] == "Passed"]
    if status_filter == "failed":
        return history_df[history_df["status"] == "Failed"]
    return history_df.copy()

def _safe_datetime_sort_key(value) -> int:
    try:
        parsed = pd.to_datetime(str(value).strip(), errors="coerce", utc=True)
        if pd.isna(parsed):
            return -1
        return int(parsed.value)
    except Exception:
        return -1

def build_cumulative_trend_df(history_df: pd.DataFrame, status_filter: str = "All") -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame(columns=["attempt_index", "cumulative_pass_rate", "passed"])

    working_df = history_df.copy()
    working_df = filter_history_by_status(working_df, status_filter)
    if working_df.empty:
        return pd.DataFrame(columns=["attempt_index", "cumulative_pass_rate", "passed"])

    if "date" in working_df.columns:
        working_df["_trend_sort_key"] = working_df["date"].apply(_safe_datetime_sort_key)
        if (working_df["_trend_sort_key"] >= 0).any():
            working_df = working_df.sort_values(["_trend_sort_key"], kind="stable")
        else:
            working_df = working_df.reset_index(drop=True)
    else:
        working_df = working_df.reset_index(drop=True)

    working_df["passed"] = (working_df["status"] == "Passed").astype(int)
    working_df["attempt_index"] = range(1, len(working_df) + 1)
    working_df["cumulative_pass_rate"] = working_df["passed"].expanding().mean() * 100
    base_cols = ["attempt_index", "cumulative_pass_rate", "passed", "status", "date"]
    if "topic" in working_df.columns:
        base_cols.append("topic")
    if "username" in working_df.columns:
        base_cols.append("username")
    return working_df[base_cols]

def build_topic_trend_df(history_df: pd.DataFrame, topic_filter: str, status_filter: str = "All") -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame(columns=["attempt_index", "cumulative_pass_rate", "passed"])

    working_df = history_df.copy()
    if "topic" in working_df.columns and topic_filter != "All Topics":
        working_df = working_df[working_df["topic"].fillna("").astype(str).str.strip().str.lower() == topic_filter.strip().lower()]

    return build_cumulative_trend_df(working_df, status_filter)

def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None

def get_growth_prediction(history_df: pd.DataFrame, topic_filter: str, status_filter: str = "All") -> str:
    trend_df = build_topic_trend_df(history_df, topic_filter, status_filter)
    if trend_df.empty or len(trend_df) < 2:
        return "Not enough data yet to make a prediction."

    recent = trend_df.tail(min(6, len(trend_df)))
    start_rate = float(recent["cumulative_pass_rate"].iloc[0])
    end_rate = float(recent["cumulative_pass_rate"].iloc[-1])
    gain = end_rate - start_rate
    attempts = len(recent)
    latest_status = recent["status"].iloc[-1]

    # Cache keyed on the actual computed stats, not on call site or widget
    # state, so this only calls Gemini again when the underlying data has
    # genuinely changed rather than on every unrelated rerun/click.
    cache_key = f"prediction_cache:{topic_filter}:{status_filter}:{attempts}:{start_rate:.1f}:{end_rate:.1f}:{latest_status}"
    cached = st.session_state.get(cache_key)
    if cached:
        return cached

    prompt = f"""
    You are helping a teacher interpret a student's math progress.

    Topic: {topic_filter}
    Attempts analyzed: {attempts}
    Cumulative pass rate started at {start_rate:.1f}% and ended at {end_rate:.1f}% over the recent attempts.
    Net change: {gain:+.1f} percentage points.
    Latest observed status: {latest_status}

    Give a short, credible prediction of the student's likely next performance or mastery trend.
    Mention whether the student seems to be improving, plateauing, or struggling.
    Keep it to 2 sentences max and do not invent exact certainty.
    """
    client = get_gemini_client()
    if client is None:
        if gain > 8:
            result = f"This student is improving quickly in {topic_filter}. If this pattern continues, mastery looks likely soon."
        elif gain < -8:
            result = f"This student may be struggling more in {topic_filter} recently, so the next check could still be shaky."
        else:
            result = f"This student looks fairly steady in {topic_filter}; the next result will likely depend on whether the current pattern continues."
        st.session_state[cache_key] = result
        return result

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
        )
        result = response.text.strip()
    except Exception:
        result = f"This student looks steady in {topic_filter}, but there isn't enough stable trend data for a strong prediction yet."

    st.session_state[cache_key] = result
    return result

def render_trend_and_prediction(title: str, history_df: pd.DataFrame, topic_filter: str = "All Topics", status_filter: str = "All") -> None:
    st.subheader(title)
    try:
        trend_df = build_topic_trend_df(history_df, topic_filter, status_filter)
    except Exception:
        st.info("Not enough clean submission dates yet to draw a trend.")
        return
    if trend_df.empty:
        st.info("Not enough submissions yet to draw a trend.")
        return

    chart_df = trend_df.set_index("attempt_index")[["cumulative_pass_rate"]]
    st.line_chart(chart_df)
    st.caption("Cumulative pass rate across the selected slice of submissions.")
    st.info(get_growth_prediction(history_df, topic_filter, status_filter))

def render_analytics_panel(title: str, history_df: pd.DataFrame, empty_message: str) -> None:
    st.subheader(title)
    if history_df.empty:
        st.info(empty_message)
        return

    total_scans = len(history_df)
    passed_scans = int((history_df["status"] == "Passed").sum())
    failed_scans = int((history_df["status"] == "Failed").sum())
    pass_rate = f"{int((passed_scans / total_scans) * 100)}%" if total_scans else "N/A"

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Checks", total_scans)
    with c2:
        st.metric("Pass Rate", pass_rate)
    with c3:
        st.metric("Failed Checks", failed_scans)

    error_counts = summarize_history(history_df)
    failed_total = sum(error_counts.values())
    if failed_total == 0:
        st.success("No failed checks yet. Nice work.")
        return

    col_chart, col_insights = st.columns([3, 2])
    with col_chart:
        st.bar_chart(error_counts)
    with col_insights:
        most_common_error = max(error_counts, key=error_counts.get)
        percentage = int((error_counts[most_common_error] / failed_total) * 100) if failed_total > 0 else 0
        st.metric(label="Top Error Type", value=most_common_error, delta=f"{percentage}% of mistakes")

def render_history_card(date_text: str, steps_text: str, message_text: str, passed: bool, header_text: str | None = None) -> None:
    with st.container(border=True):
        left, right = st.columns([1, 4])
        with left:
            if passed:
                st.success("PASSED")
            else:
                st.error("ERROR")
        with right:
            if header_text:
                st.caption(header_text)
            st.markdown(f"**Date:** {date_text}")
            st.markdown("**Steps Detected:**")
            st.markdown(steps_text.replace("\n", "  \n"))
            st.markdown("**Feedback:**")
            st.markdown(message_text)

def get_teacher_class_summary(class_code: str, teacher_classes: dict, credentials: dict, history_df: pd.DataFrame) -> dict:
    class_name = teacher_classes.get(class_code, class_code)
    student_accounts = {
        u: data for u, data in credentials["usernames"].items()
        if data.get("role") == "student" and data.get("class_code") == class_code
    }
    class_history_df = filter_history_for_class(history_df, class_code, list(student_accounts.keys()))
    attention_names = []
    if not class_history_df.empty:
        activity_counts = class_history_df["username"].value_counts()
        for u in activity_counts.index[:3]:
            attention_names.append(student_accounts.get(u, {}).get("first_name", u))
    if class_history_df.empty:
        total_uploads = 0
        ai_summary = "No uploads yet for this class."
    else:
        total_uploads = len(class_history_df)
        ai_summary = f"{total_uploads} total submissions logged. {len(attention_names)} student(s) may need extra support."
    return {
        "class_name": class_name,
        "class_code": class_code,
        "student_accounts": student_accounts,
        "class_history_df": class_history_df,
        "total_students": len(student_accounts),
        "total_uploads": len(class_history_df),
        "attention_names": attention_names,
        "ai_summary": ai_summary,
    }

def get_class_assignment_summary(class_code: str, student_accounts: dict) -> dict:
    class_code = (class_code or "").strip().lower()
    class_assignments = get_teacher_assignments_for_class(class_code)
    targeted_practice = get_targeted_practice_for_class(class_code)
    completion_map = get_assignment_completion_map()

    pending_students = set()
    pending_class_assignments = 0

    student_usernames = [u.strip().lower() for u in student_accounts.keys()]

    if not class_assignments.empty:
        for _, assignment in class_assignments.iterrows():
            assignment_id = str(assignment.get("assignment_id", "")).strip()
            for student_username in student_usernames:
                if not completion_map.get((assignment_id, student_username)) or str(completion_map[(assignment_id, student_username)].get("status", "")).strip().lower() != "done":
                    pending_students.add(student_username)
                    pending_class_assignments += 1

    targeted_pending = 0
    if not targeted_practice.empty:
        for _, assignment in targeted_practice.iterrows():
            assignment_id = str(assignment.get("assignment_id", "")).strip()
            student_username = str(assignment.get("username", "")).strip().lower()
            if student_username and (not completion_map.get((assignment_id, student_username)) or str(completion_map[(assignment_id, student_username)].get("status", "")).strip().lower() != "done"):
                pending_students.add(student_username)
                targeted_pending += 1

    return {
        "class_assignment_count": len(class_assignments),
        "targeted_practice_count": len(targeted_practice),
        "pending_students": sorted(pending_students),
        "pending_student_count": len(pending_students),
        "pending_class_assignment_count": pending_class_assignments,
        "pending_targeted_practice_count": targeted_pending,
        "comment_count": len(get_teacher_comments_for_class(class_code)),
    }

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
            "classes": classes_dict
        }

    return credentials

users_df = load_users_df()
credentials = build_credentials(users_df)

config_cookie = {
    'cookie': {
        'name': 'victor_auth_cookie_v2',
        'key': 'school_secure_key_123',
        'expiry_days': 30
    }
}

authenticator = stauth.Authenticate(
    credentials,
    config_cookie['cookie']['name'],
    config_cookie['cookie']['key'],
    config_cookie['cookie']['expiry_days']
)

st.session_state.setdefault("authentication_status", None)

cookie_token = authenticator.cookie_controller.get_cookie()
if cookie_token and not st.session_state.get("authentication_status"):
    cookie_username = str(cookie_token.get("username", "")).strip().lower()
    if cookie_username in credentials["usernames"]:
        cookie_profile = credentials["usernames"][cookie_username]
        st.session_state["authentication_status"] = True
        st.session_state["username"] = cookie_username
        st.session_state["name"] = f"{cookie_profile.get('first_name', '')} {cookie_profile.get('last_name', '')}".strip()
        st.session_state["email"] = cookie_profile.get("email")
        st.session_state["roles"] = cookie_profile.get("role")

def generate_class_code():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

def render_login() -> None:
    global authenticator, credentials
    credentials = build_credentials(load_users_df())
    authenticator.authentication_controller.authentication_model.credentials = credentials

    with st.form("victor_login_form", clear_on_submit=False):
        st.subheader("Login")
        login_username = st.text_input("Username", autocomplete="off")
        login_password = st.text_input("Password", type="password", autocomplete="off")
        submitted = st.form_submit_button("Login")

    if submitted:
        normalized_username = login_username.strip().lower()
        if not normalized_username or not login_password:
            st.error("Please enter both a username and password.")
            return

        try:
            user_record = credentials["usernames"].get(normalized_username)
            if not user_record:
                st.session_state["authentication_status"] = False
                st.error("Username/password is incorrect")
                return

            if Hasher.check_pw(login_password, user_record["password"]):
                st.session_state["authentication_status"] = True
                st.session_state["username"] = normalized_username
                st.session_state["name"] = f"{user_record.get('first_name', '')} {user_record.get('last_name', '')}".strip()
                st.session_state["email"] = user_record.get("email")
                st.session_state["roles"] = user_record.get("role")
                authenticator.cookie_controller.set_cookie()
                st.rerun()
            else:
                st.session_state["authentication_status"] = False
                st.error("Username/password is incorrect")
        except Exception as exc:
            message = str(exc)
            if "User not authorized" in message:
                authenticator.cookie_controller.delete_cookie()
                for key in ("authentication_status", "name", "username", "logout"):
                    st.session_state.pop(key, None)
                st.warning("Your saved login session was stale. Resetting environment...")
                st.rerun()
            else:
                raise

def get_current_user_profile() -> dict:
    current_username = st.session_state.get("username", "")
    profile = credentials["usernames"].get(current_username, {})
    if profile:
        st.session_state["last_known_profile"] = profile
        return profile
    # Live read for this rerun didn't include this user (transient sheet
    # issue) — reuse the last profile we actually confirmed rather than
    # silently showing an empty one.
    return st.session_state.get("last_known_profile", {})

def _topic_slug(topic: str) -> str:
    return topic.lower().replace(" ", "_").replace("&", "and")

def render_student_checker_page(topic: str) -> None:
    slug = _topic_slug(topic)
    last_file_key = f"last_uploaded_file_{slug}"
    ocr_text_key = f"ocr_text_{slug}"
    ocr_ready_key = f"ocr_ready_{slug}"

    st.session_state.setdefault(ocr_text_key, "")
    st.session_state.setdefault(ocr_ready_key, False)

    st.title("V.I.C.T.O.R")
    st.subheader(f"{topic} — Upload your steps for verification (Class Code: `{user_profile.get('class_code', 'Unassigned')}`)")
    uploaded_file = st.file_uploader("Choose an image...", type=["jpg", "png", "jpeg", "heic", "heif"], key=f"uploader_{slug}")

    if uploaded_file is not None:
        current_file_name = uploaded_file.name
        if st.session_state.get(last_file_key) != current_file_name:
            st.session_state[last_file_key] = current_file_name
            st.session_state[ocr_text_key] = ""
            st.session_state[ocr_ready_key] = False

        if st.button("Run OCR", key=f"run_ocr_{slug}"):
            with st.spinner('Analyzing handwriting and verifying steps...'):
                try:
                    file_extension = uploaded_file.name.split(".")[-1].lower()
                    if file_extension in ["heic", "heif"]:
                        heif_file = pillow_heif.read_heif(uploaded_file.getvalue())
                        image = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data, "raw", heif_file.mode, heif_file.stride)
                        image.save("temp_image.png", format="PNG")
                    else:
                        with open("temp_image.png", "wb") as f:
                            f.write(uploaded_file.getvalue())

                    extracted_text = clean_image("temp_image.png").strip()
                    st.session_state[ocr_text_key] = extracted_text
                    if extracted_text:
                        st.session_state[ocr_ready_key] = True
                    else:
                        st.session_state[ocr_ready_key] = False
                        st.warning("No text could be read from that image. Try a clearer photo.")
                except Exception:
                    st.error("The AI service is experiencing heavy traffic. Please try again.")

        if st.session_state[ocr_ready_key]:
            st.info("Review the OCR text below and fix any symbol mistakes before checking.")
            st.text_area("Extracted Steps:", key=ocr_text_key, height=240)

            if st.button("Confirm OCR and Check", key=f"confirm_{slug}"):
                steps = [s.strip() for s in st.session_state[ocr_text_key].splitlines() if s.strip()]
                if not steps:
                    st.warning("Please review or correct the OCR text first.")
                else:
                    known_categories = get_categories_for_class(user_profile.get("class_code", ""))
                    result = detect_first_error(
                        steps,
                        class_code=user_profile.get("class_code", ""),
                        known_categories=known_categories,
                    )
                    status_str = "Passed" if result.passed else "Failed"
                    error_category_str = "N/A"

                    if result.passed:
                        st.success(f"Passed: {result.message}")
                    else:
                        st.error(f"Error found: {result.message}")
                        error_category_str = normalize_category_name(result.error_category or "General Misconception")
                        record_category_usage(
                            user_profile.get("class_code", ""),
                            error_category_str,
                            description=result.message,
                            example_message=result.message,
                        )

                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")
                    history_df = load_history_df()
                    numbered_steps = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))

                    new_log = pd.DataFrame([{
                        'username': username, 'class_code': user_profile.get("class_code", ""), 'date': timestamp, 'equation': numbered_steps,
                        'status': status_str, 'message': result.message, 'error_category': error_category_str,
                        'topic': topic,
                    }])

                    updated_history = pd.concat([history_df, new_log], ignore_index=True)
                    save_dataframe_to_worksheet("History", updated_history, HISTORY_COLS)

def render_student_history_page() -> None:
    st.title("Your Performance History")
    history_df = load_history_df()
    user_history_df = history_df[history_df["username"] == username]
    student_display_name = st.session_state.get("name", username)

    topic_filter = st.selectbox("Filter by topic", ["All Topics"] + load_topics(user_profile.get("class_code", "")), key="history_topic_filter")
    if topic_filter != "All Topics" and "topic" in user_history_df.columns:
        filtered_df = user_history_df[user_history_df["topic"].str.strip().str.lower() == topic_filter.strip().lower()]
    else:
        filtered_df = user_history_df

    render_analytics_panel(
        "Your Individual Analytics",
        filtered_df,
        "You haven't scanned any math problems yet!"
    )

    st.markdown("---")
    if filtered_df.empty:
        st.info("You haven't scanned any math problems yet!")
    else:
        st.subheader("Recent Attempts")
        for _, item in filtered_df.iloc[::-1].iterrows():
            render_history_card(
                date_text=str(item["date"]),
                steps_text=str(item["equation"]),
                message_text=str(item["message"]),
                passed=item["status"] == "Passed",
                header_text=f"Topic: {item.get('topic', 'Unspecified') or 'Unspecified'}",
            )

    st.markdown("---")
    render_trend_and_prediction(f"{student_display_name} Growth Trend", filtered_df, "All Topics", "All")

def render_assignment_card(assignment: pd.Series, assignment_type: str, completion_map: dict[tuple[str, str], dict]) -> None:
    assignment_id = str(assignment.get("assignment_id", "")).strip()
    title = str(assignment.get("title", "")).strip() or "Untitled"
    topic = str(assignment.get("topic", "")).strip() or "Unspecified"
    due_date = str(assignment.get("due_date", "")).strip() or "No due date"
    instructions = str(assignment.get("instructions", "")).strip() or "No instructions provided."
    attachment_type = str(assignment.get("attachment_type", "")).strip().lower()
    attachment_link = str(assignment.get("attachment_link", "")).strip()
    attachment_b64 = str(assignment.get("attachment_b64", "")).strip()
    username_key = (st.session_state.get("username", "") or "").strip().lower()
    completion = completion_map.get((assignment_id, username_key))
    is_done = bool(completion and str(completion.get("status", "")).strip().lower() == "done")

    with st.container(border=True):
        st.markdown(f"### {title}")
        st.caption(f"Topic: {topic} | Due: {due_date} | Type: {assignment_type}")
        st.markdown(instructions)

        if attachment_type == "image" and attachment_b64:
            image_bytes = decode_image_b64(attachment_b64)
            if image_bytes:
                st.image(image_bytes, use_container_width=True)
        elif attachment_link:
            st.markdown(f"[Open attachment]({attachment_link})")

        if assignment_type == "targeted_practice" and topic and "student_topic_pages_by_slug" in globals():
            topic_slug = _topic_slug(topic)
            topic_page = student_topic_pages_by_slug.get(topic_slug)
            if topic_page is not None:
                if st.button(f"Open {topic} Page", key=f"open_topic_{assignment_id}"):
                    st.switch_page(topic_page)

        if is_done:
            st.success("Marked as done")
        else:
            if st.button("Mark as done", key=f"done_{assignment_type}_{assignment_id}"):
                completion_row = {
                    "assignment_id": assignment_id,
                    "assignment_type": assignment_type,
                    "class_code": str(assignment.get("class_code", "")).strip().lower(),
                    "username": st.session_state.get("username", ""),
                    "status": "done",
                    "completed_at": datetime.datetime.now().strftime("%Y-%m-%d %H-%M"),
                }
                if save_assignment_completion(completion_row):
                    st.success("Saved. Honor code complete.")
                    st.rerun()

def render_student_targeted_practice_page() -> None:
    st.title("Targeted Practice")
    class_code = user_profile.get("class_code", "")
    username_lc = username.strip().lower()
    completion_map = get_assignment_completion_map()
    targeted_practice = get_targeted_practice_for_student(class_code, username_lc)

    if targeted_practice.empty:
        st.info("No targeted practice yet. When your teacher sends one, it will show up here.")
        return

    st.caption("These are individual practice tasks for you. Open the matching topic page to work normally, then mark it done when you're finished.")
    for _, assignment in targeted_practice.iloc[::-1].iterrows():
        render_assignment_card(assignment, "targeted_practice", completion_map)

def render_student_class_assignments_page() -> None:
    st.title("Class Assignments")
    class_code = user_profile.get("class_code", "")
    completion_map = get_assignment_completion_map()
    class_assignments = get_teacher_assignments_for_class(class_code)

    if class_assignments.empty:
        st.info("No class assignments yet. Check back later.")
        return

    for _, assignment in class_assignments.iloc[::-1].iterrows():
        render_assignment_card(assignment, "class_assignment", completion_map)

def render_student_messages_page() -> None:
    st.title("Messages")
    class_code = user_profile.get("class_code", "")
    comments_df = get_teacher_comments_for_student(class_code, username)

    if comments_df.empty:
        st.info("No teacher comments yet.")
        return

    comments_df = comments_df.copy()
    if "created_at" in comments_df.columns:
        comments_df = comments_df.sort_values("created_at")

    for _, comment in comments_df.iloc[::-1].iterrows():
        scope = str(comment.get("scope", "class")).strip().title()
        topic = str(comment.get("topic", "")).strip()
        with st.container(border=True):
            st.caption(f"{scope} comment" + (f" | Topic: {topic}" if topic else ""))
            st.markdown(str(comment.get("message", "")).strip())
            if str(comment.get("created_at", "")).strip():
                st.caption(f"Sent {comment.get('created_at')}")

def render_teacher_assignments_and_comments(selected_code: str, teacher_classes: dict, student_accounts: dict, class_history_df: pd.DataFrame) -> None:
    topic_options = ["No topic"] + load_topics(selected_code)
    student_options = list(student_accounts.keys())
    completion_map = get_assignment_completion_map()

    tab_class, tab_targeted, tab_comments = st.tabs(["Class Assignments", "Targeted Practice", "Comments"])

    with tab_class:
        st.caption("Create one assignment for the whole class. Students will see it in their Assignments section and mark it done when finished.")
        with st.form(f"class_assignment_form_{selected_code}", clear_on_submit=True):
            title = st.text_input("Assignment title")
            topic = st.selectbox("Topic", topic_options, key=f"class_assignment_topic_{selected_code}")
            due_date = st.date_input("Due date")
            instructions = st.text_area("Instructions")
            attachment_link = st.text_input("Attachment link (e.g. a Google Drive link)")
            submitted = st.form_submit_button("Publish class assignment")

        if submitted:
            if not title.strip():
                st.warning("Please add a title first.")
            else:
                row = {
                    "assignment_id": make_record_id("class"),
                    "class_code": selected_code,
                    "topic": "" if topic == "No topic" else topic,
                    "title": title.strip(),
                    "instructions": instructions.strip(),
                    "due_date": str(due_date),
                    "attachment_type": "link" if attachment_link.strip() else "",
                    "attachment_link": attachment_link.strip(),
                    "attachment_b64": "",
                    "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H-%M"),
                    "created_by": st.session_state.get("username", ""),
                }
                if save_class_assignment(row):
                    st.success("Class assignment published.")
                    st.rerun()

        st.markdown("---")
        class_assignments = get_teacher_assignments_for_class(selected_code)
        if class_assignments.empty:
            st.info("No class assignments yet.")
        else:
            for _, assignment in class_assignments.iloc[::-1].iterrows():
                with st.container(border=True):
                    st.markdown(f"**{assignment.get('title', 'Untitled')}**")
                    st.caption(f"Due: {assignment.get('due_date', 'No due date')} | Topic: {assignment.get('topic', 'No topic') or 'No topic'}")
                    st.write(str(assignment.get("instructions", "")).strip())
                    assignment_id = str(assignment.get("assignment_id", "")).strip()
                    done_count = sum(
                        1
                        for (mapped_assignment_id, _username), status_row in completion_map.items()
                        if mapped_assignment_id == assignment_id and str(status_row.get("status", "")).strip().lower() == "done"
                    )
                    st.caption(f"Done by {done_count} student(s)")

    with tab_targeted:
        st.caption("Create practice for one student. It still appears in the student's normal workflow as targeted practice.")
        if not student_options:
            st.info("No students are in this class yet, so targeted practice is unavailable for now.")
        else:
            with st.form(f"targeted_practice_form_{selected_code}", clear_on_submit=True):
                student_username = st.selectbox("Student", student_options, format_func=lambda x: f"{student_accounts[x].get('first_name', x)} (@{x})" if x in student_accounts else x)
                title = st.text_input("Practice title")
                topic = st.selectbox("Topic", topic_options, key=f"targeted_topic_{selected_code}")
                due_date = st.date_input("Due date", key=f"targeted_due_{selected_code}")
                instructions = st.text_area("Instructions", key=f"targeted_instructions_{selected_code}")
                attachment_link = st.text_input("Attachment link (e.g. a Google Drive link)", key=f"targeted_link_{selected_code}")
                submitted = st.form_submit_button("Publish targeted practice")

            if submitted:
                if not title.strip():
                    st.warning("Please add a title first.")
                else:
                    row = {
                        "assignment_id": make_record_id("practice"),
                        "class_code": selected_code,
                        "username": student_username,
                        "topic": "" if topic == "No topic" else topic,
                        "title": title.strip(),
                        "instructions": instructions.strip(),
                        "due_date": str(due_date),
                        "attachment_type": "link" if attachment_link.strip() else "",
                        "attachment_link": attachment_link.strip(),
                        "attachment_b64": "",
                        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H-%M"),
                        "created_by": st.session_state.get("username", ""),
                    }
                    if save_targeted_practice(row):
                        st.success("Targeted practice published.")
                        st.rerun()

        st.markdown("---")
        targeted_df = get_targeted_practice_for_class(selected_code)
        if targeted_df.empty:
            st.info("No targeted practice yet.")
        else:
            st.caption("This is the full class preview; student-specific items appear to each student only.")
            st.dataframe(targeted_df[["title", "username", "topic", "due_date"]], use_container_width=True, hide_index=True)

    with tab_comments:
        st.caption("Leave feedback to the whole class or to one student individually.")
        with st.form(f"teacher_comment_form_{selected_code}", clear_on_submit=True):
            comment_scope = st.radio("Comment scope", ["Class", "Individual Student"], horizontal=True, key=f"comment_scope_{selected_code}")
            if student_options:
                comment_student = st.selectbox(
                    "Choose student",
                    student_options,
                    format_func=lambda x: f"{student_accounts[x].get('first_name', x)} (@{x})" if x in student_accounts else x,
                    key=f"comment_student_{selected_code}",
                    disabled=comment_scope != "Individual Student",
                    help="Pick a student when you want the comment to appear only for them.",
                )
            else:
                st.info("No students are in this class yet, so individual comments are unavailable for now.")
                comment_student = ""
            comment_topic = st.selectbox("Topic (optional)", topic_options, key=f"comment_topic_{selected_code}")
            comment_message = st.text_area("Comment")
            submitted = st.form_submit_button("Send comment")

        if submitted:
            if not comment_message.strip():
                st.warning("Write a comment first.")
            elif comment_scope == "Individual Student" and not student_options:
                st.warning("Add students to the class before sending an individual comment.")
            else:
                row = {
                    "comment_id": make_record_id("comment"),
                    "class_code": selected_code,
                    "scope": "student" if comment_scope == "Individual Student" else "class",
                    "username": comment_student if (comment_scope == "Individual Student" and student_options) else "",
                    "topic": "" if comment_topic == "No topic" else comment_topic,
                    "message": comment_message.strip(),
                    "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H-%M"),
                    "created_by": st.session_state.get("username", ""),
                }
                if save_teacher_comment(row):
                    st.success("Comment sent.")
                    st.rerun()

        st.markdown("---")
        comments_df = load_teacher_comments_df()
        if comments_df.empty:
            st.info("No comments yet.")
        else:
            comments_df = _normalize_working_sheet(comments_df)
            comments_df = comments_df[comments_df["class_code"] == selected_code]
            if comments_df.empty:
                st.info("No comments yet.")
            else:
                for _, row in comments_df.iloc[::-1].iterrows():
                    recipient = "Class" if str(row.get("scope", "")).strip() == "class" else f"@{row.get('username', '')}"
                    with st.container(border=True):
                        st.caption(f"To {recipient} | Topic: {row.get('topic', 'No topic') or 'No topic'} | {row.get('created_at', '')}")
                        st.write(str(row.get("message", "")).strip())

def render_teacher_dashboard() -> None:
    global teacher_detail_page
    st.title("Teacher Hub")

    user_profile = get_current_user_profile()
    teacher_classes = user_profile.get("classes", {})

    with st.sidebar.expander("Create a New Class", expanded=False):
        new_class_name = st.text_input("Class Name (e.g., Calculus Level 2):")
        if st.button("Generate Class"):
            if new_class_name.strip():
                new_code = generate_class_code()
                teacher_classes[new_code] = new_class_name.strip()
                users_df = load_users_df()
                users_df.loc[users_df["username"] == st.session_state.get("username", ""), "classes"] = json.dumps(teacher_classes)
                save_dataframe_to_worksheet("Users", users_df, USER_COLS)
                st.session_state["class_creation_success"] = f"Class '{new_class_name.strip()}' was successfully created! Enrollment Code: **{new_code}**"
                st.rerun()
            else:
                st.error("Please enter a class name.")

    with st.sidebar.expander("Delete an Existing Class", expanded=False):
        if not teacher_classes:
            st.caption("You don't have any classes to delete yet.")
        else:
            delete_options = {code: f"{name} ({code})" for code, name in teacher_classes.items()}
            class_to_delete_code = st.selectbox(
                "Select Class to Permanently Delete:",
                options=list(delete_options.keys()),
                format_func=lambda x: delete_options[x],
                key="delete_class_select",
            )

            confirm_delete = st.checkbox(
                f"I understand this deletes all logs associated with code {class_to_delete_code}",
                key="confirm_delete_chk",
            )
            if st.button("Permanently Delete Class", type="primary"):
                if confirm_delete:
                    deleted_class_name = teacher_classes[class_to_delete_code]
                    teacher_classes.pop(class_to_delete_code, None)
                    users_df = load_users_df()
                    users_df.loc[users_df["username"] == st.session_state.get("username", ""), "classes"] = json.dumps(teacher_classes)
                    save_dataframe_to_worksheet("Users", users_df, USER_COLS)
                    st.session_state["class_deletion_success"] = f"Class '{deleted_class_name}' was successfully permanently deleted."
                    st.rerun()
                else:
                    st.error("Please check the confirmation box before deleting.")

    if "class_creation_success" in st.session_state:
        st.success(st.session_state["class_creation_success"])
        del st.session_state["class_creation_success"]

    if "class_deletion_success" in st.session_state:
        st.error(st.session_state["class_deletion_success"])
        del st.session_state["class_deletion_success"]

    if not teacher_classes:
        st.info("Welcome! Open the left sidebar panel to create your first classroom section and get your enrollment code.")
        return

    st.subheader("Your Classrooms")
    st.caption("Click a classroom card to open its detailed view.")
    history_df = load_history_df()
    class_cols = st.columns(2)

    for idx, (class_code, class_name) in enumerate(teacher_classes.items()):
        with class_cols[idx % 2]:
            class_data = get_teacher_class_summary(class_code, teacher_classes, credentials, history_df)
            assignment_summary = get_class_assignment_summary(class_code, class_data["student_accounts"])
            with st.container(border=True):
                st.markdown(f"### {class_data['class_name']}")
                st.caption(f"Class code: `{class_data['class_code']}`")

                metric_cols = st.columns(4)
                with metric_cols[0]:
                    st.metric("# Students", class_data["total_students"])
                with metric_cols[1]:
                    st.metric("# Uploads", class_data["total_uploads"])
                with metric_cols[2]:
                    st.metric("Assignments", assignment_summary["class_assignment_count"] + assignment_summary["targeted_practice_count"])
                with metric_cols[3]:
                    st.metric("Pending", assignment_summary["pending_student_count"])

                st.write("Recently active students:")
                if class_data["attention_names"]:
                    st.write(f":red[{', '.join(class_data['attention_names'])}]")
                else:
                    st.write(":green[None so far.]")

                st.write("Students with pending work:")
                if assignment_summary["pending_students"]:
                    pretty_pending = []
                    for u in assignment_summary["pending_students"][:5]:
                        pretty_pending.append(class_data["student_accounts"].get(u, {}).get("first_name", u))
                    more_text = "" if len(assignment_summary["pending_students"]) <= 5 else f" +{len(assignment_summary['pending_students']) - 5} more"
                    st.write(f":orange[{', '.join(pretty_pending)}{more_text}]")
                else:
                    st.write(":green[None right now.]")

                st.write("Class Summary (AI):")
                st.write(class_data["ai_summary"])

                if st.button("Open Class", key=f"open_class_{class_code}"):
                    st.session_state["selected_class_code"] = class_code
                    st.session_state.pop("selected_student_username", None)
                    st.switch_page(teacher_detail_page)

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state["authentication_status"] = False
        for key in ("username", "name", "email", "roles"):
            st.session_state.pop(key, None)
        st.switch_page("app.py")

def render_student_detail_for_teacher(s_user: str, s_data: dict, class_history_df: pd.DataFrame, class_code: str) -> None:
    student_name = f"{s_data.get('first_name', s_user)} {s_data.get('last_name', '')}".strip()

    if st.button("← Back to Roster", key=f"back_to_roster_{s_user}"):
        st.session_state.pop("selected_student_username", None)
        st.rerun()

    st.subheader(f"{student_name}'s Performance History")
    st.caption(f"@{s_user}")

    s_history_df = class_history_df[class_history_df["username"] == s_user]
    status_filter = st.radio("Show submissions", ["All", "Passed", "Failed"], horizontal=True, key=f"student_detail_status_filter_{s_user}")

    topic_filter = st.selectbox(
        "Filter by topic",
        ["All Topics"] + load_topics(class_code),
        key=f"student_detail_topic_filter_{s_user}",
    )
    filtered_df = filter_history_by_status(s_history_df, status_filter)
    if topic_filter != "All Topics" and "topic" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["topic"].str.strip().str.lower() == topic_filter.strip().lower()]

    render_analytics_panel(
        "Individual Analytics",
        filtered_df,
        f"{student_name} hasn't scanned any math problems yet."
    )

    if not filtered_df.empty:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Uploads", len(filtered_df))
        with c2:
            st.metric("Passed", int((filtered_df["status"] == "Passed").sum()))
        with c3:
            st.metric("Failed", int((filtered_df["status"] == "Failed").sum()))

    st.markdown("---")
    if filtered_df.empty:
        st.info(f"{student_name} hasn't scanned any math problems yet.")
    else:
        st.subheader("Recent Attempts")
        for _, item in filtered_df.iloc[::-1].iterrows():
            render_history_card(
                date_text=str(item["date"]),
                steps_text=str(item["equation"]),
                message_text=str(item["message"]),
                passed=item["status"] == "Passed",
                header_text=f"Topic: {item.get('topic', 'Unspecified') or 'Unspecified'}",
            )

def render_teacher_detail() -> None:
    global teacher_dashboard_page
    user_profile = get_current_user_profile()
    teacher_classes = user_profile.get("classes", {})
    selected_code = st.session_state.get("selected_class_code")

    if not selected_code or selected_code not in teacher_classes:
        st.warning("Pick a classroom from the teacher dashboard first.")
        if st.button("Back to Dashboard"):
            st.switch_page(teacher_dashboard_page)
        st.stop()

    history_df = load_history_df()
    student_accounts = {
        u: data for u, data in credentials["usernames"].items()
        if data.get("role") == "student" and data.get("class_code") == selected_code
    }
    class_history_df = filter_history_for_class(history_df, selected_code, list(student_accounts.keys()))

    st.title(f"{teacher_classes[selected_code]} ({selected_code})")
    st.caption("Detailed class view")

    if st.button("Back to Dashboard"):
        st.switch_page(teacher_dashboard_page)

    view_choice = st.sidebar.radio("View", ["Overview", "Student Roster & Live Logs", "Concept Analysis", "Assignments & Comments"], index=0)

    if view_choice != "Student Roster & Live Logs":
        st.session_state.pop("selected_student_username", None)

    if view_choice == "Overview":
        assignment_summary = get_class_assignment_summary(selected_code, student_accounts)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Students", len(student_accounts))
        with c2:
            st.metric("Uploads", len(class_history_df))
        with c3:
            st.metric("Assignments", assignment_summary["class_assignment_count"] + assignment_summary["targeted_practice_count"])
        with c4:
            st.metric("Pending Students", assignment_summary["pending_student_count"])

        attention_names = []
        for s_user, s_data in student_accounts.items():
            s_history_df = class_history_df[class_history_df["username"] == s_user]
            if not s_history_df.empty and len(s_history_df) > 0:
                attention_names.append(s_data.get("first_name", s_user))

        st.write("Students needing attention:")
        st.write(", ".join(attention_names) if attention_names else "None so far.")

        st.write("Class Summary (AI):")
        if class_history_df.empty:
            st.info("No uploads yet for this class.")
        else:
            st.success(f"{len(class_history_df)} total submissions logged. {len(attention_names)} student(s) may need extra support.")

        st.markdown("---")
        st.write("Assignment snapshot:")
        if assignment_summary["pending_students"]:
            pending_labels = [student_accounts[u].get("first_name", u) for u in assignment_summary["pending_students"] if u in student_accounts]
            st.write(f"Students with open work: {', '.join(pending_labels) if pending_labels else 'None'}")
        else:
            st.write("No open work right now.")

        st.markdown("---")
        render_trend_and_prediction("Class-Wide Growth Trend", class_history_df, "All Topics", "All")

    elif view_choice == "Student Roster & Live Logs":
        if not student_accounts:
            st.info("No students have entered this classroom code yet.")
        else:
            selected_student = st.session_state.get("selected_student_username")

            if selected_student and selected_student in student_accounts:
                render_student_detail_for_teacher(selected_student, student_accounts[selected_student], class_history_df, selected_code)
            else:
                roster_topic_filter = st.selectbox(
                    "Filter submissions by topic",
                    ["All Topics"] + load_topics(selected_code),
                    key="roster_topic_filter",
                )
                st.caption("Click a student to view their full history.")
                for s_user, s_data in student_accounts.items():
                    s_history_df = class_history_df[class_history_df["username"] == s_user]
                    if roster_topic_filter != "All Topics" and "topic" in s_history_df.columns:
                        s_history_df = s_history_df[s_history_df["topic"].str.strip().str.lower() == roster_topic_filter.strip().lower()]

                    student_name = f"{s_data.get('first_name', s_user)} {s_data.get('last_name', '')}".strip()
                    col_name, col_count = st.columns([4, 1])
                    with col_name:
                        if st.button(f"{student_name} (@{s_user})", key=f"open_student_{s_user}", use_container_width=True):
                            st.session_state["selected_student_username"] = s_user
                            st.rerun()
                    with col_count:
                        st.caption(f"{len(s_history_df)} submissions")

    elif view_choice == "Assignments & Comments":
        render_teacher_assignments_and_comments(selected_code, teacher_classes, student_accounts, class_history_df)

    else:
        with st.expander("➕ Add a new topic"):
            st.caption(f"This topic will only be added for {teacher_classes.get(selected_code, selected_code)} — not your other classes.")
            new_topic_input = st.text_input("New topic name", key="new_topic_input")
            if st.button("Add Topic", key="add_topic_button"):
                cleaned_topic = new_topic_input.strip()
                if not cleaned_topic:
                    st.warning("Enter a topic name first.")
                elif add_topic(selected_code, cleaned_topic):
                    st.success(f"'{cleaned_topic}' added. It will now appear as an upload page for students in this class.")
                    st.rerun()

        st.subheader("Submissions by Topic")
        topic_counts_df = summarize_topic_counts(class_history_df)
        if topic_counts_df.empty:
            st.info("No submissions yet to break down by topic.")
        else:
            st.bar_chart(topic_counts_df)

        st.markdown("---")
        concept_topic_filter = st.selectbox(
            "Focus the misconception breakdown on a topic",
            ["All Topics"] + load_topics(selected_code),
            key="concept_topic_filter",
        )
        if concept_topic_filter != "All Topics" and "topic" in class_history_df.columns:
            topic_filtered_df = class_history_df[class_history_df["topic"].str.strip().str.lower() == concept_topic_filter.strip().lower()]
        else:
            topic_filtered_df = class_history_df

        st.subheader("Overall Class Errors")
        overall_error_counts = summarize_history(class_history_df)
        if overall_error_counts:
            st.bar_chart(overall_error_counts)
        else:
            st.info("No class errors recorded yet.")

        st.markdown("---")
        render_trend_and_prediction(f"Topic Growth Trend — {concept_topic_filter}", class_history_df, concept_topic_filter, "All")

        render_analytics_panel(
            f"Classroom Misconception Breakdown — {concept_topic_filter}",
            topic_filtered_df,
            "Zero student errors recorded for this topic yet."
        )

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state["authentication_status"] = False
        for key in ("username", "name", "email", "roles"):
            st.session_state.pop(key, None)
        st.switch_page("app.py")

auth_status = st.session_state.get("authentication_status")

if auth_status:
    st.write(f'Welcome back, *{st.session_state["name"]}*!')

    username = st.session_state["username"]
    user_profile = credentials["usernames"].get(username, {})

    if user_profile:
        # Genuine profile found in this rerun's credentials read — trust it,
        # and remember it in case a future rerun's read is transiently empty.
        user_role = user_profile.get('role', 'student')
        st.session_state["roles"] = user_role
    else:
        # The live Users-sheet read for this rerun came back without this
        # user (e.g. a transient Google Sheets error/rate limit — see
        # load_users_df's exception fallback). Do NOT silently treat an
        # already-authenticated user as a brand-new student in that case;
        # fall back to whatever role we last confirmed for this session.
        user_role = st.session_state.get("roles", "student")

    if user_role == "teacher":
        teacher_dashboard_page = st.Page(render_teacher_dashboard, title="Teacher Dashboard")
        teacher_detail_page = st.Page(render_teacher_detail, title="Class Detail")
        current_page = st.navigation([teacher_dashboard_page, teacher_detail_page], position="hidden")
        current_page.run()

    else:
        global student_topic_pages_by_slug
        student_topic_pages_by_slug = {}
        authenticator.logout('Logout', 'sidebar')

        topic_pages = []
        for topic in load_topics(user_profile.get("class_code", "")):
            page = st.Page(functools.partial(render_student_checker_page, topic), title=topic, url_path=_topic_slug(topic))
            topic_pages.append(page)
            student_topic_pages_by_slug[_topic_slug(topic)] = page

        targeted_practice_page = st.Page(render_student_targeted_practice_page, title="Targeted Practice", url_path="targeted-practice")
        assignments_page = st.Page(render_student_class_assignments_page, title="Class Assignments", url_path="assignments")
        messages_page = st.Page(render_student_messages_page, title="Messages", url_path="messages")
        history_page = st.Page(render_student_history_page, title="My Performance History", url_path="history")

        current_page = st.navigation(topic_pages + [targeted_practice_page, assignments_page, messages_page, history_page])
        current_page.run()

elif auth_status is False:
    st.error('Username/password is incorrect')
    init_mode = st.radio("Choose Action:", ["Login", "Sign Up"], horizontal=True)
    if init_mode == "Login": render_login()

elif auth_status is None or auth_status == "":
    init_mode = st.radio("Choose Action:", ["Login", "Sign Up"], horizontal=True)
    if init_mode == "Login":
        render_login()
        st.warning('Please enter your username and password')
    elif init_mode == "Sign Up":
        try:
            signup_role = st.radio("I am registering as a:", ["Student", "Teacher"], horizontal=True)
            if signup_role == "Student":
                student_class_code = st.text_input("Enter Classroom Code from your Teacher:")

            email_of_user, username, name = authenticator.register_user(location="main")
            if username:
                users_df = load_users_df()
                hashed_pw = authenticator.authentication_controller.authentication_model.credentials["usernames"][username]["password"]
                password_hint = authenticator.authentication_controller.authentication_model.credentials["usernames"][username].get("password_hint", "")
                
                new_user_row = pd.DataFrame([{
                    "username": username, "password": hashed_pw, "first_name": name, "last_name": "", "email": email_of_user,
                    "role": 'student' if signup_role == "Student" else 'teacher',
                    "class_code": student_class_code.strip().lower() if signup_role == "Student" else "unassigned",
                    "classes": json.dumps({}) if signup_role == "Teacher" else "",
                    "password_hint": password_hint
                }])
                
                updated_users = pd.concat([users_df, new_user_row], ignore_index=True)
                if save_dataframe_to_worksheet("Users", updated_users, USER_COLS):
                    st.success("Account created successfully! Flip over to the 'Login' tab.")
                    st.rerun()
                else:
                    st.warning("Account details were filled in, but the save failed. Check your Google Sheets credentials and spreadsheet setup.")
        except Exception as e:
            st.error(e)