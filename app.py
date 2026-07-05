import streamlit as st
import json
import random
import string
import datetime
from PIL import Image
import pillow_heif
import pandas as pd
import streamlit_authenticator as stauth
from streamlit_gsheets import GSheetsConnection
from App.sanitiser import clean_image
from App.checker import detect_first_error

st.set_page_config(page_title="V.I.C.T.O.R", layout="centered")

conn = st.connection("gsheets", type=GSheetsConnection)

def load_users_df():
    try:
        return conn.read(spreadsheet=st.secrets["GSHEET_URL"], worksheet="Users", ttl=0)
    except Exception:
        return pd.DataFrame(columns=["username", "password", "first_name", "last_name", "email", "role", "class_code", "classes"])

def load_history_df():
    try:
        return conn.read(spreadsheet=st.secrets["GSHEET_URL"], worksheet="History", ttl=0)
    except Exception:
        return pd.DataFrame(columns=["username", "date", "equation", "status", "message", "error_type"])

users_df = load_users_df()
credentials = {"usernames": {}}

for _, row in users_df.dropna(subset=["username"]).iterrows():

    classes_dict = {}
    if pd.notna(row.get("classes")) and str(row["classes"]).strip():
        try:
            classes_dict = json.loads(str(row["classes"]))
        except Exception:
            classes_dict = {}

    credentials["usernames"][str(row["username"])] = {
        "password": str(row["password"]),
        "first_name": str(row["first_name"]) if pd.notna(row["first_name"]) else "",
        "last_name": str(row["last_name"]) if pd.notna(row["last_name"]) else "",
        "email": str(row["email"]) if pd.notna(row["email"]) else "",
        "role": str(row["role"]) if pd.notna(row["role"]) else "student",
        "class_code": str(row["class_code"]).strip().lower() if pd.notna(row["class_code"]) else "unassigned",
        "classes": classes_dict
    }

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

def generate_class_code():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

def render_login() -> None:
    try:
        authenticator.login(location="main", key="victor_main_login")
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
                    conn.update(spreadsheet=st.secrets["GSHEET_URL"], worksheet="Users", data=users_df)
                    
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
                        
                        # Remove class and rewrite tracking dataframe to Google Sheet
                        teacher_classes.pop(class_to_delete_code, None)
                        users_df = load_users_df()
                        users_df.loc[users_df["username"] == username, "classes"] = json.dumps(teacher_classes)
                        conn.update(spreadsheet=st.secrets["GSHEET_URL"], worksheet="Users", data=users_df)

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
                
                error_counts = {
                    "Sign Error": 0, 
                    "Distribution Error": 0, 
                    "Arithmetic Error": 0, 
                    "Variable Mismatch": 0, 
                    "Conceptual/Other": 0
                }
                
                failed_scans = class_history_df[class_history_df["status"] == "Failed"]
                for e_type in failed_scans["error_type"]:
                    if e_type in error_counts:
                        error_counts[e_type] += 1
                
                if len(failed_scans) == 0:
                    st.success("Zero student errors recorded in this section yet! Everything balances perfectly.")
                else:
                    col_chart, col_insights = st.columns([3, 2])
                    
                    with col_chart:
                        st.caption("Mistake frequencies detected across all collective submissions:")
                        st.bar_chart(error_counts)
                        
                    with col_insights:
                        st.markdown("#### Automated Action Items")
                        total_errors = sum(error_counts.values())
                        most_common_error = max(error_counts, key=error_counts.get)
                        percentage = int((error_counts[most_common_error] / total_errors) * 100) if total_errors > 0 else 0
                        
                        st.metric(label="Top Class Misconception", value=most_common_error, delta=f"{percentage}% of mistakes")
                        
                        if most_common_error == "Sign Error":
                            st.warning("Students are commonly mismanaging negative integers when shifting expressions across `=` signs.")
                            st.info("**Suggested Intervention:** Run a 5-minute warm-up lesson focused strictly on performing matching inverse operations simultaneously to both sides.")
                        elif most_common_error == "Distribution Error":
                            st.warning("Students are dropping coefficients outside of group parentheses items.")
                            st.info("**Suggested Intervention:** Demonstrate the 'rainbow multiplication arrow method' on the whiteboard before next assignments.")
                        elif most_common_error == "Variable Mismatch":
                            st.warning("Students are accidentally misplacing or changing variables mid-equation.")
                            st.info("**Suggested Intervention:** Advise students to carefully utilize the handwriting validation text area tool inside V.I.C.T.O.R before submitting.")
                        else:
                            st.info("General arithmetic and evaluation errors are standard. Keep tracking step progression trends over the coming assignments.")

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
                                        if item['status'] == "Passed":
                                            st.success("PASSED")
                                        else:
                                            st.error("ERROR")
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
                                image = Image.frombytes(
                                    heif_file.mode, heif_file.size, heif_file.data, "raw", heif_file.mode, heif_file.stride
                                )
                                image.save("temp_image.png", format="PNG")
                            else:
                                with open("temp_image.png", "wb") as f:
                                    f.write(uploaded_file.getvalue())

                            st.session_state["ocr_text"] = clean_image("temp_image.png").strip()
                            st.session_state["ocr_ready"] = True
                        except Exception as e:
                            st.error("The AI service is experiencing heavy traffic. Please try again.")
                            st.caption(f"Technical info: {e}")

                if st.session_state["ocr_ready"]:
                    st.info("Review the OCR text below and fix any symbol mistakes before checking.")
                    st.caption("Use `*` for multiplication and `x` for a variable.")
                    st.text_area("Extracted Steps:", key="ocr_text", height=240)

                    if st.button("Confirm OCR and Check"):
                        steps = [s.strip() for s in st.session_state["ocr_text"].splitlines() if s.strip()]

                        if not steps:
                            st.warning("Please review or correct the OCR text first.")
                        else:
                            st.write(steps)
                            result = detect_first_error(steps)

                            if result.passed:
                                status_str = "Passed"
                                st.success(f"Passed: {result.message}")
                            else:
                                status_str = "Failed"
                                st.error(f"Error found: {result.message}")

                            msg_lower = result.message.lower()
                            if "sign" in msg_lower:
                                error_type_str = "Sign Error"
                            elif "distrib" in msg_lower:
                                error_type_str = "Distribution Error"
                            elif "arithmetic" in msg_lower or "calculat" in msg_lower:
                                error_type_str = "Arithmetic Error"
                            elif "variable" in msg_lower or "drop" in msg_lower:
                                error_type_str = "Variable Mismatch"
                            else:
                                error_type_str = "Conceptual/Other"

                            # Append math resolution to flat History spreadsheet tab
                            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")
                            history_df = load_history_df()
                            
                            new_log = pd.DataFrame([{
                                'username': username,
                                'date': timestamp,
                                'equation': " ➔ ".join(steps),
                                'status': status_str,
                                'message': result.message,
                                'error_type': error_type_str
                            }])

                            updated_history = pd.concat([history_df, new_log], ignore_index=True)
                            conn.update(spreadsheet=st.secrets["GSHEET_URL"], worksheet="History", data=updated_history)

        with tab2:
            st.title("Your Performance History")
            st.subheader("Track your math submissions over time")
            
            history_df = load_history_df()
            user_history_df = history_df[history_df["username"] == username]

            if user_history_df.empty:
                st.info("You haven't scanned any math problems yet! Your history log will appear here.")
            else:
                total_scans = len(user_history_df)
                passed_scans = sum(user_history_df['status'] == "Passed")
                st.metric(label="Success Rate", value=f"{int((passed_scans/total_scans)*100)}%", delta=f"{total_scans} Total Submissions")
                
                st.markdown("---")
                for _, item in user_history_df.iloc[::-1].iterrows():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        if item['status'] == "Passed":
                            st.success("PASSED")
                        else:
                            st.error("ERROR")
                    with col2:
                        st.markdown(f"**Date:** {item['date']}")
                        st.caption(f"**Steps Detected:** {item['equation']}")
                        st.markdown(f"*{item['message']}*")
                    st.markdown("---")

