import mysql.connector

def get_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="ucms"
    )
    return conn
if __name__ == "__main__":
    try:
        db = get_connection()
        print("Database connected successfully")
        db.close()
    except Exception as e:
        print("Error:", e)