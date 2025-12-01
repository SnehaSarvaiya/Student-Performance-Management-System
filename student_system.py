"""
student_system.py
A simple Student Performance Management System:
- CRUD operations stored in MySQL
- CSV backup/restore
- Statistical analysis with pandas (mean, median, topper list)
- Marks distribution plot with matplotlib
"""

import mysql.connector
from mysql.connector import Error
import pandas as pd
import csv
import os
import statistics
import matplotlib.pyplot as plt
from dataclasses import dataclass, asdict
from typing import Optional, List

# ---------- CONFIG ----------
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': "",
    'database': 'student_db',
    'raise_on_warnings': True
}
CSV_BACKUP = 'students_backup.csv'

# ---------- DATA CLASS ----------
@dataclass
class Student:
    roll_no: str
    name: str
    marks: float
    grade: str

# ---------- DATABASE HANDLER ----------
class Database:
    def __init__(self, config):
        self.config = config
        self.conn = None

    def connect(self):
        try:
            self.conn = mysql.connector.connect(**self.config)
            return True
        except Error as e:
            print(f"❌ Database connection error: {e}")
            return False

    def close(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()

    def execute(self, query, params=None, commit=False, fetch=False):
        if not self.conn or not self.conn.is_connected():
            if not self.connect():
                raise RuntimeError("DB connection failed")
        cursor = self.conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params or ())
            if commit:
                self.conn.commit()
            if fetch:
                return cursor.fetchall()
            return None
        except Error as e:
            raise
        finally:
            cursor.close()

# ---------- STUDENT MANAGER ----------
class StudentManager:
    def __init__(self, db: Database):
        self.db = db

    # Create (Add)
    def add_student(self, student: Student):
        try:
            q = "INSERT INTO students (roll_no, name, marks, grade) VALUES (%s, %s, %s, %s)"
            self.db.execute(q, (student.roll_no, student.name, student.marks, student.grade), commit=True)
            print("✅ Student added.")
        except Error as e:
            print("❌ Error adding student:", e)

    # Read (View all)
    def view_students(self) -> List[dict]:
        try:
            q = "SELECT * FROM students ORDER BY roll_no"
            rows = self.db.execute(q, fetch=True)
            if not rows:
                print("No students found.")
                return []
            df = pd.DataFrame(rows)
            print(df.to_string(index=False))
            return rows
        except Error as e:
            print("❌ Error fetching students:", e)
            return []

    # Read (single)
    def get_student_by_roll(self, roll_no: str) -> Optional[dict]:
        try:
            q = "SELECT * FROM students WHERE roll_no = %s"
            rows = self.db.execute(q, (roll_no,), fetch=True)
            return rows[0] if rows else None
        except Error as e:
            print("❌ Error:", e)
            return None

    # Update
    def update_student(self, roll_no: str, *, name=None, marks=None, grade=None):
        existing = self.get_student_by_roll(roll_no)
        if not existing:
            print("❌ Student not found.")
            return
        # build dynamic update
        updates = []
        params = []
        if name is not None:
            updates.append("name=%s"); params.append(name)
        if marks is not None:
            updates.append("marks=%s"); params.append(marks)
        if grade is not None:
            updates.append("grade=%s"); params.append(grade)
        if not updates:
            print("Nothing to update.")
            return
        params.append(roll_no)
        q = f"UPDATE students SET {', '.join(updates)} WHERE roll_no = %s"
        try:
            self.db.execute(q, tuple(params), commit=True)
            print("✅ Student updated.")
        except Error as e:
            print("❌ Error updating student:", e)

    # Delete
    def delete_student(self, roll_no: str):
        try:
            q = "DELETE FROM students WHERE roll_no = %s"
            self.db.execute(q, (roll_no,), commit=True)
            print("✅ Student deleted (if existed).")
        except Error as e:
            print("❌ Error deleting student:", e)

    # CSV backup
    def backup_to_csv(self, path=CSV_BACKUP):
        rows = self.view_students()
        if not rows:
            print("Nothing to backup.")
            return
        keys = rows[0].keys()
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(rows)
            print(f"✅ Backup saved to {path}")
        except Exception as e:
            print("❌ Backup error:", e)

    # CSV restore (simple replace-inserts skipping duplicates on roll_no)
    def restore_from_csv(self, path=CSV_BACKUP):
        if not os.path.exists(path):
            print("❌ CSV file not found.")
            return
        try:
            df = pd.read_csv(path)
        except Exception as e:
            print("❌ Could not read CSV:", e)
            return
        for _, row in df.iterrows():
            try:
                # Upsert-like: try insert, if duplicate roll_no then update
                q = "INSERT INTO students (roll_no, name, marks, grade) VALUES (%s,%s,%s,%s)"
                self.db.execute(q, (row['roll_no'], row['name'], float(row['marks']), row['grade']), commit=True)
            except Error as e:
                # attempt update on duplicate
                try:
                    q2 = "UPDATE students SET name=%s, marks=%s, grade=%s WHERE roll_no=%s"
                    self.db.execute(q2, (row['name'], float(row['marks']), row['grade'], row['roll_no']), commit=True)
                except Error as e2:
                    print("❌ Error restoring row:", e2)
        print("✅ Restore complete.")

    # Statistics using pandas
    def stats(self):
        rows = self.db.execute("SELECT roll_no, name, marks FROM students", fetch=True)
        if not rows:
            print("No data to compute stats.")
            return
        df = pd.DataFrame(rows)
        # ensure marks numeric
        df['marks'] = pd.to_numeric(df['marks'], errors='coerce')
        mean_val = df['marks'].mean()
        median_val = df['marks'].median()
        std_dev = df['marks'].std()
        # toppers (top 3)
        toppers = df.nlargest(3, 'marks')[['roll_no', 'name', 'marks']]
        print(f"Mean marks: {mean_val:.2f}")
        print(f"Median marks: {median_val:.2f}")
        print(f"Std deviation: {std_dev:.2f}" if not pd.isna(std_dev) else "Std deviation: N/A")
        print("\nTopper(s):")
        print(toppers.to_string(index=False))

        return {
            'mean': mean_val,
            'median': median_val,
            'std': std_dev,
            'toppers': toppers
        }

    # Plot marks distribution
    def plot_marks_distribution(self):
        rows = self.db.execute("SELECT marks FROM students", fetch=True)
        if not rows:
            print("No marks to plot.")
            return
        marks = [r['marks'] for r in rows if r['marks'] is not None]
        if not marks:
            print("No marks to plot.")
            return
        plt.figure(figsize=(8,5))
        plt.hist(marks, bins=10)
        plt.title("Marks Distribution")
        plt.xlabel("Marks")
        plt.ylabel("Number of Students")
        plt.grid(axis='y', alpha=0.75)
        plt.show()

