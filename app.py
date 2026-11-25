from flask import Flask, render_template, request, redirect, send_from_directory, make_response, session
from werkzeug.utils import secure_filename
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from io import BytesIO
import os
import subprocess
import mysql.connector

from database import get_connection
from NER import extract_entities

app = Flask(__name__)

app.secret_key = "ucms_secret_key"

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# =========================================================
# CREATE NOTIFICATION
# =========================================================

def create_notification(user_email, complaint_id, message):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO notifications
        (user_email, complaint_id, message)
        VALUES (%s, %s, %s)
    """, (
        user_email,
        complaint_id,
        message
    ))

    conn.commit()
    conn.close()

# =========================
# Home Page
# =========================

@app.route("/")
def home():
    return render_template("login.html")

# =========================
# Register Page
# =========================

@app.route("/register")
def register():
    return render_template("register.html")

# =========================
# Complaint Page
# =========================

@app.route("/complaint")
def complaint():

    if session.get("user_role") not in ["Student", "Teacher"]:
        return "Access Denied! Only Student or Teacher can access this page.", 403

    return render_template(
        "complaint.html",
        user_email=session.get("user_email")
    )

# =========================
# Register User
# =========================

@app.route("/register_user", methods=["POST"])
def register_user():

    name = request.form["full_name"]
    email = request.form["email"]
    password = request.form["password"]
    role = request.form["role"]

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            INSERT INTO users
            (full_name, email, password, role)
            VALUES (%s, %s, %s, %s)
        """, (name, email, password, role))

        conn.commit()
        conn.close()

        return "Registration Successful!"

    except mysql.connector.IntegrityError:

        conn.close()

        return "Email already exists. Please use another email."

# =========================
# Login User
# =========================

