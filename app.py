import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from PIL import Image
import pillow_heif
import random
import os
import string
from App.sanitiser import clean_image
from App.checker import detect_first_error

if os.path.exists("/data"):
    DATA_PATH = "/data/config.yaml"
else:
    DATA_PATH = "config.yaml"  

try:
    with open(DATA_PATH, "r") as file:
        config = yaml.safe_load(file)
except FileNotFoundError:
    config = {"credentials": {"usernames": {}}}

st.set_page_config(page_title="V.I.C.T.O.R", layout="centered")

with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
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
    user_profile = config['credentials']['usernames'].get(username, {})
    user_role = user_profile.get('role', 'student')

    if user_role == "teacher":
        st.title("Teacher Hub")
        
        if 'classes' not in user_profile:
            config['credentials']['usernames'][username]['classes'] = {}
            with open('config.yaml', 'w') as file:
                yaml.dump(config, file, default_flow_style=False)
        
        teacher_classes = user_profile.get('classes', {}) 

        with st.sidebar.expander("Create a New Class", expanded=False):
            new_class_name = st.text_input("Class Name (e.g., Calculus Level 2):")
            if st.button("Generate Class"):
                if new_class_name.strip():
                    new_code = generate_class_code()
                    config['credentials']['usernames'][username]['classes'][new_code] = new_class_name.strip()
                    with open('config.yaml', 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)
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
                        config['credentials']['usernames'][username]['classes'].pop(class_to_delete_code, None)
                        with open('config.yaml', 'w') as file:
                            yaml.dump(config, file, default_flow_style=False)

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
            
            all_users = config['credentials']['usernames']
            student_accounts = {
                u: data for u, data in all_users.items() 
                if data.get('role') == 'student' and data.get('class_code') == selected_code
            }
            
            total_students = len(student_accounts)
            total_class_scans = 0
            total_class_passed = 0
            
            for s_user, s_data in student_accounts.items():
                s_history = s_data.get('history', [])
                total_class_scans += len(s_history)
                total_class_passed += sum(1 for item in s_history if item['status'] == "Passed")
                
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
                has_failures = False
                
                for s_user, s_data in student_accounts.items():
                    for log in s_data.get('history', []):
                        if log.get('status') == "Failed":
                            e_type = log.get('error_type', 'Conceptual/Other')
                            if e_type in error_counts:
                                error_counts[e_type] += 1
                                has_failures = True
                
                if not has_failures:
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
                        percentage = int((error_counts[most_common_error] / total_errors) * 100)
                        
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
                        s_history = s_data.get('history', [])
                        with st.expander(f"{s_data['first_name']} (@{s_user}) — {len(s_history)} submissions"):
                            if not s_history:
                                st.caption("This student hasn't checked any equations yet.")
                            else:
                                for item in reversed(s_history):
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

                            if 'history' not in config['credentials']['usernames'][username]:
                                config['credentials']['usernames'][username]['history'] = []

                            import datetime
                            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")

                            config['credentials']['usernames'][username]['history'].append({
                                'date': timestamp,
                                'equation': " ➔ ".join(steps),
                                'status': status_str,
                                'message': result.message,
                                "error_type": error_type_str
                                })

                            with open('config.yaml', 'w') as file:
                                yaml.dump(config, file, default_flow_style=False)

        with tab2:
            st.title("Your Performance History")
            st.subheader("Track your math submissions over time")
            
            history = user_profile.get('history', [])

            if not history:
                st.info("You haven't scanned any math problems yet! Your history log will appear here.")
            else:
                total_scans = len(history)
                passed_scans = sum(1 for item in history if item['status'] == "Passed")
                st.metric(label="Success Rate", value=f"{int((passed_scans/total_scans)*100)}%", delta=f"{total_scans} Total Submissions")
                
                st.markdown("---")
                for item in reversed(history):
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
                if signup_role == "Student":
                    config['credentials']['usernames'][username]['role'] = 'student'
                    config['credentials']['usernames'][username]['class_code'] = student_class_code.strip().lower() if student_class_code else 'unassigned'

                    with open('config.yaml', 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)

                    st.success(f"Account created! You have successfully joined classroom code `{student_class_code.strip().lower()}`. Click the 'Login' tab to access V.I.C.T.O.R.")

                elif signup_role == "Teacher":
                    config['credentials']['usernames'][username]['role'] = 'teacher'
                    config['credentials']['usernames'][username]['classes'] = {}

                    with open('config.yaml', 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)

                    st.success("Teacher profile registered perfectly! Flip over to the 'Login' tab to launch your administrative hub.")

        except Exception as e:
            st.error(e)