elif auth_status is False:
    st.error('Username/password is incorrect')
    init_mode = st.radio("Choose Action:", ["Login", "Sign Up"], horizontal=True)
    if init_mode == "Login":
        render_login()

elif auth_status is None or auth_status == "":
    init_mode = st.radio("Choose Action:", ["Login", "Sign Up"], horizontal=True)
    if init_mode == "Login":
        render_login()
        st.warning('Please enter your username and password')

    elif init_mode == "Sign Up":
        try:
            signup_role = st.radio("I am registering as a:", ["Student", "Teacher"], horizontal=True, key="signup_role_selector")

            if signup_role == "Student":
                student_class_code = st.text_input("Enter Classroom Code from your Teacher:", key="signup_student_code_field")
            else:
                st.info("As a Teacher, you will be able to instantly generate your own custom classroom sections from your dashboard once logged in.")

            st.markdown("---")
            st.caption("Fill in your account details below to finalize registration:")

            email_of_user, username, name = authenticator.register_user(location="main")

            if username:
                users_df = load_users_df()
              
                hashed_pw = authenticator.credentials["usernames"][username]["password"]
                
                new_user_row = pd.DataFrame([{
                    "username": username,
                    "password": hashed_pw,
                    "first_name": name,
                    "last_name": "",
                    "email": email_of_user,
                    "role": 'student' if signup_role == "Student" else 'teacher',
                    "class_code": student_class_code.strip().lower() if signup_role == "Student" else "unassigned",
                    "classes": json.dumps({}) if signup_role == "Teacher" else ""
                }])
                
                updated_users = pd.concat([users_df, new_user_row], ignore_index=True)
                conn.update(spreadsheet=st.secrets["GSHEET_URL"], worksheet="Users", data=updated_users)

                if signup_role == "Student":
                    st.success(f"Account created! You have successfully joined classroom code `{student_class_code.strip().lower()}`. Click the 'Login' tab to access V.I.C.T.O.R.")
                else:
                    st.success("Teacher profile registered! Flip over to the 'Login' tab to launch your administrative hub.")

        except Exception as e:
            st.error(e)