@app.route("/login_user", methods=["POST"])
def login_user():

    email = request.form["email"]
    password = request.form["password"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM users
        WHERE email=%s AND password=%s
    """, (email, password))

    user = cursor.fetchone()

    conn.close()

    if user:

        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        session["user_role"] = user["role"]
        session["user_name"] = user["full_name"]

        # =========================
        # ROLE BASED REDIRECT
        # =========================

        if user["role"] == "Admin":

            return redirect("/admin")

        elif user["role"] == "Program Head":

            return redirect("/program_head")


        elif user["role"] == "Committee":

            return redirect("/committee")

        elif user["role"] == "HOD":

            return redirect("/hod")

        elif user["role"] == "Accounts Coordinator":

            return redirect("/account_coordinator")

        elif user["role"] == "Student":

            return render_template(
                "complaint.html",
                user_email=email
            )

        elif user["role"] == "Teacher":

            return render_template(
                "complaint.html",
                user_email=email
            )

        else:

            return "Invalid user role!"

    else:

        return "Invalid Email or Password!"

# =========================
# Submit Complaint
# =========================

@app.route("/submit_complaint", methods=["POST"])
def submit_complaint():

    complaint_by = request.form["complaint_by"]
    email = request.form["email"]
    complaint = request.form["complaint"]

    # =========================
    # Evidence Upload
    # =========================

    evidence = request.files["evidence"]

    filename = ""

    if evidence and evidence.filename != "":

        filename = secure_filename(evidence.filename)

        evidence.save(
            os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )
        )

    # =========================
    # Extract Information
    # =========================

    result = extract_entities(
        complaint,
        complaint_by
    )

    student_name = result["student_name"]
    teacher_name = result["teacher_name"]
    target_name = result["target_name"]
    target_role = result["target_role"]
    department = result["department"]
    category = result["category"]
    complaint_date = result["date"]

    # =========================
    # Save Complaint
    # =========================

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO complaints
        (
            student_name,
            teacher_name,
            department,
            complaint,
            complaint_date,
            category,
            status,
            complaint_by,
            evidence,
            user_email
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        student_name,
        teacher_name,
        department,
        complaint,
        complaint_date,
        category,
        "Pending",
        complaint_by,
        filename,
        email
    ))

    # Get newly created complaint ID
    complaint_id = cursor.lastrowid

    # =====================================================
    # DETERMINE WHO SHOULD RECEIVE THE COMPLAINT
    # =====================================================

    notification_users = []

    # =====================================================
    # 1. COMPLAINT AGAINST PROGRAM HEAD
    # =====================================================

    if target_role == "Program Head":

        notification_message = (
            "New complaint against Program Head received. "
            f"Category: {category}"
        )

        cursor.execute("""
            SELECT email
            FROM users
            WHERE role = 'HOD'
        """)

        notification_users = cursor.fetchall()

   
    # =====================================================
    # 2. FEE AND SALARY COMPLAINTS
    # =====================================================

    elif category in ["Fee Issue", "Salary Issue"]:

        notification_message = (
            f"New {category} complaint received."
        )

        cursor.execute("""
            SELECT email
            FROM users
            WHERE role = 'Accounts Coordinator'
        """)

        notification_users = cursor.fetchall()


    # =====================================================
    # 3. STUDENT -> STUDENT
    #    HOD + PROGRAM HEAD
    # =====================================================

    elif (
        complaint_by.lower() == "student"
        and target_role == "Student"
    ):

        notification_message = (
            f"New {complaint_by} complaint received. "
            f"Category: {category}"
        )

        cursor.execute("""
            SELECT email
            FROM users
            WHERE role = 'HOD'
               OR (
                    role = 'Program Head'
                    AND department = %s
                  )
        """, (department,))

        notification_users = cursor.fetchall()

    # =====================================================
    # 4. STUDENT -> TEACHER
    #    HOD ONLY
    # =====================================================

    elif (
        complaint_by.lower() == "student"
        and target_role == "Teacher"
    ):

        notification_message = (
            f"New {complaint_by} complaint received. "
            f"Category: {category}"
        )

        cursor.execute("""
            SELECT email
            FROM users
            WHERE role = 'HOD'
        """)

        notification_users = cursor.fetchall()


    # =====================================================
    # 5. TEACHER -> STUDENT
    #    HOD + RELEVANT DEPARTMENT PROGRAM HEAD
    # =====================================================

    elif (
        complaint_by.lower() == "teacher"
        and target_role == "Student"
    ):

        notification_message = (
            f"New {complaint_by} complaint received. "
            f"Category: {category}"
        )

        cursor.execute("""
            SELECT email
            FROM users
            WHERE role = 'HOD'
               OR (
                    role = 'Program Head'
                    AND department = %s
                  )
        """, (department,))

        notification_users = cursor.fetchall()


    # =====================================================
    # 6. TEACHER -> TEACHER
    #    HOD ONLY
    # =====================================================

    elif (
        complaint_by.lower() == "teacher"
        and target_role == "Teacher"
    ):

        notification_message = (
            f"New {complaint_by} complaint received. "
            f"Category: {category}"
        )

        cursor.execute("""
            SELECT email
            FROM users
            WHERE role = 'HOD'
        """)

        notification_users = cursor.fetchall()

    # =====================================================
    # 7. ACADEMIC / ATTENDANCE / RESULT / GENERAL
    #    HOD + PROGRAM HEAD
    # =====================================================

    else:

        notification_message = (
            f"New {complaint_by} complaint received. "
            f"Category: {category}"
        )

        cursor.execute("""
            SELECT email
            FROM users
            WHERE role IN ('HOD', 'Program Head')
        """)

        notification_users = cursor.fetchall()

    # =====================================================
    # CREATE NOTIFICATIONS
    # =====================================================

    for user in notification_users:

        cursor.execute("""
            INSERT INTO notifications
            (user_email, complaint_id, message, is_read)
            VALUES (%s, %s, %s, 0)
        """, (
            user[0],
            complaint_id,
            notification_message
        ))

    # =========================
    # Save Everything
    # =========================

    conn.commit()
    conn.close()

    return "Complaint Submitted Successfully!"


# =========================
# Voice Complaint
# =========================

@app.route("/voice_complaint", methods=["POST"])
def voice_complaint():

    try:

        result = subprocess.run(
            [
                "py",
                "-3.13",
                "voice_ner.py"
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )

        output = result.stdout

        print("======================================")
        print("VOICE SCRIPT OUTPUT")
        print(output)
        print("======================================")

        # Find the recognized voice text
        if "VOICE_TEXT_START" in output and "VOICE_TEXT_END" in output:

            voice_text = output.split(
                "VOICE_TEXT_START", 1
            )[1].split(
                "VOICE_TEXT_END", 1
            )[0].strip()

            print("======================================")
            print("TEXT SENT TO COMPLAINT PAGE:")
            print(voice_text)
            print("======================================")

            return render_template(
                "complaint.html",
                voice_text=voice_text,
                voice_success=True
            )

        else:

            return render_template(
                "complaint.html",
                voice_text="",
                voice_error="Sorry, I could not understand your voice. Please try again."
            )

    except Exception as e:

        print("VOICE COMPLAINT ERROR:", str(e))

        return render_template(
            "complaint.html",
            voice_text="",
            voice_error="Voice recording failed. Please try again."
        )

# =========================
# Uploaded Files
# =========================

@app.route("/uploads/<filename>")
def uploaded_file(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )
# =========================================================
# track complaint page
# =========================================================
@app.route("/track")
def track():

    if session.get("user_role") not in ["Student", "Teacher"]:
        return "Access Denied! Only Student or Teacher can access this page.", 403

    user_email = session.get(
        "user_email",
        ""
    )
    message = request.args.get(
    "message",
    ""
    )

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # =========================
    # UNREAD NOTIFICATIONS
    # =========================

    cursor.execute("""
        SELECT COUNT(*) AS unread_notifications
        FROM notifications
        WHERE user_email=%s
          AND is_read=0
    """, (
        user_email,
    ))

    unread_notifications = cursor.fetchone()["unread_notifications"]

    conn.close()

    return render_template(
        "track_complaint.html",
        user_email=user_email,
        unread_notifications=unread_notifications,
        message=message
    )

# =========================
# Track Complaint
# =========================

@app.route("/track_complaint", methods=["POST"])
def track_complaint():

    if session.get("user_role") not in ["Student", "Teacher"]:
        return "Access Denied! Only Student or Teacher can access this page.", 403

    email = session.get(
        "user_email",
        ""
    )

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # =========================
    # GET USER COMPLAINTS + FEEDBACK
    # =========================

    cursor.execute("""
        SELECT
            c.*,
            c.created_at AS complaint_date_display,
            f.id AS feedback_id,
            f.rating AS feedback_rating,
            f.comments AS feedback_comments
        FROM complaints c
        LEFT JOIN feedback f
            ON c.id = f.complaint_id
        WHERE c.user_email=%s
        ORDER BY c.id DESC
    """, (
        email,
    ))

    complaints = cursor.fetchall()

    # =========================
    # UNREAD NOTIFICATIONS
    # =========================

    cursor.execute("""
        SELECT COUNT(*) AS unread_notifications
        FROM notifications
        WHERE user_email=%s
          AND is_read=0
    """, (
        email,
    ))

    unread_notifications = cursor.fetchone()["unread_notifications"]

    conn.close()

    return render_template(
        "track_complaint.html",
        complaints=complaints,
        user_email=email,
        unread_notifications=unread_notifications
    )

# =========================================================
# SUBMIT FEEDBACK
# =========================================================

@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():

    if session.get("user_role") not in ["Student", "Teacher"]:
        return "Access Denied!", 403

    complaint_id = request.form["complaint_id"]

    rating = request.form["rating"]

    comments = request.form.get(
        "comments",
        ""
    ).strip()

    user_email = session.get(
        "user_email"
    )

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # =====================================================
    # CHECK COMPLAINT BELONGS TO CURRENT USER
    # =====================================================

    cursor.execute("""
        SELECT
            id,
            category,
            status,
            approval_status
        FROM complaints
        WHERE id=%s
          AND user_email=%s
    """, (
        complaint_id,
        user_email
    ))

    complaint = cursor.fetchone()

    if not complaint:

        conn.close()

        return "Complaint not found!", 404

    # =====================================================
    # FEE ISSUE
    # FEEDBACK ONLY AFTER ACCOUNTS COORDINATOR SOLVES IT
    # =====================================================

    if complaint["category"] in ["Fee Issue", "Salary Issue"]:

        if complaint["status"] != "Solved":

            conn.close()

            return """
            <script>
                alert("Feedback can only be submitted after the Accounts Coordinator resolves the fee complaint.");
                window.history.back();
            </script>
            """

    # =====================================================
    # ALL OTHER COMPLAINTS
    # KEEP EXISTING ADMIN DECISION FLOW
    # =====================================================

    else:

        if complaint["approval_status"] not in [
            "Approved",
            "Rejected"
        ]:

            conn.close()

            return """
            <script>
                alert("Feedback can only be submitted after the Admin decision.");
                window.history.back();
            </script>
            """

    # =====================================================
    # CHECK IF FEEDBACK ALREADY EXISTS
    # =====================================================

    cursor.execute("""
        SELECT id
        FROM feedback
        WHERE complaint_id=%s
    """, (
        complaint_id,
    ))

    existing_feedback = cursor.fetchone()

    if existing_feedback:

        conn.close()

        return """
        <script>
            alert("Feedback has already been submitted for this complaint.");
            window.history.back();
        </script>
        """

    # =====================================================
    # SAVE FEEDBACK
    # =====================================================

    cursor.execute("""
        INSERT INTO feedback
        (
            complaint_id,
            user_email,
            rating,
            comments
        )
        VALUES (%s, %s, %s, %s)
    """, (
        complaint_id,
        user_email,
        rating,
        comments
    ))

    conn.commit()
    conn.close()

    return redirect(
        "/track?message=Feedback+Submitted+Successfully"
    )


# =========================================================
# PROGRAM HEAD DASHBOARD
# =========================================================
@app.route("/program_head")
def program_head():

    if session.get("user_role") != "Program Head":
        return "Access Denied! Only Program Head can access this page.", 403

    search = request.args.get("search", "").strip()

    # =====================================================
    # DETERMINE PROGRAM HEAD DEPARTMENT
    # =====================================================

    user_name = (
        session.get("user_name") or ""
    ).strip().lower()

    # Remove "sir " if it exists
    if user_name.startswith("sir "):
        user_name = user_name[4:].strip()


   # -----------------------------------------------------
   # OFFICIAL UNIVERSITY HIERARCHY DATA
   # -----------------------------------------------------

    UNIVERSITY_HIERARCHY = {
       "HOD": {
           "name": "Dr. Muhammad Mubashir Malik"
       },

       "BSCS": {
           "program_head": "Dr. Anser Munir Shah",
           "academic_coordinator": "Abdul Wahab Sami"
       },

       "BSIT": {
           "program_head": "Dr. Hamid Ghaus",
           "academic_coordinator": "Nasir Hussain"
       },

       "BSAI": {
           "program_head": "Dr. Azam",
           "academic_coordinator": "Imran Ali"
       },

       "Cyber Security": {
           "program_head": "Dr. Ahmed Raza",
           "academic_coordinator": "Qasim Niazi"
       },

       "ADC": {
           "program_head": "Dr. Shehzad Akbar",
           "academic_coordinator": "Sir Zeeshan Haider Ali"
       },

       "Software Engineering": {
           "program_head": "Dr. Shehzad Akbar",
           "academic_coordinator": "Sir Zeeshan Haider Ali"
       },

       "Data Sciences": {
           "program_head": "Dr. Shehzad Akbar",
           "academic_coordinator": "Sir Zeeshan Haider Ali"
       },

       "Overall Faculty Coordinator": {
           "name": "Muneeb-ur-Rehman"
       }
   }


    # -----------------------------------------------------
    # Program Head Department Mapping
    # -----------------------------------------------------

    if "dr. anser munir shah" in user_name:
        program_department = "CS"

        # Existing NER value + standardized value
        department_values = (
            "CS",
            "Computer Science Department"
        )

    elif "dr. hamid ghaus" in user_name:
        program_department = "IT"

        department_values = (
            "IT",
            "IT Department"
        )

    elif "dr. azam" in user_name:
        program_department = "AI"

        department_values = (
            "AI",
            "Artificial Intelligence Department"
        )
    
    elif "dr. shehzad akbar" in user_name:
        program_department = "Software"

        department_values = (
            "Software Engineering",
            "Software Engineering Department",
            "ADC",
            "ADC Department",
            "Data Sciences",
            "Data Sciences Department"
        )
    
    elif "dr. ahmed raza" in user_name:
        program_department = "Cyber Security"

        department_values = (
            "Cyber Security",
            "Cyber Security Department",
            "Cybersecurity",
            "Cybersecurity Department"
        )

    else:
        return """
        <script>
            alert("Program Head department is not configured for this account.");
            window.location.href = "/";
        </script>
        """

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # =====================================================
    # GET COMPLAINTS + FEEDBACK
    # CURRENT PROGRAM HEAD DEPARTMENT ONLY
    # =====================================================

    if search:

        cursor.execute("""
            SELECT
                c.*,
                f.id AS feedback_id,
                f.rating AS feedback_rating,
                f.comments AS feedback_comments,
                f.user_email AS feedback_user_email
            FROM complaints c
            LEFT JOIN feedback f
                ON c.id = f.complaint_id
            WHERE c.department IN (%s, %s)
              AND c.category NOT IN ('Fee Issue', 'Salary Issue')
              AND (
                    c.student_name LIKE %s
                    OR c.teacher_name LIKE %s
                    OR c.department LIKE %s
                    OR c.category LIKE %s
                    OR c.complaint LIKE %s
              )
            ORDER BY c.id DESC
        """, (
            department_values[0],
            department_values[1],
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%"
        ))

    else:

        cursor.execute("""
            SELECT
                c.*,
                f.id AS feedback_id,
                f.rating AS feedback_rating,
                f.comments AS feedback_comments,
                f.user_email AS feedback_user_email
            FROM complaints c
            LEFT JOIN feedback f
                ON c.id = f.complaint_id
            WHERE c.department IN (%s, %s)
             AND c.category NOT IN ('Fee Issue', 'Salary Issue')
            ORDER BY c.id DESC
        """, (
            department_values[0],
            department_values[1]
        ))

    complaints = cursor.fetchall()

    # =====================================================
    # GET ALL COMMITTEE MEMBERS
    # =====================================================

    cursor.execute("""
        SELECT *
        FROM committee_members
        ORDER BY committee_type, member_name
    """)

    committee_members = cursor.fetchall()

    # =====================================================
    # DASHBOARD COUNTS
    # CURRENT PROGRAM HEAD DEPARTMENT ONLY
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM complaints
        WHERE department IN (%s, %s)
          AND category != 'Fee Issue'
    """, (
        department_values[0],
        department_values[1]
    ))

    total_count = cursor.fetchone()["total"]

    # =====================================================
    # PENDING COUNT
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS pending
        FROM complaints
        WHERE department IN (%s, %s)
          AND category != 'Fee Issue'
          AND status = 'Pending'
    """, (
        department_values[0],
        department_values[1]
    ))

    pending_count = cursor.fetchone()["pending"]

    # =====================================================
    # IN PROGRESS COUNT
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS progress
        FROM complaints
        WHERE department IN (%s, %s)
          AND category != 'Fee Issue'
          AND status = 'In Progress'
    """, (
        department_values[0],
        department_values[1]
    ))

    progress_count = cursor.fetchone()["progress"]

    # =====================================================
    # RESOLVED COUNT
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS resolved
        FROM complaints
        WHERE department IN (%s, %s)
          AND category != 'Fee Issue'
          AND status = 'Resolved'
    """, (
        department_values[0],
        department_values[1]
    ))

    resolved_count = cursor.fetchone()["resolved"]

    # =====================================================
    # INVESTIGATION REPORT COUNT
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS report_count
        FROM complaints
        WHERE department IN (%s, %s)
          AND category != 'Fee Issue'
          AND (
                investigation_report IS NOT NULL
                AND investigation_report != ''
          )
    """, (
        department_values[0],
        department_values[1]
    ))

    report_count = cursor.fetchone()["report_count"]

    # =====================================================
    # FEEDBACK COUNT
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS feedback_count
        FROM feedback f
        INNER JOIN complaints c
            ON c.id = f.complaint_id
        WHERE c.department IN (%s, %s)
          AND c.category != 'Fee Issue'
    """, (
        department_values[0],
        department_values[1]
    ))

    feedback_count = cursor.fetchone()["feedback_count"]

    # =====================================================
    # UNREAD NOTIFICATIONS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS unread
        FROM notifications
        WHERE user_email = %s
          AND is_read = 0
    """, (
        session.get("user_email"),
    ))

    unread_notifications = cursor.fetchone()["unread"]

    conn.close()

    import re

    filtered_complaints = []

    # =====================================================
    # PROCESS EACH COMPLAINT
    # =====================================================

    for complaint in complaints:

        complaint["conflict_member_id"] = None
        complaint["conflict_member_name"] = ""
        complaint["recommended_committee"] = []

        complaint_text = (
            complaint.get("complaint") or ""
        ).strip().lower()

        complaint_by = (
            complaint.get("complaint_by") or ""
        ).strip().lower()

        category = (
            complaint.get("category") or ""
        ).strip().lower()

        # =================================================
        # COMPLAINT AGAINST PROGRAM HEAD
        # =================================================

        program_head_patterns = [

            r"\bagainst\s+(?:the\s+)?program\s+head\b",

            r"\bcomplaint\s+against\s+(?:the\s+)?program\s+head\b",

            r"\bcomplain\s+against\s+(?:the\s+)?program\s+head\b",

            r"\bcomplain\s+about\s+(?:the\s+)?program\s+head\b",

            r"\bcomplaint\s+about\s+(?:the\s+)?program\s+head\b",

            r"\breport\s+(?:the\s+)?program\s+head\b",

            r"\bagainst\s+program\s+head\b",

            r"\bprogram\s+head\s+(?:is|was|has|have|treated|treats|harass|harassed|harassing|ignored|ignores|refused|reject|rejected|misbehaved|misbehaving|unfair|unfairly|not\s+responding|not\s+helping|not\s+cooperating)\b"
        ]

        is_program_head_complaint = False

        for pattern in program_head_patterns:

            if re.search(
                pattern,
                complaint_text,
                re.IGNORECASE
            ):

                is_program_head_complaint = True
                break

        if is_program_head_complaint:
            continue

        # =================================================
        # DETERMINE TARGET PERSON
        # =================================================

        target_text = ""

        # -------------------------------------------------
        # STUDENT COMPLAINT
        # -------------------------------------------------

        if complaint_by == "student":

            target_text = (
                complaint.get("teacher_name") or ""
            ).strip().lower()

            if not target_text:

                teacher_pattern = (
                    r"\b(?:teacher|professor|prof|sir|madam|ma'am|mam)\s+"
                    r"([a-z]+(?:\s+[a-z]+){0,2})"
                )

                match = re.search(
                    teacher_pattern,
                    complaint_text,
                    re.IGNORECASE
                )

                if match:

                    target_text = (
                        match.group(1)
                        .strip()
                        .lower()
                    )

        # -------------------------------------------------
        # TEACHER COMPLAINT
        # -------------------------------------------------

        elif complaint_by == "teacher":

            teacher_words = [
                "teacher",
                "professor",
                "prof",
                "sir",
                "madam",
                "ma'am",
                "mam"
            ]

            # Example:
            # against teacher Ali Khan

            for word in teacher_words:

                pattern = (
                    r"\bagainst\s+"
                    + re.escape(word)
                    + r"\s+"
                    + r"([a-z]+(?:\s+[a-z]+){0,2})"
                )

                match = re.search(
                    pattern,
                    complaint_text,
                    re.IGNORECASE
                )

                if match:

                    target_text = (
                        match.group(1)
                        .strip()
                        .lower()
                    )

                    break

            # Example:
            # teacher Ali Khan is harassing me

            if not target_text:

                for word in teacher_words:

                    pattern = (
                        r"\b"
                        + re.escape(word)
                        + r"\s+"
                        + r"([a-z]+(?:\s+[a-z]+){0,2})\s+"
                        r"(?:is|was|has|have|keeps|kept|"
                        r"harass|harassed|harassing|"
                        r"treat|treated|treats)\b"
                    )

                    match = re.search(
                        pattern,
                        complaint_text,
                        re.IGNORECASE
                    )

                    if match:

                        target_text = (
                            match.group(1)
                            .strip()
                            .lower()
                        )

                        break

    
        # =================================================
        # PROGRAM HEAD VISIBILITY
        #
        # Student -> Teacher: HIDE
        # Teacher -> Teacher: HIDE
        # Student -> Student: SHOW
        # Teacher -> Student: SHOW
        # =================================================

        if category == "harassment" or "academic" in category:

            # Student -> Teacher: HIDE from Program Head
            if complaint_by == "student":

                teacher_match = re.search(
                    r"\b(?:teacher|professor|prof|sir|madam|ma'am|mam)\b",
                    complaint_text,
                    re.IGNORECASE
                )

                if (
                    complaint.get("teacher_name")
                    or teacher_match
                ):
                    continue

            # Teacher -> Teacher: HIDE from Program Head
            elif complaint_by == "teacher":

                teacher_match = re.search(
                    r"\b(?:teacher|professor|prof|sir|madam|ma'am|mam|colleague)\b",
                    complaint_text,
                    re.IGNORECASE
                )

                if teacher_match:
                    continue

        # =================================================
        # DETERMINE CORRECT COMMITTEE
        # =================================================

        if category == "fee issue":

            required_type = "accounts"

        else:

            required_type = category

        # =================================================
        # CONFLICT CHECK
        # ONLY RELEVANT COMMITTEE
        # =================================================

        if target_text:

            for member in committee_members:

                member_name = (
                    member.get("member_name") or ""
                ).strip()

                member_type = (
                    member.get("committee_type") or ""
                ).strip().lower()

                if not member_name:
                    continue

                if member_type != required_type:
                    continue

                member_name_lower = member_name.lower()

                if (
                    member_name_lower == target_text
                    or member_name_lower in target_text
                ):

                    complaint["conflict_member_id"] = member["id"]

                    complaint["conflict_member_name"] = (
                        member["member_name"]
                    )

                    break

        # =================================================
        # RECOMMENDED COMMITTEE
        # =================================================

        for member in committee_members:

            member_type = (
                member.get("committee_type") or ""
            ).strip().lower()

            if member_type != required_type:
                continue

            if (
                complaint.get("conflict_member_id")
                and member["id"]
                == complaint["conflict_member_id"]
            ):
                continue

            complaint["recommended_committee"].append(
                member
            )

        # =================================================
        # ADD COMPLAINT
        # =================================================

        filtered_complaints.append(complaint)

    # =====================================================
    # SEND DATA TO PROGRAM HEAD TEMPLATE
    # =====================================================

    return render_template(
        "program_head.html",

        complaints=filtered_complaints,

        committee_members=committee_members,

        total_count=total_count,

        pending_count=pending_count,

        progress_count=progress_count,

        resolved_count=resolved_count,

        report_count=report_count,

        feedback_count=feedback_count,

        unread_notifications=unread_notifications,

        displayed_count=len(filtered_complaints),

        program_department=program_department,
        user_name=session.get("user_name")
    )