# ---------- INPUT VALIDATION HELPERS ----------
def input_roll():
    r = input("Enter Roll No: ").strip()
    if not r:
        raise ValueError("Roll no cannot be empty.")
    return r

def input_name():
    n = input("Enter Name: ").strip()
    if not n:
        raise ValueError("Name cannot be empty.")
    return n

def input_marks():
    s = input("Enter Marks (0-100): ").strip()
    try:
        m = float(s)
        if m < 0 or m > 100:
            raise ValueError("Marks must be between 0 and 100.")
        return m
    except ValueError:
        raise ValueError("Invalid marks; enter a number between 0 and 100.")

def input_grade():
    g = input("Enter Grade (e.g. A, B+, C): ").strip()
    if not g:
        raise ValueError("Grade cannot be empty.")
    return g

# ---------- CLI ----------
def main_menu(manager: StudentManager):
    while True:
        print("\n--- Student Performance Management ---")
        print("1. Add Student")
        print("2. View All Students")
        print("3. View Student by Roll No")
        print("4. Update Student")
        print("5. Delete Student")
        print("6. Backup to CSV")
        print("7. Restore from CSV")
        print("8. Statistics (mean, median, toppers)")
        print("9. Plot Marks Distribution")
        print("0. Exit")
        choice = input("Choose an option: ").strip()
        try:
            if choice == '1':
                roll = input_roll()
                name = input_name()
                marks = input_marks()
                grade = input_grade()
                student = Student(roll_no=roll, name=name, marks=marks, grade=grade)
                manager.add_student(student)
            elif choice == '2':
                manager.view_students()
            elif choice == '3':
                roll = input_roll()
                s = manager.get_student_by_roll(roll)
                if s:
                    print(pd.DataFrame([s]).to_string(index=False))
                else:
                    print("Not found.")
            elif choice == '4':
                roll = input_roll()
                print("Leave a field blank to skip updating it.")
                name = input("New Name: ").strip() or None
                marks_input = input("New Marks: ").strip()
                marks = None
                if marks_input != '':
                    marks = float(marks_input)  # may raise ValueError
                grade = input("New Grade: ").strip() or None
                manager.update_student(roll, name=name, marks=marks, grade=grade)
            elif choice == '5':
                roll = input_roll()
                confirm = input(f"Type 'yes' to delete student {roll}: ").strip().lower()
                if confirm == 'yes':
                    manager.delete_student(roll)
                else:
                    print("Delete cancelled.")
            elif choice == '6':
                manager.backup_to_csv()
            elif choice == '7':
                manager.restore_from_csv()
            elif choice == '8':
                manager.stats()
            elif choice == '9':
                manager.plot_marks_distribution()
            elif choice == '0':
                print("Exiting...")
                break
            else:
                print("Invalid choice.")
        except ValueError as ve:
            print("❌ Input error:", ve)
        except Exception as e:
            print("❌ Unexpected error:", e)

# ---------- RUN ----------
if __name__ == "__main__":
    db = Database(DB_CONFIG)
    if not db.connect():
        print("Cannot continue without DB. Check DB credentials and server.")
        exit(1)
    manager = StudentManager(db)
    try:
        main_menu(manager)
    finally:
        db.close()
