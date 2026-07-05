import streamlit as st
import json
import random
import string
import datetime
from PIL import Image
import pillow_heif
import pandas as pd
import gspread
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities import Hasher
from streamlit_gsheets import GSheetsConnection
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
    try:
        if gc and SPREADSHEET_ID:
            sh = gc.open_by_key(SPREADSHEET_ID)
            worksheet = sh.worksheet("Users")
            records = worksheet.get_all_records()
            return pd.DataFrame(records) if records else pd.DataFrame(columns=USER_COLS)
        return conn.read(worksheet="Users", ttl=0)
    except Exception:
        return pd.DataFrame(columns=["username", "password", "first_name", "last_name", "email", "role", "class_code", "classes", "password_hint"])

def load_history_df():
    try:
        if gc and SPREADSHEET_ID:
            sh = gc.open_by_key(SPREADSHEET_ID)
            worksheet = sh.worksheet("History")
            records = worksheet.get_all_records()
            return pd.DataFrame(records) if records else pd.DataFrame(columns=HISTORY_COLS)
        return conn.read(worksheet="History", ttl=0)
    except Exception:
        return pd.DataFrame(columns=["username", "date", "equation", "status", "message", "error_type"])

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

USER_COLS = ["username", "password", "first_name", "last_name", "email", "role", "class_code", "classes", "password_hint"]
HISTORY_COLS = ["username", "date", "equation", "status", "message", "error_type"]

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

# Extract and map active system accounts
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

st.session_state.setdefault("ocr_ready", False)
st.session_state.setdefault("ocr_text", "")
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

auth_status = st.session_state.get("authentication_status")