@app.route("/hod")
def hod():

    if session.get("user_role") != "HOD":
        return "Access Denied! Only HOD can access this page.", 403

    search = request.args.get("search", "").strip()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # =========================================================
    # GET COMPLAINTS
    # =========================================================

    if search:

        cursor.execute("""
            SELECT *
            FROM complaints
            WHERE category != 'Fee Issue'
              AND (
                    student_name LIKE %s
                    OR teacher_name LIKE %s
                    OR department LIKE %s
                    OR category LIKE %s
                    OR complaint LIKE %s
                  )
            ORDER BY id DESC
        """, (
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%"
        ))

    else:

        cursor.execute("""
            SELECT *
            FROM complaints
            WHERE category != 'Fee Issue'
            ORDER BY id DESC
        """)

    complaints = cursor.fetchall()

    # =========================================================
    # GET ALL COMMITTEE MEMBERS
    # =========================================================

    cursor.execute("""
        SELECT *
        FROM committee_members
        ORDER BY committee_type, member_name
    """)

    committee_members = cursor.fetchall()

    # =========================================================
    # PENDING COUNT
    # =========================================================

    cursor.execute("""
        SELECT COUNT(*) AS pending
        FROM complaints
        WHERE status = 'Pending'
          AND category != 'Fee Issue'
    """)

    pending_count = cursor.fetchone()["pending"]

    # =========================================================
    # CATEGORY COUNT
    # =========================================================

    cursor.execute("""
        SELECT COUNT(DISTINCT category) AS categories
        FROM complaints
        WHERE category != 'Fee Issue'
    """)

    categories_count = cursor.fetchone()["categories"]

    # =========================================================
    # UNREAD NOTIFICATIONS
    # =========================================================

    cursor.execute("""
        SELECT COUNT(*) AS unread
        FROM notifications
        WHERE user_email = %s
          AND is_read = 0
    """, (
        session.get("user_email"),
    ))

    unread_notifications = cursor.fetchone()["unread"]

    conn.close()

    import re

    # =========================================================
    # PROCESS EACH COMPLAINT
    # =========================================================

    for complaint in complaints:

        complaint["conflict_member_id"] = None
        complaint["conflict_member_name"] = ""
        complaint["recommended_committee"] = []

        complaint_text = (
            complaint.get("complaint") or ""
        ).strip().lower()

        complaint_by = (
            complaint.get("complaint_by") or ""
        ).strip().lower()

        category = (
            complaint.get("category") or ""
        ).strip().lower()

        # =====================================================
        # FIND TARGET PERSON
        # =====================================================

        target_text = ""

        # -----------------------------------------------------
        # STUDENT COMPLAINT
        # -----------------------------------------------------

        if complaint_by == "student":

            target_text = (
                complaint.get("teacher_name") or ""
            ).strip().lower()

            if not target_text:

                teacher_pattern = (
                    r"\b(?:teacher|professor|prof|sir|madam|ma'am|mam)\s+"
                    r"([a-z]+(?:\s+[a-z]+){0,2})"
                )

                match = re.search(
                    teacher_pattern,
                    complaint_text,
                    re.IGNORECASE
                )

                if match:

                    target_text = (
                        match.group(1)
                        .strip()
                        .lower()
                    )

        # -----------------------------------------------------
        # TEACHER COMPLAINT
        # -----------------------------------------------------

        elif complaint_by == "teacher":

            teacher_words = [
                "teacher",
                "professor",
                "prof",
                "sir",
                "madam",
                "ma'am",
                "mam"
            ]

            # Example:
            # against teacher Ali Khan

            for word in teacher_words:

                pattern = (
                    r"\bagainst\s+"
                    + re.escape(word)
                    + r"\s+"
                    + r"([a-z]+(?:\s+[a-z]+){0,2})"
                )

                match = re.search(
                    pattern,
                    complaint_text,
                    re.IGNORECASE
                )

                if match:

                    target_text = (
                        match.group(1)
                        .strip()
                        .lower()
                    )

                    break

            # Example:
            # teacher Ali Khan is harassing me

            if not target_text:

                for word in teacher_words:

                    pattern = (
                        r"\b"
                        + re.escape(word)
                        + r"\s+"
                        + r"([a-z]+(?:\s+[a-z]+){0,2})\s+"
                        r"(?:is|was|has|have|keeps|kept|"
                        r"harass|harassed|harassing|"
                        r"treat|treated|treats)\b"
                    )

                    match = re.search(
                        pattern,
                        complaint_text,
                        re.IGNORECASE
                    )

                    if match:

                        target_text = (
                            match.group(1)
                            .strip()
                            .lower()
                        )

                        break

        # =====================================================
        # DETERMINE CORRECT COMMITTEE
        # =====================================================

        if category == "fee issue":

            required_type = "accounts"

        else:

            required_type = category

        # =====================================================
        # CONFLICT CHECK
        #
        # VERY IMPORTANT:
        # ONLY CHECK THE CORRECT COMMITTEE
        # =====================================================

        if target_text:

            for member in committee_members:

                member_name = (
                    member.get("member_name") or ""
                ).strip()

                member_type = (
                    member.get("committee_type") or ""
                ).strip().lower()

                if not member_name:
                    continue

                # Ignore members from other committees

                if member_type != required_type:
                    continue

                member_name_lower = member_name.lower()

                if (
                    member_name_lower == target_text
                    or member_name_lower in target_text
                ):

                    complaint["conflict_member_id"] = member["id"]

                    complaint["conflict_member_name"] = (
                        member["member_name"]
                    )

                    break

        # =====================================================
        # RECOMMENDED COMMITTEE
        # =====================================================

        for member in committee_members:

            member_type = (
                member.get("committee_type") or ""
            ).strip().lower()

            # Only correct committee

            if member_type != required_type:
                continue

            # Remove conflict member

            if (
                complaint.get("conflict_member_id")
                and member["id"]
                == complaint["conflict_member_id"]
            ):
                continue

            complaint["recommended_committee"].append(
                member
            )

    # =========================================================
    # RENDER HOD PAGE
    # =========================================================

    return render_template(
        "hod.html",
        user_name=session.get("user_name"),
        complaints=complaints,
        committee_members=committee_members,
        pending_count=pending_count,
        categories_count=categories_count,
        unread_notifications=unread_notifications
    )
