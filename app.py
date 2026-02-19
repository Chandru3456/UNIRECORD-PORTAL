import os, socket, qrcode, time, img2pdf, shutil
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secure-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure folders exist
for folder in ['uploads', 'static', 'backups', 'instance']:
    os.makedirs(folder, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

DEPARTMENTS = ["Computer Science", "Information Technology", "Mechanical Engineering", 
               "Civil Engineering", "Electronics", "B.Com", "B.Sc", "MBA", "Physics"]

# --- MODELS ---
class Student(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    username = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(50))
    year_start = db.Column(db.String(20))
    year_end = db.Column(db.String(20))
    address = db.Column(db.Text)
    father_name = db.Column(db.String(50))
    mother_name = db.Column(db.String(50))
    phone = db.Column(db.String(15))
    alt_phone = db.Column(db.String(15))
    blood_grp = db.Column(db.String(5))
    password = db.Column(db.String(200), nullable=False)
    documents = db.relationship('Document', backref='owner', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "username": self.username,
            "department": self.department,
            "year_start": self.year_start,
            "year_end": self.year_end,
            "father_name": self.father_name,
            "mother_name": self.mother_name,
            "phone": self.phone,
            "alt_phone": self.alt_phone or "",
            "address": self.address or "",
            "blood_grp": self.blood_grp,
            "documents": [{"id": d.id, "filename": d.filename} for d in self.documents]
        }

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200))
    student_pk = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return Student.query.get(int(user_id))

# --- HELPERS ---
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception: IP = '127.0.0.1'
    finally: s.close()
    return IP

def process_file(file, sid):
    ext = file.filename.split('.')[-1].lower()
    timestamp = int(time.time())
    unique_id = os.urandom(2).hex()
    if ext in ['jpg', 'jpeg', 'png']:
        pdf_name = f"{sid}_{timestamp}_{unique_id}.pdf"
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_name)
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(file.read()))
        return pdf_name
    else:
        fname = f"{sid}_{timestamp}_{unique_id}_{secure_filename(file.filename)}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        return fname

# --- ROUTES ---

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    if current_user.student_id == 'admin':
        return redirect(url_for('admin_panel'))
    return redirect(url_for('view_portal'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Student.query.filter_by(student_id=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            if user.student_id == 'admin':
                return redirect(url_for('admin_panel'))
            return redirect(url_for('view_portal'))
        flash('Invalid Credentials', 'danger')
    return render_template('login.html')

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_panel():
    if current_user.student_id != 'admin': return "Access Denied", 403
    
    if request.method == 'POST':
        spk = request.form.get('student_pk')
        new_pass = request.form.get('new_password')
        
        if spk and new_pass:
            s = Student.query.get(spk)
            s.password = generate_password_hash(new_pass)
            db.session.commit()
            return redirect(url_for('admin_panel'))

        sid = request.form.get('student_id')
        if spk:
            s = Student.query.get(spk)
        else:
            s = Student(student_id=sid, password=generate_password_hash(request.form.get('password', '12345')))
            db.session.add(s)
        
        s.username = request.form.get('username')
        s.department = request.form.get('department')
        s.year_start = request.form.get('year_start')
        s.year_end = request.form.get('year_end')
        s.father_name = request.form.get('father_name')
        s.mother_name = request.form.get('mother_name')
        s.phone = request.form.get('phone')
        s.alt_phone = request.form.get('alt_phone', "")
        s.address = request.form.get('address', "")
        s.blood_grp = request.form.get('blood_grp')

        files = request.files.getlist('documents')
        for file in files:
            if file and file.filename != '':
                fname = process_file(file, sid)
                db.session.add(Document(filename=fname, owner=s))
        
        db.session.commit()
        if not spk:
            qr = qrcode.make(f"http://{get_ip()}:5000/login?id={sid}")
            qr.save(f"static/{sid}_qr.png")
        return redirect(url_for('admin_panel'))

    students = Student.query.filter(Student.student_id != 'admin').all()
    return render_template('admin.html', students=students, departments=DEPARTMENTS)

@app.route('/portal')
@login_required
def view_portal():
    # If admin accidentally goes here, send them back to admin
    if current_user.student_id == 'admin':
        return redirect(url_for('admin_panel'))
    return render_template('viewer.html', student=current_user)

@app.route('/delete_document/<int:doc_id>')
@login_required
def delete_document(doc_id):
    if current_user.student_id != 'admin': return "Forbidden", 403
    doc = Document.query.get(doc_id)
    if doc:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], doc.filename)
        if os.path.exists(file_path): os.remove(file_path)
        db.session.delete(doc)
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/delete/<int:id>')
@login_required
def delete_student(id):
    if current_user.student_id != 'admin': return "Forbidden", 403
    s = Student.query.get(id)
    if s:
        # Delete QR image
        qr_path = f"static/{s.student_id}_qr.png"
        if os.path.exists(qr_path): os.remove(qr_path)
        # Delete all student files
        for doc in s.documents:
            f_path = os.path.join(app.config['UPLOAD_FOLDER'], doc.filename)
            if os.path.exists(f_path): os.remove(f_path)
        db.session.delete(s)
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/uploads/<filename>')
@login_required
def get_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Student.query.filter_by(student_id='admin').first():
            admin_user = Student(
                student_id='admin', 
                username='Super Admin', 
                password=generate_password_hash('admin123')
            )
            db.session.add(admin_user)
            db.session.commit()
    app.run(host='0.0.0.0', port=5000, debug=True)