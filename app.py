from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os, datetime, uuid, qrcode

app = Flask(__name__)

# --- CONFIG ---
app.config['SECRET_KEY'] = 'super-secure-secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///notices.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = "static/uploads"
QR_FOLDER = "static/qrcodes"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "mp4"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["QR_FOLDER"] = QR_FOLDER

db = SQLAlchemy(app)

# --- LOGIN MANAGER SETUP ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'hod', 'coordinator', 'student_rep'
    assigned_class = db.Column(db.Integer, nullable=True)

class Notice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    target_class = db.Column(db.Integer, nullable=False)
    expiry = db.Column(db.String(20), nullable=True)
    image = db.Column(db.String(100), nullable=True)
    pdf = db.Column(db.String(100), nullable=True)
    qr_code = db.Column(db.String(100), nullable=True)
    pinned = db.Column(db.Integer, default=0)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "class": self.target_class,
            "expiry": self.expiry,
            "image": self.image,
            "pdf": self.pdf,
            "qr_code": self.qr_code,
            "pinned": self.pinned
        }

class Broadcast(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_file = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "message": self.message,
            "class": self.target_class, "expiry": self.expiry,
            "image": self.image, "pdf": self.pdf,
            "qr_code": self.qr_code, "pinned": self.pinned
        }

# --- NEW: SECURITY & TRACKING MODELS ---
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    reg_no = db.Column(db.String(50), unique=True, nullable=False)

class NoticeView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    notice_id = db.Column(db.Integer, nullable=False)
    student_id = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# --- DB INITIALIZATION & DEFAULT ACCOUNTS ---
with app.app_context():
    db.create_all()
    # Create default accounts if they don't exist
    if not User.query.first():
        users = [
            User(username="hod", password_hash=generate_password_hash("hod123"), role="hod"),
            User(username="coordinator", password_hash=generate_password_hash("coord123"), role="coordinator"),
            User(username="rep1", password_hash=generate_password_hash("rep123"), role="student_rep", assigned_class=1),
            User(username="rep2", password_hash=generate_password_hash("rep123"), role="student_rep", assigned_class=2),
            User(username="rep3", password_hash=generate_password_hash("rep123"), role="student_rep", assigned_class=3)
        ]
        db.session.bulk_save_objects(users)
        db.session.commit()
        print("✅ Default accounts created!")
    if not Broadcast.query.first():
        db.session.add(Broadcast(is_active=0))
        db.session.commit()

# --- HELPERS ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_upload(upload_file):
    if upload_file and upload_file.filename != "":
        if allowed_file(upload_file.filename):
            ext = upload_file.filename.rsplit(".", 1)[1].lower()
            name = f"{uuid.uuid4().hex}.{ext}"
            upload_file.save(os.path.join(app.config["UPLOAD_FOLDER"], name))
            return name
    return None

def generate_qr(notice_id, base_url):
    qr_file = f"qr_{notice_id}.png"
    qrcode.make(f"{base_url}notice/{notice_id}").save(os.path.join(app.config["QR_FOLDER"], qr_file))
    return qr_file

def delete_file(filename, folder="UPLOAD_FOLDER"):
    if filename:
        path = os.path.join(app.config[folder], filename)
        if os.path.exists(path):
            os.remove(path)

# --- ADMIN AUTH ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if current_user.is_authenticated:
            logout_user()

        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('admin'))
        error = "Invalid username or password"

    else:
        if current_user.is_authenticated:
            return redirect(url_for('admin'))

    return render_template('login.html', error=error)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- NEW: STUDENT AUTH & VERIFICATION ---
@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    # Remember where the student was trying to go before we stopped them
    next_url = request.args.get('next') or url_for('mobile_landing')

    error = None
    if request.method == 'POST':
        name = request.form['name'].strip().lower()
        reg_digits = request.form['reg_digits'].strip()

        # Search the database for this student
        student = Student.query.filter(db.func.lower(Student.name) == name).first()

        # Verify: Did we find the student AND do the last 2 digits match?
        if student and student.reg_no.endswith(reg_digits):
            session['student_id'] = student.id
            session['student_name'] = student.name
            return redirect(next_url)
        else:
            error = "Invalid Name or Registration Digits. Please try again."

    return render_template('student_login.html', error=error)