# =========================================================
# ACCOUNT COORDINATOR DASHBOARD
# =========================================================

@app.route("/account_coordinator")
def account_coordinator():

    if session.get("user_role") != "Accounts Coordinator":
        return "Access Denied! Only Account Coordinator can access this page.", 403

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    selected_status = request.args.get("status", "").strip()

    query = """
        SELECT
            c.*,
            f.id AS feedback_id,
            f.rating AS feedback_rating,
            f.comments AS feedback_comments
        FROM complaints c
        LEFT JOIN feedback f
            ON c.id = f.complaint_id
        WHERE c.category IN ('Fee Issue', 'Salary Issue')

    """

    params = []

    if selected_status in ["In Process", "Solved"]:
        query += " AND c.status = %s"
        params.append(selected_status)

    query += " ORDER BY c.id DESC"

    cursor.execute(query, tuple(params))

    complaints = cursor.fetchall()

    conn.close()

    return render_template(
        "account_coordinator.html",
        complaints=complaints,
        selected_status=selected_status
    )
# =========================================================
# COMMITTEE DASHBOARD
# =========================================================

@app.route("/committee")
def committee():

    if session.get("user_role") != "Committee":
        return "Access Denied! Only Committee can access this page.", 403

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.*
        FROM complaints c
        JOIN committee_members cm
            ON FIND_IN_SET(cm.id, c.selected_committee) > 0
        WHERE c.forward_to = 'Committee'
          AND cm.member_email = %s
        ORDER BY c.id DESC
    """, (
        session.get("user_email"),
    ))

    complaints = cursor.fetchall()

    conn.close()

    return render_template(
        "committee.html",
        complaints=complaints
    )
#--------------------------------------
# FORWARD COMPLAINT TO COMMITTEE
#--------------------------------------

@app.route("/forward/<int:id>", methods=["POST"])
def forward(id):

    # Only Program Head and HOD can forward complaints
    if session.get("user_role") not in ["Program Head", "HOD"]:
        return "Access Denied!", 403

    forwarding_user_email = session.get("user_email")
    forwarding_role = session.get("user_role")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ---------------------------------------------------------
    # Get complaint
    # ---------------------------------------------------------
    cursor.execute("""
        SELECT *
        FROM complaints
        WHERE id = %s
    """, (id,))

    complaint = cursor.fetchone()

    if not complaint:
        conn.close()
        return "Complaint not found!", 404

    # ---------------------------------------------------------
    # Determine the correct committee
    # ---------------------------------------------------------
    category = (
        complaint.get("category") or ""
    ).strip().lower()

    if category == "fee issue":

        required_type = "accounts"

    elif category == "academic":

        required_type = "academic"

    elif category == "harassment":

        required_type = "harassment"

    elif category == "attendance":

        required_type = "attendance"

    elif category in ["result issue", "general complaint"]:

        required_type = "other"

    elif category == "it":

        required_type = "it"

    else:

        required_type = category

    # ---------------------------------------------------------
    # Get ONLY members of the correct committee
    # ---------------------------------------------------------
    cursor.execute("""
        SELECT *
        FROM committee_members
        WHERE LOWER(TRIM(committee_type)) = %s
        ORDER BY id
    """, (
        required_type,
    ))

    members = cursor.fetchall()

    if not members:

        conn.close()

        return f"""
        <script>
            alert(
                "No committee members are available for the {category} complaint."
            );
            window.history.back();
        </script>
        """

    # ---------------------------------------------------------
    # Check conflict of interest
    # ---------------------------------------------------------
    conflict_member_id = None
    conflict_member_name = None

    complaint_by = (
        complaint.get("complaint_by") or ""
    ).strip().lower()

    student_name = (
        complaint.get("student_name") or ""
    ).strip().lower()

    teacher_name = (
        complaint.get("teacher_name") or ""
    ).strip().lower()

    for member in members:

        member_name = (
            member.get("member_name") or ""
        ).strip().lower()

        if (
            (student_name and member_name == student_name)
            or
            (teacher_name and member_name == teacher_name)
            or
            (
                complaint_by
                and member_name == complaint_by
            )
        ):

            conflict_member_id = member["id"]

            conflict_member_name = (
                member["member_name"]
            )

            break

    # ---------------------------------------------------------
    # Conflict found
    # ---------------------------------------------------------
    if conflict_member_id:

        conn.close()

        dashboard = (
            "hod"
            if forwarding_role == "HOD"
            else "program_head"
        )

        return f"""
        <script>
            alert(
                "Conflict of Interest detected against {conflict_member_name}. " +
                "Please use Create Committee to select other committee members."
            );

            window.location.href = "/{dashboard}";
        </script>
        """

    # ---------------------------------------------------------
    # Select ONLY the correct committee members
    # ---------------------------------------------------------
    selected_committee = ",".join(
        str(member["id"])
        for member in members
    )

    # ---------------------------------------------------------
    # Save forwarding authority
    # ---------------------------------------------------------
    cursor.execute("""
        UPDATE complaints
        SET
            forward_to = %s,
            selected_committee = %s,
            forwarded_by = %s,
            status = %s
        WHERE id = %s
    """, (
        "Committee",
        selected_committee,
        forwarding_user_email,
        "In Progress",
        id
    ))

    # ---------------------------------------------------------
    # Notify ONLY the correct committee members
    # ---------------------------------------------------------
    for member in members:

        if member.get("member_email"):

            cursor.execute("""
                INSERT INTO notifications
                (
                    user_email,
                    complaint_id,
                    message
                )
                VALUES (%s, %s, %s)
            """, (
                member["member_email"],
                id,
                f"A {category} complaint has been forwarded to you by the {forwarding_role} for committee review."
            ))

    conn.commit()
    conn.close()

    # ---------------------------------------------------------
    # Return to the correct dashboard
    # ---------------------------------------------------------
    if forwarding_role == "HOD":

        return redirect(
            "/hod?message=Complaint+Forwarded+Successfully"
        )

    else:

        return redirect(
            "/program_head?message=Complaint+Forwarded+Successfully"
        )
    
#----------------------
# CREATE COMMITTEE
#----------------------

@app.route("/create_committee", methods=["POST"])
def create_committee():

    # Only Program Head and HOD can create a committee
    if session.get("user_role") not in ["Program Head", "HOD"]:
        return "Access Denied!", 403

    forwarding_user_email = session.get("user_email")
    forwarding_role = session.get("user_role")

    complaint_id = request.form.get("complaint_id")
    selected_members = request.form.getlist("selected_members")

    if not complaint_id:
        return "Complaint ID is missing!", 400

    if not selected_members:
        return "Please select at least one committee member!", 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ---------------------------------------------------------
    # Check complaint
    # ---------------------------------------------------------
    cursor.execute("""
        SELECT *
        FROM complaints
        WHERE id = %s
    """, (complaint_id,))

    complaint = cursor.fetchone()

    if not complaint:
        conn.close()
        return "Complaint not found!", 404

    # ---------------------------------------------------------
    # Check conflict of interest
    # ---------------------------------------------------------
    conflict_member_name = None

    complaint_by = complaint.get("complaint_by")
    student_name = complaint.get("student_name")
    teacher_name = complaint.get("teacher_name")

    for member_id in selected_members:

        cursor.execute("""
            SELECT *
            FROM committee_members
            WHERE id = %s
        """, (member_id,))

        member = cursor.fetchone()

        if not member:
            continue

        member_name = member.get("member_name", "").strip().lower()

        if (
            (complaint_by and member_name == str(complaint_by).strip().lower())
            or
            (student_name and member_name == str(student_name).strip().lower())
            or
            (teacher_name and member_name == str(teacher_name).strip().lower())
        ):
            conflict_member_name = member["member_name"]
            break

    if conflict_member_name:

        conn.close()

        dashboard = "hod" if forwarding_role == "HOD" else "program_head"

        return f"""
        <script>
            alert(
                "Conflict of Interest detected against {conflict_member_name}. " +
                "Please select another committee member."
            );
            window.location.href = "/{dashboard}";
        </script>
        """

    # ---------------------------------------------------------
    # Save selected committee members
    # ---------------------------------------------------------
    selected_committee = ",".join(
        str(member_id)
        for member_id in selected_members
    )

    # ---------------------------------------------------------
    # Save the person who created the committee
    # ---------------------------------------------------------
    cursor.execute("""
        UPDATE complaints
        SET
            forward_to = %s,
            selected_committee = %s,
            forwarded_by = %s,
            status = %s
        WHERE id = %s
    """, (
        "Committee",
        selected_committee,
        forwarding_user_email,
        "In Progress",
        complaint_id
    ))

    # ---------------------------------------------------------
    # Notify selected committee members
    # ---------------------------------------------------------
    for member_id in selected_members:

        cursor.execute("""
            SELECT member_email, member_name
            FROM committee_members
            WHERE id = %s
        """, (member_id,))

        member = cursor.fetchone()

        if member and member.get("member_email"):

            cursor.execute("""
                INSERT INTO notifications
                (
                    user_email,
                    complaint_id,
                    message
                )
                VALUES (%s, %s, %s)
            """, (
                member["member_email"],
                complaint_id,
                f"A complaint has been forwarded to you by the {forwarding_role} for committee review."
            ))

    conn.commit()
    conn.close()

    # ---------------------------------------------------------
    # Return to the correct dashboard
    # ---------------------------------------------------------
    if forwarding_role == "HOD":
        return redirect("/hod?message=Committee+Created+Successfully")
    else:
        return redirect("/program_head?message=Committee+Created+Successfully")

# =========================================================
# UPDATE COMPLAINT STATUS
# =========================================================

@app.route("/update_status", methods=["POST"])
def update_status():

    complaint_id = request.form["id"]
    status = request.form["status"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE complaints
        SET status=%s
        WHERE id=%s
        """,
        (
            status,
            complaint_id
        )
    )

    conn.commit()
    conn.close()

    return redirect("/program_head")


