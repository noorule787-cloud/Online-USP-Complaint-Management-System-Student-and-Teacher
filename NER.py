import spacy
import re

nlp = spacy.load("en_core_web_sm")


def extract_entities(text, complaint_by="Student"):

    doc = nlp(text)

    student_name = ""
    teacher_name = ""
    target_name = ""
    target_role = ""

    text_lower = text.lower()

    # =================================
    # PERSON WHO SUBMITTED COMPLAINT
    # =================================

    my_name_match = re.search(
        r"(?:my name is|i am|i'm|this is)\s+"
        r"([A-Za-z]+(?:\s+[A-Za-z]+){0,1})"
        r"(?=\s*[.,!?]|\s+i am\b|\s+i'm\b|\s+i belong\b|"
        r"\s+i have\b|\s+i want\b|\s+student\b|\s+teacher\b|"
        r"\s+from\b|\s+of\b|$)",
        text,
        re.IGNORECASE
    )

    if my_name_match:

        submitter_name = (
            my_name_match.group(1)
            .strip()
            .title()
        )

        if complaint_by.lower() == "teacher":
            teacher_name = submitter_name
        else:
            student_name = submitter_name

    # =================================
    # TARGET PROGRAM HEAD
    # =================================
    #
    # Detects complaints such as:
    #
    # complaint against Program Head
    # complaint against the Program Head
    # Program Head is not responding
    # Program Head treated me unfairly
    # I want to complain about Program Head
    # I want to report the Program Head
    #

    program_head_match = re.search(
        r"(?:against|about|regarding|complain\s+about|"
        r"complaint\s+against|report)\s+"
        r"(?:the\s+)?program\s+head"
        r"|"
        r"(?:the\s+)?program\s+head\s+"
        r"(?:is|was|has|have|had|"
        r"treated|treats|"
        r"harass|harassed|harassing|"
        r"ignored|ignores|"
        r"refused|reject|rejected|"
        r"misbehaved|misbehaving|"
        r"unfair|unfairly|"
        r"not\s+responding|"
        r"not\s+helping|"
        r"not\s+cooperating)",
        text,
        re.IGNORECASE
    )

    if program_head_match:

        target_name = "Program Head"
        target_role = "Program Head"

    # =================================
    # TARGET TEACHER
    # =================================
    #
    # Handles:
    # teacher Hina
    # teacher Hina Malik
    # against Teacher Hina Malik
    # Teacher Hina Malik harassing me
    # Teacher Hina Malik is harassing me
    #

    if not target_name:

        teacher_match = re.search(
            r"(?:against\s+)?"
            r"(?:teacher|professor|prof|sir|madam|ma'am|mam)"
            r"\s+"
            r"([A-Za-z]+(?:\s+[A-Za-z]+){0,1})"
            r"(?=\s+(?:is|was|has|have|had|"
            r"harass|harassed|harassing|"
            r"treated|treats|unfairly|me|my|"
            r"for|about|because|regarding|"
            r"and|but|in|on|at|"
            r"she|he|they)\b|[.,!?]|$)",
            text,
            re.IGNORECASE
        )

        if teacher_match:

            possible_teacher = (
                teacher_match.group(1)
                .strip()
                .title()
            )

            # Do not use complainant's own name
            if possible_teacher.lower() != student_name.lower():

                teacher_name = possible_teacher
                target_name = possible_teacher
                target_role = "Teacher"

    # =================================
    # TARGET STUDENT
    # =================================

    if not target_name:

        student_match = re.search(
            r"(?:against\s+)?"
            r"student\s+"
            r"([A-Za-z]+(?:\s+[A-Za-z]+){0,1})"
            r"(?=\s+(?:is|was|has|have|had|"
            r"harass|harassed|harassing|"
            r"treated|treats|unfairly|me|my|"
            r"for|about|because|regarding|"
            r"and|but|in|on|at)\b|[.,!?]|$)",
            text,
            re.IGNORECASE
        )

        if student_match:

            possible_student = (
                student_match.group(1)
                .strip()
                .title()
            )

            if possible_student.lower() != student_name.lower():

                target_name = possible_student
                target_role = "Student"

    # =================================
    # TEACHER COMPLAINT
    # FIND STUDENT
    # =================================

    if complaint_by.lower() == "teacher":

        student_match = re.search(
            r"(?:against\s+)?student\s+"
            r"([A-Za-z]+(?:\s+[A-Za-z]+){0,1})"
            r"(?=\s+(?:is|was|has|have|had|"
            r"harass|harassed|harassing|"
            r"treated|treats|unfairly|me|my|"
            r"for|about|because|regarding|"
            r"and|but|in|on|at)\b|[.,!?]|$)",
            text,
            re.IGNORECASE
        )

        if student_match:

            found_student = (
                student_match.group(1)
                .strip()
                .title()
            )

            if not student_name:
                student_name = found_student


    # =================================
    # DEPARTMENT
    # =================================

    department = ""

    if (
        "cyber security" in text_lower
        or "cybersecurity" in text_lower
        or "cyber-security" in text_lower
    ):

        department = "Cyber Security Department"

    elif (
        "computer science" in text_lower
        or "cs department" in text_lower
        or "bscs" in text_lower
    ):

        department = "Computer Science Department"

    elif (
        "it department" in text_lower
        or "information technology" in text_lower
        or "bsit" in text_lower
    ):

        department = "IT Department"

    elif (
        "artificial intelligence" in text_lower
        or "ai department" in text_lower
        or "bsai" in text_lower
    ):

        department = "AI"

    elif (
        "software engineering" in text_lower
        or "software engineering department" in text_lower
    ):

        department = "Software Engineering Department"

    elif (
        "data sciences" in text_lower
        or "data science" in text_lower
    ):

        department = "Data Sciences Department"

    elif (
        "adc department" in text_lower
        or "adc program" in text_lower
        or "adc" in text_lower
    ):

        department = "ADC Department"

    # =================================
    # DATE
    # =================================

    date = ""

    date_match = re.search(
        r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b",
        text,
        re.IGNORECASE
    )

    if date_match:

        date = date_match.group(1)

    else:

        for ent in doc.ents:

            if ent.label_ == "DATE":

                date = ent.text
                break

    # =================================
    # COMPLAINT CATEGORY
    # =================================

    if (
        "harass" in text_lower
        or "harassment" in text_lower
        or "harassing" in text_lower
        or "bully" in text_lower
        or "bullying" in text_lower
        or "threaten" in text_lower
        or "threatening" in text_lower
        or "stalk" in text_lower
        or "stalking" in text_lower
    ):

        category = "Harassment"
    elif (
        "salary" in text_lower
        or "salaries" in text_lower
        or "payroll" in text_lower
        or "unpaid salary" in text_lower
        or "salary delay" in text_lower
        or "salary delayed" in text_lower
        or "salary not received" in text_lower
        or "salary deduction" in text_lower
        or "salary deducted" in text_lower
    ):

        category = "Salary Issue"
    
    elif (
        "academic" in text_lower
        or "assignment" in text_lower
        or "exam" in text_lower
        or "examination" in text_lower
        or "course" in text_lower
        or "class" in text_lower
        or "lecture" in text_lower
        or "study" in text_lower
        or "teacher" in text_lower
        or "marks" in text_lower
    ):

        category = "Academic"

    elif (
        "absent" in text_lower
        or "attendance" in text_lower
    ):

        category = "Attendance"

    elif (
        "fee" in text_lower
        or "fees" in text_lower
    ):

        category = "Fee Issue"

    elif "result" in text_lower:

        category = "Result Issue"

    elif "hostel" in text_lower:

        category = "Hostel Issue"

    else:

        category = "General Complaint"

    # =================================
    # RETURN
    # =================================

    return {
        "student_name": student_name,
        "teacher_name": teacher_name,
        "target_name": target_name,
        "target_role": target_role,
        "department": department,
        "date": date,
        "category": category
    }


# =================================
# TEST
# =================================

if __name__ == "__main__":

    complaint_by = input(
        "Complaint By (Student/Teacher): "
    )

    text = input(
        "Enter Complaint: "
    )

    result = extract_entities(
        text,
        complaint_by
    )

    print("\n------ Complaint Details ------")

    print("Student Name :", result["student_name"])
    print("Teacher Name :", result["teacher_name"])
    print("Target Name  :", result["target_name"])
    print("Target Role  :", result["target_role"])
    print("Department   :", result["department"])
    print("Date         :", result["date"])
    print("Category     :", result["category"])