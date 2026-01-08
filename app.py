from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
import uuid

app = Flask(__name__, template_folder='static/template')
app.secret_key = 'student_focus_secret_key'

# --- MongoDB Connection ---
# Connects to local MongoDB by default. 
# Replace the string below with your MongoDB Atlas connection string if using cloud.
client = MongoClient('mongodb://localhost:27017/')
db = client.student_todo_db
tasks_collection = db.tasks
subjects_collection = db.subjects
marks_collection = db.marks
notes_collection = db.notes
rewards_collection = db.rewards

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page to capture user name."""
    if request.method == 'POST':
        username = request.form.get('username')
        if username:
            session['username'] = username
            flash('Successfully login')
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    """Show the Student Dashboard."""
    # 1. Fetch Data
    all_tasks = list(tasks_collection.find())
    subjects = list(subjects_collection.find())

    # 2. Date Logic
    today = datetime.now().date()
    next_week = today + timedelta(days=7)

    # 3. Categorize Tasks
    overdue = []
    due_today = []
    upcoming = []
    completed_count = 0

    for task in all_tasks:
        # Ensure defaults for missing fields (prevents Jinja errors on old data)
        task.setdefault('priority', 'medium')
        task.setdefault('color', '#ccc')
        task.setdefault('subject', 'General')

        if task.get('status') == 'completed':
            completed_count += 1
            continue
        
        # Check dates for pending tasks
        if task.get('due_date'):
            try:
                task_date = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
                if task_date < today:
                    overdue.append(task)
                elif task_date == today:
                    due_today.append(task)
                elif today < task_date <= next_week:
                    upcoming.append(task)
            except ValueError:
                upcoming.append(task) # Fallback if date format is wrong
        else:
            upcoming.append(task)

    # 4. Calculate Progress
    total_tasks = len(all_tasks)
    progress = int((completed_count / total_tasks) * 100) if total_tasks > 0 else 0

    # 5. Calculate Score (Stars)
    stars_from_tasks = completed_count * 2
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$stars"}}}]
    result = list(marks_collection.aggregate(pipeline))
    stars_from_marks = result[0]['total'] if result else 0
    total_score = stars_from_tasks + stars_from_marks

    return render_template('index.html', 
                           overdue=overdue, 
                           due_today=due_today, 
                           upcoming=upcoming, 
                           subjects=subjects,
                           progress=progress,
                           completed_count=completed_count,
                           total_score=total_score)

@app.route('/assignments')
def assignments():
    """Show all assignments with management options."""
    tasks = list(tasks_collection.find().sort("due_date", 1))
    subjects = list(subjects_collection.find())
    
    # Separate pending and completed for cleaner view
    pending = [t for t in tasks if t.get('status') != 'completed']
    completed = [t for t in tasks if t.get('status') == 'completed']
    
    return render_template('assignments.html', pending=pending, completed=completed, subjects=subjects)

@app.route('/subjects')
def subjects_page():
    """Show subjects management."""
    subjects = list(subjects_collection.find())
    return render_template('subjects.html', subjects=subjects)

@app.route('/marks')
def marks_page():
    """Show marks and performance."""
    marks = list(marks_collection.find().sort("date", -1))
    subjects = list(subjects_collection.find())
    return render_template('marks.html', marks=marks, subjects=subjects)

@app.route('/notes')
def notes_page():
    """Show study notes."""
    notes = list(notes_collection.find().sort("date", -1))
    return render_template('notes.html', notes=notes)

@app.route('/rewards')
def rewards_page():
    """Show gamification and rewards."""
    # 1. Calculate Stars from Completed Tasks (e.g., 2 stars per task)
    completed_tasks = tasks_collection.count_documents({"status": "completed"})
    stars_from_tasks = completed_tasks * 2
    
    # 2. Calculate Stars from Marks (Sum of stars given in performance)
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$stars"}}}]
    result = list(marks_collection.aggregate(pipeline))
    stars_from_marks = result[0]['total'] if result else 0
    
    total_stars = stars_from_tasks + stars_from_marks
    
    rewards = list(rewards_collection.find())
    return render_template('rewards.html', total_stars=total_stars, rewards=rewards)

@app.route('/puzzle')
def puzzle_page():
    """Show the relaxation puzzle page."""
    return render_template('puzzle.html')

@app.route('/add_mark', methods=['POST'])
def add_mark():
    subject_id = request.form.get('subject')
    score = request.form.get('score')
    total = request.form.get('total')
    remarks = request.form.get('remarks')
    stars = int(request.form.get('stars', 0))
    
    subject_name = "General"
    if subject_id:
        subj = subjects_collection.find_one({"_id": subject_id})
        if subj: subject_name = subj['name']

    marks_collection.insert_one({
        "_id": uuid.uuid4().hex,
        "subject": subject_name,
        "score": score,
        "total": total,
        "remarks": remarks,
        "stars": stars,
        "date": datetime.now()
    })
    return redirect(url_for('marks_page'))

@app.route('/add_note', methods=['POST'])
def add_note():
    title = request.form.get('title')
    content = request.form.get('content')
    
    notes_collection.insert_one({
        "_id": uuid.uuid4().hex,
        "title": title,
        "content": content,
        "date": datetime.now()
    })
    return redirect(url_for('notes_page'))

@app.route('/add_reward', methods=['POST'])
def add_reward():
    name = request.form.get('name')
    cost = int(request.form.get('cost'))
    
    rewards_collection.insert_one({
        "_id": uuid.uuid4().hex,
        "name": name,
        "cost": cost
    })
    return redirect(url_for('rewards_page'))

@app.route('/add', methods=['POST'])
def add_task():
    """Add a new task."""
    title = request.form.get('title')
    description = request.form.get('description')
    due_date = request.form.get('due_date')
    subject_id = request.form.get('subject')
    priority = request.form.get('priority')
    task_type = request.form.get('type')

    # Basic Validation
    if not title or title.strip() == "":
        return redirect(request.referrer or url_for('assignments'))
    
    # Find subject name for display
    subject_name = "General"
    subject_color = "#667eea"
    if subject_id:
        subj = subjects_collection.find_one({"_id": subject_id})
        if subj:
            subject_name = subj['name']
            subject_color = subj['color']

    # Create task object
    new_task = {
        "_id": uuid.uuid4().hex,
        "title": title,
        "description": description,
        "due_date": due_date, # Stored as YYYY-MM-DD string
        "subject": subject_name,
        "color": subject_color,
        "priority": priority, # low, medium, high
        "type": task_type,    # homework, exam, etc
        "status": "pending",  # pending, completed
        "created_at": datetime.now()
    }
    
    tasks_collection.insert_one(new_task)
    return redirect(url_for('assignments'))

@app.route('/add_subject', methods=['POST'])
def add_subject():
    """Add a new subject."""
    name = request.form.get('name')
    color = request.form.get('color')
    
    if name:
        subjects_collection.insert_one({
            "_id": uuid.uuid4().hex,
            "name": name,
            "color": color
        })
    return redirect(url_for('subjects_page'))

@app.route('/complete/<task_id>')
def complete_task(task_id):
    """Toggle task completion status."""
    task = tasks_collection.find_one({"_id": task_id})
    
    if task:
        # Toggle status
        current_status = task.get('status', 'pending')
        new_status = 'completed' if current_status != 'completed' else 'pending'
        
        tasks_collection.update_one(
            {"_id": task_id},
            {"$set": {"status": new_status}}
        )
        
    return redirect(request.referrer or url_for('index'))

@app.route('/delete/<task_id>')
def delete_task(task_id):
    """Delete a task."""
    tasks_collection.delete_one({"_id": task_id})
    return redirect(request.referrer or url_for('index'))

@app.route('/delete_subject/<subject_id>')
def delete_subject(subject_id):
    """Delete a subject."""
    subjects_collection.delete_one({"_id": subject_id})
    return redirect(url_for('subjects_page'))

@app.route('/delete_generic/<collection>/<item_id>')
def delete_generic(collection, item_id):
    """Generic delete for notes, marks, rewards."""
    db[collection].delete_one({"_id": item_id})
    return redirect(request.referrer)

if __name__ == '__main__':
    app.run(debug=True)