# =========================================================
# UPDATE COMMITTEE STATUS
# =========================================================

@app.route("/update_committee_status", methods=["POST"])
def update_committee_status():

    complaint_id = request.form["complaint_id"]
    status = request.form["status"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE complaints
        SET status=%s
        WHERE id=%s
        """,
        (
            status,
            complaint_id
        )
    )

    conn.commit()
    conn.close()

    return redirect("/committee")

# =========================================================
# SUBMIT COMMITTEE INVESTIGATION REPORT
# =========================================================

@app.route("/submit_investigation_report", methods=["POST"])
def submit_investigation_report():

    if session.get("user_role") != "Committee":
        return "Access Denied!", 403

    complaint_id = request.form.get("complaint_id")
    investigation_report = request.form.get("investigation_report", "").strip()
    committee_remarks = request.form.get("committee_remarks", "").strip()
    recommendation = request.form.get("recommendation", "").strip()

    if not complaint_id:
        return "Complaint ID is missing!", 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ---------------------------------------------------------
    # Check complaint
    # ---------------------------------------------------------
    cursor.execute("""
        SELECT id, category, complaint_by, forwarded_by
        FROM complaints
        WHERE id = %s
    """, (complaint_id,))

    complaint = cursor.fetchone()

    if not complaint:
        conn.close()
        return "Complaint not found!", 404

    # ---------------------------------------------------------
    # Save investigation report
    # ---------------------------------------------------------
    cursor.execute("""
        UPDATE complaints
        SET
            investigation_report = %s,
            committee_remarks = %s,
            recommendation = %s,
            status = %s
        WHERE id = %s
    """, (
        investigation_report,
        committee_remarks,
        recommendation,
        "Investigation Completed",
        complaint_id
    ))

    # ---------------------------------------------------------
    # Notify ONLY the person who originally forwarded
    # the complaint to the committee
    # ---------------------------------------------------------
    forwarded_by_email = complaint.get("forwarded_by")

    if forwarded_by_email:

        cursor.execute("""
            SELECT email, role
            FROM users
            WHERE email = %s
        """, (forwarded_by_email,))

        responsible_user = cursor.fetchone()

        if responsible_user:

            cursor.execute("""
                INSERT INTO notifications
                (
                    user_email,
                    complaint_id,
                    message
                )
                VALUES (%s, %s, %s)
            """, (
                responsible_user["email"],
                complaint_id,
                "Committee investigation completed. Investigation report, remarks and recommendation are available for review."
            ))
    # ---------------------------------------------------------
    # ALSO NOTIFY ADMIN
    # ---------------------------------------------------------
    cursor.execute("""
        SELECT email
        FROM users
        WHERE role = 'Admin'
    """)

    admin_users = cursor.fetchall()

    for admin in admin_users:

        if admin.get("email"):

            cursor.execute("""
                INSERT INTO notifications
                (
                    user_email,
                    complaint_id,
                    message,
                    is_read
                )
                VALUES (%s, %s, %s, 0)
            """, (
                admin["email"],
                complaint_id,
                "Committee investigation has been completed. Investigation report, remarks and recommendation are available for review."
            ))

    conn.commit()
    conn.close()

    return redirect("/committee?message=Investigation+Report+Submitted+Successfully")

# =========================================================
# ADMIN APPROVAL
# =========================================================

@app.route("/admin_approval", methods=["POST"])
def admin_approval():

    complaint_id = request.form["complaint_id"]

    approval_status = request.form[
        "approval_status"
    ]

    decision = request.form.get(
        "decision",
        ""
    ).strip()

    if approval_status not in [
        "Approved",
        "Rejected"
    ]:

        return "Invalid approval status!"

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # =====================================================
    # GET COMPLAINT OWNER EMAIL
    # =====================================================

    cursor.execute("""
        SELECT user_email
        FROM complaints
        WHERE id=%s
    """, (
        complaint_id,
    ))

    complaint = cursor.fetchone()

    if not complaint:

        conn.close()

        return "Complaint not found!", 404

    user_email = complaint["user_email"]

    # =====================================================
    # FINAL STATUS
    # =====================================================

    if approval_status == "Approved":

        final_status = "Resolved"

        notification_message = (
            f"Your complaint #{complaint_id} has been "
            f"approved by the Admin. "
            f"Final Status: Resolved."
        )

    else:

        final_status = "In Progress"

        notification_message = (
            f"Your complaint #{complaint_id} has been "
            f"reviewed by the Admin. "
            f"Decision: Rejected. "
            f"Status: In Progress."
        )

    # =====================================================
    # UPDATE COMPLAINT
    # =====================================================

    cursor.execute("""
        UPDATE complaints
        SET
            approval_status=%s,
            decision=%s,
            status=%s
        WHERE id=%s
    """, (
        approval_status,
        decision,
        final_status,
        complaint_id
    ))

    # =====================================================
    # NOTIFY STUDENT / TEACHER
    # =====================================================

    cursor.execute("""
        INSERT INTO notifications
        (
            user_email,
            complaint_id,
            message,
            is_read
        )
        VALUES (%s, %s, %s, 0)
    """, (
        user_email,
        complaint_id,
        notification_message
    ))

    # =====================================================
    # SAVE EVERYTHING
    # =====================================================

    conn.commit()
    conn.close()

    return redirect(
        "/admin?message=Decision+Saved+Successfully"
    )
# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route("/notifications")
def notifications():

    # Allow all logged-in users
    if not session.get("user_email"):
        return redirect("/")

    user_email = session.get("user_email")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # =====================================================
    # GET ALL NOTIFICATIONS FOR CURRENT USER
    # =====================================================

    cursor.execute("""
        SELECT
            id,
            user_email,
            complaint_id,
            message,
            is_read,
            created_at
        FROM notifications
        WHERE user_email=%s
        ORDER BY id DESC
    """, (
        user_email,
    ))

    notifications = cursor.fetchall()
    
    print("USER EMAIL:", user_email)
    print("NOTIFICATIONS:", notifications)

    # =====================================================
    # MARK NOTIFICATIONS AS READ
    # =====================================================

    cursor.execute("""
        UPDATE notifications
        SET is_read=1
        WHERE user_email=%s
          AND is_read=0
    """, (
        user_email,
    ))

    conn.commit()
    conn.close()

    return render_template(
        "notifications.html",
        notifications=notifications
    )
# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin():

    # Only Admin can access
    if session.get("user_role") != "Admin":
        return "Access Denied! Only Admin can access this page.", 403

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # =====================================================
    # ALL COMPLAINTS
    # =====================================================

    cursor.execute("""
        SELECT *
        FROM complaints
        ORDER BY id DESC
    """)

    complaints = cursor.fetchall()

    # =====================================================
    # GET ALL STUDENT / TEACHER FEEDBACK
    # =====================================================

    cursor.execute("""
        SELECT
            f.id,
            f.complaint_id,
            f.user_email,
            f.rating,
            f.comments AS feedback,
            c.complaint,
            c.category,
            c.student_name,
            c.teacher_name,
            c.created_at
        FROM feedback f
        LEFT JOIN complaints c
            ON c.id = f.complaint_id
        ORDER BY f.id DESC
    """)

    feedbacks = cursor.fetchall()

    # =====================================================
    # TOTAL COMPLAINTS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM complaints
    """)

    total = cursor.fetchone()["total"]

    # =====================================================
    # PENDING COMPLAINTS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS pending
        FROM complaints
        WHERE status='Pending'
    """)

    pending = cursor.fetchone()["pending"]

    # =====================================================
    # IN PROGRESS COMPLAINTS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS progress
        FROM complaints
        WHERE status='In Progress'
    """)

    progress = cursor.fetchone()["progress"]

    # =====================================================
    # RESOLVED COMPLAINTS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS resolved
        FROM complaints
        WHERE status='Resolved'
    """)

    resolved = cursor.fetchone()["resolved"]

    # =====================================================
    # UNREAD NOTIFICATIONS
    # =====================================================

    cursor.execute("""
        SELECT COUNT(*) AS unread_notifications
        FROM notifications
        WHERE user_email=%s
          AND is_read=0
    """, (
        session.get("user_email"),
    ))

    unread_notifications = cursor.fetchone()["unread_notifications"]

    # =====================================================
    # MESSAGE
    # =====================================================

    message = request.args.get(
        "message",
        ""
    )

    conn.close()

    return render_template(
        "admin.html",
        complaints=complaints,
        feedbacks=feedbacks,
        total=total,
        pending=pending,
        progress=progress,
        resolved=resolved,
        message=message,
        unread_notifications=unread_notifications
    )

# =========================================================
# DOWNLOAD REPORT
# =========================================================

@app.route("/download_report")
def download_report():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            student_name,
            teacher_name,
            department,
            category,
            status
        FROM complaints
    """)

    complaints = cursor.fetchall()

    conn.close()

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer
    )

    data = [
        [
            "Student",
            "Teacher",
            "Department",
            "Category",
            "Status"
        ]
    ]

    for row in complaints:

        data.append(
            list(row)
        )

    table = Table(
        data
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.grey
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.whitesmoke
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                1,
                colors.black
            ),
            (
                "BACKGROUND",
                (0, 1),
                (-1, -1),
                colors.beige
            )
        ])
    )

    doc.build([
        table
    ])

    pdf = buffer.getvalue()

    buffer.close()

    response = make_response(
        pdf
    )

    response.headers[
        "Content-Type"
    ] = "application/pdf"

    response.headers[
        "Content-Disposition"
    ] = (
        "attachment; "
        "filename=Complaint_Report.pdf"
    )

    return response