# --- ADMIN ROUTES WITH RBAC ---
# --- ADMIN ROUTES WITH RBAC ---
@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if request.method == "POST":
        if current_user.role == 'student_rep':
            t_class = current_user.assigned_class
            pinned = 0
        else:
            t_class = int(request.form["class"])
            pinned = 1 if request.form.get("pinned") else 0

        class_notices = Notice.query.filter_by(target_class=t_class).order_by(Notice.id.asc()).all()
        if len(class_notices) >= 3:
            db.session.delete(class_notices[0])

        new_n = Notice(
            title=request.form["title"],
            message=request.form["message"],
            target_class=t_class,
            expiry=request.form.get("expiry") + "T23:59" if request.form.get("expiry") else None,
            pinned=pinned,
            image=save_upload(request.files.get("image")),
            pdf=save_upload(request.files.get("pdf")),
            author_id=current_user.id
        )

        db.session.add(new_n)
        db.session.flush()
        new_n.qr_code = generate_qr(new_n.id, request.url_root)
        db.session.commit()
        return redirect(url_for("admin"))

    # --- NEW: ANALYTICS FETCHING LOGIC ---
    raw_notices = Notice.query.order_by(Notice.pinned.desc(), Notice.id.desc()).all()
    notices = []

    for n in raw_notices:
        n_dict = n.to_dict()

        # 1. Ask the database how many times this specific notice was viewed
        views = NoticeView.query.filter_by(notice_id=n.id).all()
        n_dict['view_count'] = len(views)

        # 2. Get the actual names of the students who viewed it
        viewers = []
        for v in views:
            student = Student.query.get(v.student_id)
            if student:
                # Format it like: "Naveenkumar (34)"
                viewers.append(f"{student.name.title()} ({student.reg_no[-2:]})")

        n_dict['viewers'] = viewers
        notices.append(n_dict)

    return render_template("admin.html", notices=notices, user=current_user, now=datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"))

# --- NEW: STUDENT MANAGEMENT PORTAL ---
@app.route("/manage_students", methods=["GET", "POST"])
@login_required
def manage_students():
    # RBAC: Only HOD and Coordinators can manage the student database
    if current_user.role == 'student_rep':
        return redirect(url_for('admin'))

    if request.method == "POST":
        name = request.form.get("name").strip()
        reg_no = request.form.get("reg_no").strip()

        if name and reg_no:
            # Check if this register number is already in the database
            existing_student = Student.query.filter_by(reg_no=reg_no).first()
            if not existing_student:
                new_student = Student(name=name, reg_no=reg_no)
                db.session.add(new_student)
                db.session.commit()
        return redirect(url_for("manage_students"))

    students = Student.query.order_by(Student.name.asc()).all()
    return render_template("manage_students.html", students=students, user=current_user)

@app.route("/delete_student/<int:student_id>")
@login_required
def delete_student(student_id):
    if current_user.role == 'student_rep':
        return redirect(url_for('admin'))

    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    return redirect(url_for("manage_students"))

@app.route("/edit/<int:notice_id>", methods=["GET", "POST"])
@login_required
def edit_notice(notice_id):
    notice = Notice.query.get_or_404(notice_id)

    if current_user.role == 'student_rep' and notice.author_id != current_user.id:
        return redirect(url_for('admin'))

    if request.method == "POST":
        notice.title = request.form["title"]
        notice.message = request.form["message"]

        if current_user.role != 'student_rep':
            notice.target_class = int(request.form["class"])
            notice.pinned = 1 if request.form.get("pinned") else 0

        expiry_raw = request.form.get("expiry")
        notice.expiry = expiry_raw + "T23:59" if expiry_raw and len(expiry_raw) == 10 else (expiry_raw or notice.expiry)

        if request.form.get("delete_image"):
            delete_file(notice.image)
            notice.image = None
        new_img = save_upload(request.files.get("image"))
        if new_img:
            delete_file(notice.image)
            notice.image = new_img

        if request.form.get("delete_pdf"):
            delete_file(notice.pdf)
            notice.pdf = None
        new_pdf = save_upload(request.files.get("pdf"))
        if new_pdf:
            delete_file(notice.pdf)
            notice.pdf = new_pdf

        db.session.commit()
        return redirect(url_for("admin"))

    return render_template("edit.html", notice=notice.to_dict(), now=datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"), user=current_user)

@app.route("/delete/<int:notice_id>")
@login_required
def delete_notice(notice_id):
    notice = Notice.query.get_or_404(notice_id)

    if current_user.role == 'student_rep' and notice.author_id != current_user.id:
        return redirect(url_for('admin'))

    delete_file(notice.image)
    delete_file(notice.pdf)
    delete_file(notice.qr_code, "QR_FOLDER")

    db.session.delete(notice)
    db.session.commit()
    return redirect(url_for("admin"))

# --- PUBLIC ROUTES & TRACKING LOGIC ---
@app.route("/")
def index():
    notices = [n.to_dict() for n in Notice.query.order_by(Notice.pinned.desc(), Notice.id.desc()).all()]
    return render_template("index.html", notices=notices, now=datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"))

@app.route("/api/notices")
def api_notices():
    return jsonify([n.to_dict() for n in Notice.query.order_by(Notice.pinned.desc(), Notice.id.desc()).all()])

# --- UPDATED: THIS NOW TRACKS THE STUDENT ---
@app.route("/notice/<int:notice_id>")
def notice_detail(notice_id):
    # SECURITY CHECK: Force unverified users to login
    if 'student_id' not in session:
        return redirect(url_for('student_login', next=request.url))

    notice = Notice.query.get_or_404(notice_id)
    student_id = session['student_id']

    # TRACKING LOGIC: Has this student viewed this before?
    existing_view = NoticeView.query.filter_by(notice_id=notice_id, student_id=student_id).first()

    if not existing_view:
        new_view = NoticeView(notice_id=notice_id, student_id=student_id)
        db.session.add(new_view)
        db.session.commit()

    return render_template("notice_detail.html", notice=notice.to_dict())

@app.route("/mobile")
def mobile_landing():
    notices = [n.to_dict() for n in Notice.query.order_by(Notice.pinned.desc(), Notice.id.desc()).all()]
    return render_template("mobile.html", notices=notices, now=datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"))

@app.route("/api/broadcast")
def api_broadcast():
    b = Broadcast.query.first()
    if b and b.is_active and b.video_file:
        return jsonify({"active": True, "video": url_for('static', filename='uploads/' + b.video_file)})
    return jsonify({"active": False})

@app.route("/toggle_broadcast", methods=["POST"])
@login_required
def toggle_broadcast():
    if current_user.role == 'student_rep':
        return redirect(url_for('admin'))

    b = Broadcast.query.first()
    action = request.form.get("action")

    if action == "start":
        video = request.files.get("video")
        if video and allowed_file(video.filename):
            b.video_file = save_upload(video)
            b.is_active = 1
    elif action == "stop":
        b.is_active = 0

    db.session.commit()
    return redirect(url_for('admin'))

if __name__ == "__main__":
    app.run(debug=True)