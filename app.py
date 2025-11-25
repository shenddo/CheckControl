from flask import Flask,render_template, session, redirect, url_for, request, flash
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

from datetime import datetime

def format_date(date_obj):
    if date_obj:
        return date_obj.strftime("%d.%m.%Y")
    return "—"
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
    section = db.Column(db.String(100))

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
# ====================== АВТОРИЗАЦИЯ ======================
# Хардкод пользователей (можно потом вынести в БД)
USERS = {
    "pasha": {"password": "Test1234", "role": "admin"},
    "user":  {"password": "user123",  "role": "user"},
    # Добавляй сколько угодно: "ivanov": {"password": "123", "role": "user"},
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user") is None:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user") is None:
            return redirect(url_for('login', next=request.url))
        if session.get("role") != "admin":
            flash("Доступ запрещён", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
# ====================== ГЛАВНАЯ ======================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = USERS.get(username)
        if user and user['password'] == password:
            session['user'] = username
            session['role'] = user['role']
            flash(f"Добро пожаловать, {username}!", "success")
            next_page = request.form.get('next') or url_for('index')
            return redirect(next_page)
        flash("Неверный логин или пароль", "danger")
    return render_template('login.html', next=request.args.get('next'))

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash("Вы вышли из системы", "info")
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    search = request.args.get('search', '').strip()
    position = request.args.get('position', '')
    section_filter = request.args.get('section', '')
    status = request.args.get('status', '')      # overdue / soon

    query = Employee.query
    if search:
        query = query.filter(Employee.full_name.ilike(f'%{search}%'))
    if position:
        query = query.filter(Employee.position == position)
    if section_filter:
        query = query.filter(Employee.section == section_filter)

    employees = query.all()
    today = datetime.today().date()
    data = []
    row_number = 1  # ← нумерация

    # Список всех участков для фильтра
    all_sections = sorted({e.section for e in Employee.query.all() if e.section})

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
            data.append({
                'number': row_number,
                'emp': emp,
                'checks': checks
            })
            row_number += 1

    return render_template('index.html',
                           data=data,
                           search=search,
                           position=position,
                           section_filter=section_filter,
                           status=status,
                           positions=sorted({e.position for e in Employee.query.all()}),
                           sections=all_sections,
                           format_period=format_period,
                           format_date=format_date)

# ====================== УСТАНОВКА ДАТЫ И НОМЕРА ======================
@app.route('/set_date', methods=['POST'])
@login_required
def set_date():
    try:
        emp_id = int(request.form['emp_id'])
        kind = request.form['kind'].strip()
        kind_id = int(request.form['kind_id'])
        date_str = request.form.get('date', '').strip()
        doc_number = request.form.get('doc_number', '').strip() or None
    except:
        flash("Ошибка данных", "danger")
        return redirect(url_for('index'))

    if not date_str:
        EmployeeCheck.query.filter_by(employee_id=emp_id, kind=kind, kind_id=kind_id).delete()
    else:
        new_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        check = EmployeeCheck.query.filter_by(employee_id=emp_id, kind=kind, kind_id=kind_id).first()
        if check:
            check.last_date = new_date
            check.document_number = doc_number
        else:
            check = EmployeeCheck(employee_id=emp_id, kind=kind, kind_id=kind_id,
                                  last_date=new_date, document_number=doc_number)
            db.session.add(check)

    db.session.commit()
    flash("Сохранено!", "success")

    # ← ВОТ ГЛАВНОЕ: возвращаемся к этому сотруднику с открытой карточкой
    return redirect(url_for('index') + f"?open_id={emp_id}#collapse{emp_id}")

# ====================== РЕДАКТИРОВАНИЕ СОТРУДНИКА (без потери дат!) ======================
@app.route('/employee/add', methods=['GET', 'POST'])
@app.route('/employee/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_employee(id=None):
    emp = Employee.query.get(id) if id else None

    if request.method == 'POST':
        full_name = request.form['full_name'].strip()
        position = request.form['position'].strip()
        section = request.form.get('section').strip()
        if not section:
            section = 'Общий'

        if not emp:
            emp = Employee(full_name=full_name, position=position, section=section)
            db.session.add(emp)
            db.session.flush()
            is_new = True
        else:
            emp.full_name = full_name
            emp.position = position
            emp.section = section
            is_new = False

        db.session.flush()

        if is_new:
            pass  # при создании старых связей нет
        else:
            # Удаляем старые связи только при редактировании
            EmployeeTraining.query.filter_by(employee_id=emp.id).delete()
            EmployeeHazard.query.filter_by(employee_id=emp.id).delete()

        # Создаём новые связи
        for tr in TrainingType.query.all():
            period_str = request.form.get(f'training_{tr.id}')
            if period_str and period_str.strip():
                period = int(period_str)
                et = EmployeeTraining(employee_id=emp.id, training_type_id=tr.id, periodicity_months=period)
                db.session.add(et)

        for h_id in request.form.getlist('hazards'):
            h_id = int(h_id)
            hazard = Hazard.query.get(h_id)
            eh = EmployeeHazard(
                employee_id=emp.id,
                hazard_id=h_id,
                periodicity_months=hazard.periodicity_months
            )
            db.session.add(eh)

        db.session.commit()
        flash("Сотрудник сохранён!", "success")
        return redirect(url_for('index'))

    # GET — отображение формы
    trainings = TrainingType.query.all()
    hazards = Hazard.query.all()
    emp_trainings = {et.training_type_id: et.periodicity_months for et in (emp.employee_trainings if emp else [])}
    emp_hazards ={eh.hazard_id for eh in (emp.employee_hazards if emp else [])}

    # ← ВАЖНО: безопасно передаём section
    current_section = emp.section if emp else ''

    return render_template('edit_employee.html',
                           emp=emp,
                           trainings=trainings,
                           hazards=hazards,
                           emp_trainings=emp_trainings,
                           emp_hazards=emp_hazards,
                           current_section=current_section)
# ====================== УДАЛЕНИЕ ======================
@app.route('/delete/<int:id>')
@admin_required
def delete_employee(id):
    emp = Employee.query.get_or_404(id)
    db.session.delete(emp)
    db.session.commit()
    return redirect(url_for('index'))

# ====================== АДМИНКА ВРЕДНОСТЕЙ ======================
@app.route('/admin')
@admin_required
def admin():
    return render_template('admin_hazards.html', hazards=Hazard.query.all())

@app.route('/admin/hazard/add', methods=['GET', 'POST'])
@admin_required
def add_hazard():
    if request.method == 'POST':
        h = Hazard(name=request.form['name'], periodicity_months=int(request.form['period']))
        db.session.add(h)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/hazard/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_hazard(id):
    h = Hazard.query.get_or_404(id)
    if request.method == 'POST':
        old_period = h.periodicity_months
        new_period = int(request.form['period'])
        h.name = request.form['name']
        h.periodicity_months = new_period

        # ← КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: обновляем у всех сотрудников!
        if old_period != new_period:
            EmployeeHazard.query.filter_by(hazard_id=id).update(
                dict(periodicity_months=new_period)
            )

        db.session.commit()
        flash("Вредность обновлена и применена ко всем сотрудникам!", "success")
        return redirect(url_for('admin'))

    return render_template('edit_hazard.html', h=h)

@app.route('/admin/hazard/<int:id>/delete')
@admin_required
def delete_hazard(id):
    h = Hazard.query.get_or_404(id)
    if not EmployeeHazard.query.filter_by(hazard_id=id).first():
        db.session.delete(h)
        db.session.commit()
    return redirect(url_for('admin'))

# ====================== ЗАПУСК ======================
# if __name__ == '__main__':
#     with app.app_context():
#         init_db()
#     app.run(debug=True)
if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='10.6.2.23', port=5000, debug=True)