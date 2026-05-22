from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import hashlib
from functools import wraps
import json
import uuid
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "your_secret_key_here_12345"
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Дозволені формати файлів
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'jfif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    conn = sqlite3.connect('quiz_app.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL,
            questions TEXT NOT NULL,
            author_id INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            quiz_id TEXT NOT NULL,
            quiz_title TEXT NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            percentage REAL NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def home():
    conn = get_db()
    all_quizzes = conn.execute('SELECT * FROM quizzes').fetchall()
    conn.close()
    
    categories = {
        'cars': {'name': '🚘 Марки автомобілів', 'icon': '🚘', 'quizzes': []},
        'countries': {'name': '🌍 Місцевість (Країни)', 'icon': '🌍', 'quizzes': []},
        'rebus': {'name': '🧩 Ребуси', 'icon': '🧩', 'quizzes': []}
    }
    
    for q in all_quizzes:
        quiz_dict = dict(q)
        if quiz_dict.get('questions'):
            quiz_dict['questions'] = json.loads(quiz_dict['questions'])
        else:
            quiz_dict['questions'] = []
        
        category_key = quiz_dict.get('category', '')
        if category_key and category_key in categories:
            categories[category_key]['quizzes'].append(quiz_dict)
    
    return render_template('home.html', categories=categories)

@app.route('/category/<category_name>')
@login_required
def category_view(category_name):
    conn = get_db()
    quizzes = conn.execute('SELECT * FROM quizzes WHERE category = ?', (category_name,)).fetchall()
    conn.close()
    
    categories_names = {
        'cars': '🚘 Марки автомобілів',
        'countries': '🌍 Місцевість (Країни)',
        'rebus': '🧩 Ребуси'
    }
    
    quizzes_list = []
    for q in quizzes:
        quiz_dict = dict(q)
        quiz_dict['questions'] = json.loads(quiz_dict['questions'])
        quizzes_list.append(quiz_dict)
    
    return render_template('category.html', quizzes=quizzes_list, category_title=categories_names.get(category_name, category_name))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE email = ? AND password = ?',
            (email, hashed_password)
        ).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            return redirect(url_for('home'))
        else:
            return "Невірний email або пароль"
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = get_db()
        try:
            conn.execute(
                'INSERT INTO users (email, password) VALUES (?, ?)',
                (email, hashed_password)
            )
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            return "Користувач з таким email вже існує"
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/add_quiz', methods=['GET', 'POST'])
@login_required
def add_quiz():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        
        questions = []
        titles = request.form.getlist('question_title')
        opt1_list = request.form.getlist('opt1')
        opt2_list = request.form.getlist('opt2')
        opt3_list = request.form.getlist('opt3')
        correct_list = request.form.getlist('correct')
        
        # Отримуємо всі картинки
        image_files = request.files.getlist('question_image')
        
        for i in range(len(titles)):
            image_path = None
            if i < len(image_files) and image_files[i] and image_files[i].filename:
                file = image_files[i]
                if allowed_file(file.filename):
                    filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_path = f'/static/uploads/{filename}'
                    print(f"✅ Збережено картинку: {filename}")
                else:
                    print(f"❌ Недозволений формат: {file.filename}")
            
            questions.append({
                'text': titles[i],
                'options': [opt1_list[i], opt2_list[i], opt3_list[i]],
                'correct': correct_list[i],
                'image': image_path
            })
        
        questions_json = json.dumps(questions, ensure_ascii=False)
        quiz_id = str(uuid.uuid4())[:8]
        
        conn = get_db()
        conn.execute(
            'INSERT INTO quizzes (quiz_id, title, description, category, questions, author_id) VALUES (?, ?, ?, ?, ?, ?)',
            (quiz_id, title, description, category, questions_json, session['user_id'])
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for('home'))
    
    return render_template('add_quiz.html')

@app.route('/quiz/<quiz_id>', methods=['GET', 'POST'])
@login_required
def take_quiz(quiz_id):
    conn = get_db()
    quiz = conn.execute('SELECT * FROM quizzes WHERE quiz_id = ?', (quiz_id,)).fetchone()
    conn.close()
    
    if not quiz:
        return "Тест не знайдено"
    
    questions = json.loads(quiz['questions'])
    
    if request.method == 'POST':
        score = 0
        for i, q in enumerate(questions):
            user_answer = request.form.get(f'q{i}')
            if user_answer == q['correct']:
                score += 1
        
        total = len(questions)
        percentage = (score / total) * 100
        
        conn = get_db()
        conn.execute(
            'INSERT INTO results (user_id, quiz_id, quiz_title, score, total, percentage) VALUES (?, ?, ?, ?, ?, ?)',
            (session['user_id'], quiz_id, quiz['title'], score, total, percentage)
        )
        conn.commit()
        conn.close()
        
        return render_template('result.html', result={
            'score': score,
            'total': total,
            'percentage': percentage,
            'quiz_title': quiz['title']
        })
    
    return render_template('quiz.html', quiz={
        'id': quiz['quiz_id'],
        'title': quiz['title'],
        'description': quiz['description'],
        'questions': questions
    })

@app.route('/my_results')
@login_required
def my_results():
    conn = get_db()
    results = conn.execute(
        'SELECT * FROM results WHERE user_id = ? ORDER BY date DESC',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    
    return render_template('my_results.html', results=results)

@app.route('/edit_quiz/<quiz_id>', methods=['GET', 'POST'])
@login_required
def edit_quiz(quiz_id):
    conn = get_db()
    quiz = conn.execute('SELECT * FROM quizzes WHERE quiz_id = ?', (quiz_id,)).fetchone()
    
    if not quiz:
        conn.close()
        return "Тест не знайдено"
    
    if quiz['author_id'] != session['user_id']:
        conn.close()
        return "У вас немає прав для редагування цього тесту"
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        
        questions = []
        titles = request.form.getlist('question_title')
        opt1_list = request.form.getlist('opt1')
        opt2_list = request.form.getlist('opt2')
        opt3_list = request.form.getlist('opt3')
        correct_list = request.form.getlist('correct')
        existing_images = request.form.getlist('existing_image')
        
        for i in range(len(titles)):
            questions.append({
                'text': titles[i],
                'options': [opt1_list[i], opt2_list[i], opt3_list[i]],
                'correct': correct_list[i],
                'image': existing_images[i] if i < len(existing_images) and existing_images[i] else None
            })
        
        questions_json = json.dumps(questions, ensure_ascii=False)
        
        conn.execute(
            'UPDATE quizzes SET title = ?, description = ?, category = ?, questions = ? WHERE quiz_id = ?',
            (title, description, category, questions_json, quiz_id)
        )
        conn.commit()
        conn.close()
        
        return redirect(url_for('home'))
    
    questions = json.loads(quiz['questions'])
    conn.close()
    
    return render_template('edit_quiz.html', quiz={
        'id': quiz['quiz_id'],
        'title': quiz['title'],
        'description': quiz['description'],
        'category': quiz['category'],
        'questions': questions
    })

@app.route('/delete_quiz/<quiz_id>')
@login_required
def delete_quiz(quiz_id):
    conn = get_db()
    quiz = conn.execute('SELECT * FROM quizzes WHERE quiz_id = ?', (quiz_id,)).fetchone()
    if quiz and quiz['author_id'] == session['user_id']:
        conn.execute('DELETE FROM quizzes WHERE quiz_id = ?', (quiz_id,))
        conn.execute('DELETE FROM results WHERE quiz_id = ?', (quiz_id,))
        conn.commit()
    
    conn.close()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)