if auth_status:
    authenticator.logout('Logout', 'sidebar')
    st.write(f'Welcome back, *{st.session_state["name"]}*!')

    username = st.session_state["username"]
    user_profile = credentials["usernames"].get(username, {})
    user_role = user_profile.get('role', 'student')

    if user_role == "teacher":
        st.title("Teacher Hub")
        teacher_classes = user_profile.get('classes', {}) 

        with st.sidebar.expander("Create a New Class", expanded=False):
            new_class_name = st.text_input("Class Name (e.g., Calculus Level 2):")
            if st.button("Generate Class"):
                if new_class_name.strip():
                    new_code = generate_class_code()
                    
                    teacher_classes[new_code] = new_class_name.strip()
                    users_df = load_users_df()
                    users_df.loc[users_df["username"] == username, "classes"] = json.dumps(teacher_classes)
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
                    key="delete_class_select"
                )

                confirm_delete = st.checkbox(f"I understand this deletes all logs associated with code {class_to_delete_code}", key="confirm_delete_chk")
                if st.button("Permanently Delete Class", type="primary"):
                    if confirm_delete:
                        deleted_class_name = teacher_classes[class_to_delete_code]
                        teacher_classes.pop(class_to_delete_code, None)
                        users_df = load_users_df()
                        users_df.loc[users_df["username"] == username, "classes"] = json.dumps(teacher_classes)
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
        else:
            class_options = {code: f"{name} ({code})" for code, name in teacher_classes.items()}
            selected_code = st.selectbox("Select Classroom Section:", options=list(class_options.keys()), format_func=lambda x: class_options[x])
            
            student_accounts = {
                u: data for u, data in credentials["usernames"].items() 
                if data.get('role') == 'student' and data.get('class_code') == selected_code
            }
            
            history_df = load_history_df()
            class_history_df = history_df[history_df["username"].isin(student_accounts.keys())]
            
            total_students = len(student_accounts)
            total_class_scans = len(class_history_df)
            total_class_passed = sum(class_history_df["status"] == "Passed")
                
            st.markdown(f"### Dashboard for *{teacher_classes[selected_code]}*")
            st.info(f"Share this enrollment code with students to let them join: **{selected_code}**")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric(label="Students Enrolled", value=total_students)
            with c2:
                st.metric(label="Total Checks Run", value=total_class_scans)
            with c3:
                class_rate = f"{int((total_class_passed/total_class_scans)*100)}%" if total_class_scans > 0 else "N/A"
                st.metric(label="Class Accuracy Rate", value=class_rate)
                
            st.markdown("---")
            tab_analytics, tab_roster = st.tabs(["Concept Analytics Insights", "Student Roster & Live Logs"])
            
            with tab_analytics:
                st.subheader("Classroom Misconception Breakdown")
                error_counts = {"Sign Error": 0, "Distribution Error": 0, "Arithmetic Error": 0, "Variable Mismatch": 0, "Conceptual/Other": 0}
                
                failed_scans = class_history_df[class_history_df["status"] == "Failed"]
                for e_type in failed_scans["error_type"]:
                    if e_type in error_counts:
                        error_counts[e_type] += 1
                
                if len(failed_scans) == 0:
                    st.success("Zero student errors recorded in this section yet! Everything balances perfectly.")
                else:
                    col_chart, col_insights = st.columns([3, 2])
                    with col_chart:
                        st.bar_chart(error_counts)
                    with col_insights:
                        total_errors = sum(error_counts.values())
                        most_common_error = max(error_counts, key=error_counts.get)
                        percentage = int((error_counts[most_common_error] / total_errors) * 100) if total_errors > 0 else 0
                        st.metric(label="Top Class Misconception", value=most_common_error, delta=f"{percentage}% of mistakes")

            with tab_roster:
                st.subheader("Student Roster & Activity Feed")
                if not student_accounts:
                    st.caption("No students have entered this classroom code yet.")
                else:
                    for s_user, s_data in student_accounts.items():
                        s_history_df = class_history_df[class_history_df["username"] == s_user]
                        with st.expander(f"{s_data['first_name']} (@{s_user}) — {len(s_history_df)} submissions"):
                            if s_history_df.empty:
                                st.caption("This student hasn't checked any equations yet.")
                            else:
                                for _, item in s_history_df.iloc[::-1].iterrows():
                                    col1, col2 = st.columns([1, 5])
                                    with col1:
                                        st.success("PASSED") if item['status'] == "Passed" else st.error("ERROR")
                                    with col2:
                                        st.markdown(f"**Date:** {item['date']}")
                                        st.caption(f"**Steps Detected:** {item['equation']}")
                                        st.markdown(f"*{item['message']}*")
                                    st.markdown("---")

    else:
        tab1, tab2 = st.tabs(["V.I.C.T.O.R Checker", "My Performance History"])

        with tab1:
            st.title("V.I.C.T.O.R")
            st.subheader(f"Upload your math steps for verification (Class Code: `{user_profile.get('class_code', 'Unassigned')}`)")
            uploaded_file = st.file_uploader("Choose an image...", type=["jpg", "png", "jpeg", "heic", "heif"])

            if uploaded_file is not None:
                current_file_name = uploaded_file.name
                if st.session_state.get("last_uploaded_file") != current_file_name:
                    st.session_state["last_uploaded_file"] = current_file_name
                    st.session_state["ocr_text"] = ""
                    st.session_state["ocr_ready"] = False

                if st.button("Run OCR"):
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

                            st.session_state["ocr_text"] = clean_image("temp_image.png").strip()
                            st.session_state["ocr_ready"] = True
                        except Exception as e:
                            st.error("The AI service is experiencing heavy traffic. Please try again.")

                if st.session_state["ocr_ready"]:
                    st.info("Review the OCR text below and fix any symbol mistakes before checking.")
                    st.text_area("Extracted Steps:", key="ocr_text", height=240)

                    if st.button("Confirm OCR and Check"):
                        steps = [s.strip() for s in st.session_state["ocr_text"].splitlines() if s.strip()]
                        if not steps:
                            st.warning("Please review or correct the OCR text first.")
                        else:
                            st.write(steps)
                            result = detect_first_error(steps)
                            status_str = "Passed" if result.passed else "Failed"
                            
                            if result.passed:
                                st.success(f"Passed: {result.message}")
                            else:
                                st.error(f"Error found: {result.message}")

                            msg_lower = result.message.lower()
                            if "sign" in msg_lower: error_type_str = "Sign Error"
                            elif "distrib" in msg_lower: error_type_str = "Distribution Error"
                            elif "arithmetic" in msg_lower or "calculat" in msg_lower: error_type_str = "Arithmetic Error"
                            elif "variable" in msg_lower or "drop" in msg_lower: error_type_str = "Variable Mismatch"
                            else: error_type_str = "Conceptual/Other"

                            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")
                            history_df = load_history_df()
                            
                            new_log = pd.DataFrame([{
                                'username': username, 'date': timestamp, 'equation': "\n".join(steps),
                                'status': status_str, 'message': result.message, 'error_type': error_type_str
                            }])

                            updated_history = pd.concat([history_df, new_log], ignore_index=True)
                            save_dataframe_to_worksheet("History", updated_history, HISTORY_COLS)

        with tab2:
            st.title("Your Performance History")
            history_df = load_history_df()
            user_history_df = history_df[history_df["username"] == username]

            if user_history_df.empty:
                st.info("You haven't scanned any math problems yet!")
            else:
                total_scans = len(user_history_df)
                passed_scans = sum(user_history_df['status'] == "Passed")
                st.metric(label="Success Rate", value=f"{int((passed_scans/total_scans)*100)}%", delta=f"{total_scans} Total Submissions")
                
                st.markdown("---")
                for _, item in user_history_df.iloc[::-1].iterrows():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.success("PASSED") if item['status'] == "Passed" else st.error("ERROR")
                    with col2:
                        st.markdown(f"**Date:** {item['date']}")
                        st.caption(f"**Steps Detected:** {item['equation']}")
                        st.markdown(f"*{item['message']}*")
                    st.markdown("---")

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
