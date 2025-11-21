from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ====================== МОДЕЛИ ======================
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100), nullable=False)

    employee_hazards = db.relationship('EmployeeHazard', backref='employee', lazy=True, cascade="all, delete-orphan")
    employee_trainings = db.relationship('EmployeeTraining', backref='employee', lazy=True, cascade="all, delete-orphan")

class Hazard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    periodicity_months = db.Column(db.Integer, default=12)

    employee_hazards = db.relationship('EmployeeHazard', backref='hazard', lazy=True)

class TrainingType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    default_periodicity = db.Column(db.Integer, default=12)

    employee_trainings = db.relationship('EmployeeTraining', backref='training_type', lazy=True)

class EmployeeHazard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    hazard_id = db.Column(db.Integer, db.ForeignKey('hazard.id'), nullable=False)
    periodicity_months = db.Column(db.Integer, nullable=False)

class EmployeeTraining(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    training_type_id = db.Column(db.Integer, db.ForeignKey('training_type.id'), nullable=False)
    periodicity_months = db.Column(db.Integer, nullable=False)

class EmployeeCheck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    kind_id = db.Column(db.Integer, nullable=False)
    last_date = db.Column(db.Date)
    document_number = db.Column(db.String(50))  # ← НОВОЕ ПОЛЕ

# ====================== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ======================
def format_period(months):
    if months % 12 == 0:
        years = months // 12
        if years == 1:
            return "1 год"
        elif 2 <= years <= 4:
            return f"{years} года"
        else:
            return f"{years} лет"
    else:
        return f"{months} мес."

# ====================== ИНИЦИАЛИЗАЦИЯ ======================
def init_db():
    db.create_all()
    if TrainingType.query.first() is None:
        trainings = [
            TrainingType(name="Охрана труда", default_periodicity=36),
            TrainingType(name="Электробезопасность", default_periodicity=12),
            TrainingType(name="Промышленная безопасность", default_periodicity=12),
        ]
        db.session.bulk_save_objects(trainings)

    if Hazard.query.first() is None:
        hazards = [
            Hazard(name="Шум и вибрация", periodicity_months=12),
            Hazard(name="Химические вещества", periodicity_months=12),
            Hazard(name="Работа на высоте", periodicity_months=12),
            Hazard(name="Пыль", periodicity_months=12),
            Hazard(name="Биологические факторы", periodicity_months=24),
        ]
        db.session.bulk_save_objects(hazards)
        db.session.commit()

# ====================== ГЛАВНАЯ ======================
@app.route('/')
def index():
    search = request.args.get('search', '').strip()
    position = request.args.get('position', '')
    status = request.args.get('status', '')      # overdue / soon

    query = Employee.query
    if search:
        query = query.filter(Employee.full_name.ilike(f'%{search}%'))
    if position:
        query = query.filter(Employee.position == position)

    employees = query.all()
    today = datetime.today().date()
    data = []
    positions = sorted({e.position for e in Employee.query.all() if e.position})

    for emp in employees:
        checks = []
        show_employee = False

        # Обучения
        for et in emp.employee_trainings:
            tr = et.training_type
            ec = EmployeeCheck.query.filter_by(employee_id=emp.id, kind='training', kind_id=et.id).first()
            last = ec.last_date if ec else None
            doc = ec.document_number if ec else None
            next_d = last + timedelta(days=et.periodicity_months * 30) if last else None
            st = "never" if not last else ("overdue" if next_d <= today else "soon" if next_d <= today + timedelta(days=30) else "ok")
            if status and st not in [status, 'never']:
                continue
            show_employee = True
            checks.append({
                'name': tr.name, 'category': 'Обучение', 'period': et.periodicity_months,
                'last': last, 'next': next_d, 'doc': doc, 'status': st,
                'kind': 'training', 'kind_id': et.id
            })

        # Вредности
        for eh in emp.employee_hazards:
            h = eh.hazard
            ec = EmployeeCheck.query.filter_by(employee_id=emp.id, kind='hazard', kind_id=eh.id).first()
            last = ec.last_date if ec else None
            doc = ec.document_number if ec else None
            next_d = last + timedelta(days=eh.periodicity_months * 30) if last else None
            st = "never" if not last else ("overdue" if next_d <= today else "soon" if next_d <= today + timedelta(days=30) else "ok")
            if status and st not in [status, 'never']:
                continue
            show_employee = True
            checks.append({
                'name': f"Медосмотр: {h.name}", 'category': 'Медосмотр', 'period': eh.periodicity_months,
                'last': last, 'next': next_d, 'doc': doc, 'status': st,
                'kind': 'hazard', 'kind_id': eh.id
            })

        if show_employee or not status:
            data.append({'emp': emp, 'checks': checks})

    return render_template('index.html', data=data, search=search, position=position,
                           status=status, positions=positions, format_period=format_period)

# ====================== УСТАНОВКА ДАТЫ И НОМЕРА ======================
@app.route('/set_date', methods=['POST'])
def set_date():
    emp_id = int(request.form['emp_id'])
    kind = request.form['kind']
    kind_id = int(request.form['kind_id'])
    date_str = request.form.get('date', '').strip()
    doc_num = request.form.get('doc_number', '').strip() or None

    ec = EmployeeCheck.query.filter_by(employee_id=emp_id, kind=kind, kind_id=kind_id).first()

    if date_str:
        new_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if ec:
            ec.last_date = new_date
            ec.document_number = doc_num
        else:
            ec = EmployeeCheck(employee_id=emp_id, kind=kind, kind_id=kind_id,
                               last_date=new_date, document_number=doc_num)
            db.session.add(ec)
    else:
        if ec:
            db.session.delete(ec)

    db.session.commit()
    ref = request.referrer or url_for('index')
    return redirect(ref)

# ====================== РЕДАКТИРОВАНИЕ СОТРУДНИКА (без потери дат!) ======================
@app.route('/employee/add', methods=['GET', 'POST'])
@app.route('/employee/<int:id>', methods=['GET', 'POST'])
def edit_employee(id=None):
    emp = Employee.query.get(id) if id else None

    if request.method == 'POST':
        full_name = request.form['full_name']
        position = request.form['position']

        if not emp:
            emp = Employee(full_name=full_name, position=position)
            db.session.add(emp)
            db.session.flush()
            create_new = True
        else:
            emp.full_name = full_name
            emp.position = position
            create_new = False

        if create_new:
            # Только при создании нового сотрудника создаём связи
            for tr in TrainingType.query.all():
                period = int(request.form.get(f'training_{tr.id}', tr.default_periodicity))
                et = EmployeeTraining(employee_id=emp.id, training_type_id=tr.id, periodicity_months=period)
                db.session.add(et)

            for h_id in request.form.getlist('hazards'):
                h = Hazard.query.get(int(h_id))
                eh = EmployeeHazard(employee_id=emp.id, hazard_id=h.id, periodicity_months=h.periodicity_months)
                db.session.add(eh)

        db.session.commit()
        return redirect(url_for('index'))

    trainings = TrainingType.query.all()
    hazards = Hazard.query.all()
    emp_trainings = {et.training_type_id: et.periodicity_months for et in (emp.employee_trainings if emp else [])}
    emp_hazards = [eh.hazard_id for eh in (emp.employee_hazards if emp else [])]

    return render_template('edit_employee.html', emp=emp, trainings=trainings, hazards=hazards,
                           emp_trainings=emp_trainings, emp_hazards=emp_hazards, format_period=format_period)

# ====================== УДАЛЕНИЕ ======================
@app.route('/delete/<int:id>')
def delete_employee(id):
    emp = Employee.query.get_or_404(id)
    db.session.delete(emp)
    db.session.commit()
    return redirect(url_for('index'))

# ====================== АДМИНКА ВРЕДНОСТЕЙ ======================
@app.route('/admin')
def admin():
    return render_template('admin_hazards.html', hazards=Hazard.query.all())

@app.route('/admin/hazard/add', methods=['GET', 'POST'])
def add_hazard():
    if request.method == 'POST':
        h = Hazard(name=request.form['name'], periodicity_months=int(request.form['period']))
        db.session.add(h)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/hazard/<int:id>/edit', methods=['GET', 'POST'])
def edit_hazard(id):
    h = Hazard.query.get_or_404(id)
    if request.method == 'POST':
        h.name = request.form['name']
        h.periodicity_months = int(request.form['period'])
        db.session.commit()
        return redirect(url_for('admin'))
    return render_template('edit_hazard.html', h=h)

@app.route('/admin/hazard/<int:id>/delete')
def delete_hazard(id):
    h = Hazard.query.get_or_404(id)
    if not EmployeeHazard.query.filter_by(hazard_id=id).first():
        db.session.delete(h)
        db.session.commit()
    return redirect(url_for('admin'))

# ====================== ЗАПУСК ======================
if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)