# =========================================================
# UPDATE ACCOUNT COORDINATOR COMPLAINT STATUS
# =========================================================

@app.route("/update_account_complaint_status", methods=["POST"])
def update_account_complaint_status():

    # -----------------------------------------------------
    # ONLY ACCOUNTS COORDINATOR CAN USE THIS ROUTE
    # -----------------------------------------------------
    if session.get("user_role") != "Accounts Coordinator":
        return "Access Denied!", 403

    complaint_id = request.form.get("complaint_id")
    new_status = request.form.get("status")

    resolution = request.form.get(
        "resolution",
        ""
    ).strip()

    # -----------------------------------------------------
    # VALIDATE STATUS
    # -----------------------------------------------------
    if new_status not in ["In Process", "Solved"]:
        return "Invalid status!", 400

    # -----------------------------------------------------
    # RESOLUTION IS REQUIRED WHEN SOLVED
    # -----------------------------------------------------
    if new_status == "Solved" and not resolution:

        return """
        <script>
            alert("Please enter the resolution before marking the complaint as Solved.");
            window.history.back();
        </script>
        """

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # -----------------------------------------------------
    # GET FEE COMPLAINT
    # -----------------------------------------------------
    cursor.execute("""
        SELECT
            id,
            user_email,
            complaint,
            category
        FROM complaints
        WHERE id = %s
             AND category IN ('Fee Issue', 'Salary Issue')
    """, (
        complaint_id,
    ))

    complaint = cursor.fetchone()

    if not complaint:

        conn.close()

        return "Fee complaint not found!", 404

    # -----------------------------------------------------
    # UPDATE STATUS + COORDINATOR RESOLUTION
    #
    # 'decision' already exists in your complaints table,
    # so we use it for the Coordinator's resolution.
    # No new database column is required.
    # -----------------------------------------------------
    cursor.execute("""
        UPDATE complaints
        SET
            status = %s,
            decision = %s
        WHERE id = %s
            AND category IN ('Fee Issue', 'Salary Issue')
    """, (
        new_status,
        resolution,
        complaint_id
    ))

    # -----------------------------------------------------
    # NOTIFY STUDENT / TEACHER
    # -----------------------------------------------------
    if complaint.get("user_email"):

        if new_status == "Solved":

            message = (
                f"Your fee complaint #{complaint_id} "
                "has been resolved by the Accounts Coordinator."
            )

        else:

            message = (
                f"Your fee complaint #{complaint_id} "
                "is now In Process with the Accounts Coordinator."
            )

        cursor.execute("""
            INSERT INTO notifications
            (
                user_email,
                complaint_id,
                message,
                is_read,
                created_at
            )
            VALUES (%s, %s, %s, 0, NOW())
        """, (
            complaint["user_email"],
            complaint_id,
            message
        ))

    # -----------------------------------------------------
    # SAVE CHANGES
    # -----------------------------------------------------
    conn.commit()
    conn.close()

    return redirect("/account_coordinator")

# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )

