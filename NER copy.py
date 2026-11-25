import spacy

nlp = spacy.load("en_core_web_sm")

text = input("Enter Complaint: ")

doc = nlp(text)

student_name = ""
teacher_name = ""
department = ""
date = ""
category = ""

for ent in doc.ents:
    if ent.label_ == "PERSON":
        if student_name == "":
            student_name = ent.text
        else:
            teacher_name = ent.text

    elif ent.label_ == "DATE":
        date = ent.text

# Department detection
if "Computer Science Department" in text:
    department = "Computer Science Department"
elif "IT Department" in text:
    department = "IT Department"

# Complaint category detection
if "absent" in text.lower() or "attendance" in text.lower():
    category = "Attendance"
elif "fee" in text.lower():
    category = "Fee Issue"
elif "result" in text.lower():
    category = "Result Issue"
else:
    category = "General Complaint"


print("\n------ Complaint Details ------")
print("Student Name :", student_name)
print("Teacher Name :", teacher_name)
print("Department   :", department)
print("Date         :", date)
print("Category     :", category)