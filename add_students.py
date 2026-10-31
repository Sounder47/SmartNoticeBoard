# Run this script ONCE to populate your database with students
from app import app, db, Student

def seed_students():
    with app.app_context():
        # List of students (Name, Registration Number)
        students_data = [
            {"name": "Naveenkumar", "reg_no": "510522106034"},
            {"name": "Raguraman", "reg_no": "510522106042"},
            {"name": "Sounderyarajan", "reg_no": "510522106053"},
            {"name": "Hariharan", "reg_no": "510522106301"}
        ]

        for data in students_data:
            # Check if student already exists to prevent duplicates
            if not Student.query.filter_by(reg_no=data['reg_no']).first():
                new_student = Student(name=data['name'], reg_no=data['reg_no'])
                db.session.add(new_student)
        
        db.session.commit()
        print("✅ Students successfully added to the secure database!")

if __name__ == '__main__':
    seed_students()