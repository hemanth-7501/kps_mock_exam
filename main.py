from fastapi import FastAPI, Form, Request, UploadFile, File, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import csv
import io
import os
import json
import math
import time
import random
from datetime import datetime, timedelta
import sqlite3

app = FastAPI(title="KSP Police Constable Mock Exam")
app.mount("/static", StaticFiles(directory="."), name="static")

QUESTIONS = []
SUBMISSIONS = []
EXAM_CONFIG = {"total_questions": 100, "time_limit": 90, "is_live": True}
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "kspadmin123"
QUESTION_PAPER_FILENAME = None

# Build a rich question bank with 100 realistic mock questions.
SUBJECTS = ["General Knowledge", "Law", "Reasoning", "Current Affairs", "Constitution", "History", "Science", "Geography"]

BASE_QUESTIONS = [
    {
        "subject": "General Knowledge",
        "question": "What is the capital of Kerala?",
        "options": ["Thiruvananthapuram", "Kochi", "Kozhikode", "Kannur"],
        "answer": "A",
        "explanation": "Thiruvananthapuram is the capital city of Kerala."
    },
    {
        "subject": "Law",
        "question": "Which article of the Indian Constitution provides for the Right to Equality?",
        "options": ["Article 14", "Article 19", "Article 21", "Article 32"],
        "answer": "A",
        "explanation": "Article 14 guarantees equality before the law and equal protection of laws."
    },
    {
        "subject": "Reasoning",
        "question": "Find the odd one out: 2, 4, 8, 16, 31",
        "options": ["2", "4", "8", "31"],
        "answer": "D",
        "explanation": "31 is not a power of 2, unlike the others."
    },
    {
        "subject": "Current Affairs",
        "question": "Who is the current President of India?",
        "options": ["Narendra Modi", "Droupadi Murmu", "Amit Shah", "Rajnath Singh"],
        "answer": "B",
        "explanation": "Droupadi Murmu is the President of India."
    },
    {
        "subject": "Constitution",
        "question": "Who is the ex-officio Chairman of the Rajya Sabha?",
        "options": ["Prime Minister", "Vice President", "Speaker", "Chief Justice"],
        "answer": "B",
        "explanation": "The Vice President of India is the ex-officio Chairman of the Rajya Sabha."
    },
    {
        "subject": "History",
        "question": "Who founded the Maurya Empire?",
        "options": ["Ashoka", "Chandragupta Maurya", "Bindusara", "Harsha"],
        "answer": "B",
        "explanation": "Chandragupta Maurya founded the Maurya Empire."
    },
    {
        "subject": "Science",
        "question": "What is the chemical symbol for gold?",
        "options": ["Go", "Gd", "Au", "Ag"],
        "answer": "C",
        "explanation": "The chemical symbol for gold is Au."
    },
    {
        "subject": "Geography",
        "question": "Which is the longest river in India?",
        "options": ["Godavari", "Narmada", "Ganga", "Brahmaputra"],
        "answer": "C",
        "explanation": "The Ganga is commonly regarded as the longest river in India."
    },
]

# Expand to 100 questions using variations and realistic content.
for i in range(1, 101):
    base = BASE_QUESTIONS[(i - 1) % len(BASE_QUESTIONS)]
    q = {
        "id": i,
        "subject": base["subject"],
        "question": f"{base['question']} (Practice Question {i})",
        "options": base["options"],
        "answer": base["answer"],
        "explanation": f"{base['explanation']} This is a practice item for KSP mock preparation."
    }
    QUESTIONS.append(q)

ADMIN_CREDENTIALS = {"admin": "kspadmin123"}
AUTH_COOKIE = "exam_user"
DB_PATH = os.path.join(os.getcwd(), "data.db")


def get_db_conn():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  conn = get_db_conn()
  cur = conn.cursor()
  cur.execute("""
  CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY,
    username TEXT,
    date TEXT,
    started_at TEXT,
    score REAL,
    percent REAL,
    correct INTEGER,
    incorrect INTEGER,
    unattempted INTEGER,
    total_questions INTEGER,
    answers TEXT,
    status TEXT,
    graded INTEGER
  )
  """)
  cur.execute("""
  CREATE TABLE IF NOT EXISTS students (
    username TEXT PRIMARY KEY,
    password TEXT
  )
  """)
  conn.commit()
  conn.close()


def load_students_from_db():
  if not os.path.exists(DB_PATH):
    return {}
  conn = get_db_conn()
  cur = conn.cursor()
  cur.execute("SELECT username, password FROM students")
  rows = cur.fetchall()
  students = {row["username"]: row["password"] for row in rows}
  conn.close()
  return students


def save_student_to_db(username: str, password: str):
  conn = get_db_conn()
  cur = conn.cursor()
  cur.execute("INSERT OR REPLACE INTO students (username, password) VALUES (?, ?)", (username, password))
  conn.commit()
  conn.close()


def verify_student_credentials(username: str, password: str) -> bool:
  conn = get_db_conn()
  cur = conn.cursor()
  cur.execute("SELECT password FROM students WHERE username = ?", (username,))
  row = cur.fetchone()
  conn.close()
  return bool(row and row["password"] == password)


def student_exists(username: str) -> bool:
  conn = get_db_conn()
  cur = conn.cursor()
  cur.execute("SELECT 1 FROM students WHERE username = ?", (username,))
  exists = cur.fetchone() is not None
  conn.close()
  return exists


def load_submissions_from_db():
  if not os.path.exists(DB_PATH):
    return []
  conn = get_db_conn()
  cur = conn.cursor()
  cur.execute("SELECT * FROM submissions ORDER BY id ASC")
  rows = cur.fetchall()
  results = []
  for r in rows:
    results.append({
      "id": r["id"],
      "username": r["username"],
      "date": r["date"],
      "started_at": r["started_at"],
      "score": r["score"],
      "percent": r["percent"],
      "correct": r["correct"],
      "incorrect": r["incorrect"],
      "unattempted": r["unattempted"],
      "total_questions": r["total_questions"],
      "answers": r["answers"],
      "status": r["status"],
      "graded": bool(r["graded"])
    })
  conn.close()
  return results


def save_submission_to_db(submission: dict):
  conn = get_db_conn()
  cur = conn.cursor()
  cur.execute("""
  INSERT OR REPLACE INTO submissions (id, username, date, started_at, score, percent, correct, incorrect, unattempted, total_questions, answers, status, graded)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  """, (
    submission.get("id"),
    submission.get("username"),
    submission.get("date"),
    submission.get("started_at"),
    submission.get("score"),
    submission.get("percent"),
    submission.get("correct"),
    submission.get("incorrect"),
    submission.get("unattempted"),
    submission.get("total_questions"),
    submission.get("answers"),
    submission.get("status"),
    1 if submission.get("graded") else 0
  ))
  conn.commit()
  conn.close()


def update_submission_in_db(submission: dict):
  # same as save (INSERT OR REPLACE handles it)
  save_submission_to_db(submission)


# Initialize DB and load existing submissions into memory
init_db()
if not student_exists("student"):
  save_student_to_db("student", "kspstudent123")
loaded = load_submissions_from_db()
if loaded:
  SUBMISSIONS.extend(loaded)

def get_current_user(request: Request) -> Optional[str]:
    return request.cookies.get(AUTH_COOKIE)


def require_admin(request: Request):
    if get_current_user(request) != "admin":
        return HTMLResponse("<h2>Access denied</h2><p><a href='/'>Go home</a></p>", status_code=403)
    return None

class Submission(BaseModel):
    answers: List[Optional[str]]
    started_at: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>KSP Police Constable Mock Exam</title>
      <script src="https://cdn.tailwindcss.com"></script>
      <style>
        body { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
      </style>
    </head>
    <body class="min-h-screen bg-slate-50 text-slate-800">
      <div class="max-w-7xl mx-auto px-4 py-8">
        <div class="bg-white rounded-3xl shadow-sm border border-slate-200 p-8 mb-6">
          <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <p class="text-sm font-semibold uppercase tracking-[0.3em] text-sky-600">KSP Mock Examination</p>
              <h1 class="text-3xl font-bold mt-2">Police Constable Mock Exam Portal</h1>
              <p class="text-slate-600 mt-2">Login as student or admin to begin the practice session.</p>
            </div>
            <div class="rounded-2xl bg-slate-50 p-4 min-w-[220px]">
              <p class="text-sm text-slate-500">Exam Duration</p>
              <p class="text-2xl font-semibold">90 Minutes</p>
            </div>
          </div>
        </div>

        <div class="grid md:grid-cols-2 gap-6">
          <div class="bg-white rounded-3xl shadow-sm border border-slate-200 p-6">
            <h2 class="text-xl font-semibold mb-4">Student Login</h2>
            <form action="/student-login" method="post" class="space-y-3">
              <input name="username" placeholder="Enter username" class="w-full border rounded-xl px-3 py-2" required />
              <input name="password" type="password" placeholder="Enter password" class="w-full border rounded-xl px-3 py-2" required />
              <button class="w-full bg-sky-600 hover:bg-sky-700 text-white py-2 rounded-xl">Enter Exam</button>
            </form>
            <p class="text-sm text-slate-500 mt-3">No account yet? <a href="/register" class="text-sky-600 font-semibold">Register as a student</a></p>
          </div>
          <div class="bg-white rounded-3xl shadow-sm border border-slate-200 p-6">
            <h2 class="text-xl font-semibold mb-4">Admin Login</h2>
            <form action="/admin-login" method="post" class="space-y-3">
              <input name="username" placeholder="Enter admin username" class="w-full border rounded-xl px-3 py-2" required />
              <input name="password" type="password" placeholder="Enter admin password" class="w-full border rounded-xl px-3 py-2" required />
              <button class="w-full bg-slate-800 hover:bg-slate-900 text-white py-2 rounded-xl">Open Admin Panel</button>
            </form>
          </div>
        </div>
      </div>
    </body>
    </html>
    """)


@app.get("/register", response_class=HTMLResponse)
def register_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Student Registration</title>
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="min-h-screen bg-slate-50 text-slate-800">
      <div class="max-w-xl mx-auto px-4 py-10">
        <div class="bg-white rounded-3xl border border-slate-200 p-8 shadow-sm">
          <h1 class="text-2xl font-bold">Create Student Account</h1>
          <p class="text-slate-600 mt-2">Register to access the mock exam portal.</p>
          <form action="/register" method="post" class="mt-6 space-y-3">
            <input name="username" placeholder="Choose username" class="w-full border rounded-xl px-3 py-2" required />
            <input name="password" type="password" placeholder="Choose password" class="w-full border rounded-xl px-3 py-2" required />
            <input name="confirm_password" type="password" placeholder="Confirm password" class="w-full border rounded-xl px-3 py-2" required />
            <button class="w-full bg-sky-600 hover:bg-sky-700 text-white py-2 rounded-xl">Register</button>
          </form>
        </div>
      </div>
    </body>
    </html>
    """)


@app.post("/register")
def register_student(username: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)):
    if not username or not password:
        return HTMLResponse("<h2>Username and password are required</h2>", status_code=400)
    if password != confirm_password:
        return HTMLResponse("<h2>Passwords do not match</h2>", status_code=400)
    if student_exists(username):
        return HTMLResponse("<h2>Username already exists</h2>", status_code=400)
    save_student_to_db(username, password)
    response = RedirectResponse(url="/exam", status_code=303)
    response.set_cookie(key=AUTH_COOKIE, value=username, httponly=True)
    return response


@app.post("/student-login")
def student_login(username: str = Form(...), password: str = Form(...)):
    if verify_student_credentials(username, password):
        response = RedirectResponse(url="/exam", status_code=303)
        response.set_cookie(key=AUTH_COOKIE, value=username, httponly=True)
        return response
    return HTMLResponse("<h2>Invalid student credentials</h2>", status_code=401)


@app.post("/admin-login")
def admin_login(username: str = Form(...), password: str = Form(...)):
    if username == "admin" and password == ADMIN_CREDENTIALS["admin"]:
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie(key=AUTH_COOKIE, value="admin", httponly=True)
        return response
    return HTMLResponse("<h2>Invalid admin credentials</h2>", status_code=401)


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(AUTH_COOKIE)
    return response


@app.get("/exam", response_class=HTMLResponse)
def exam_page(request: Request):
    current_user = get_current_user(request)
    if not current_user or current_user == "admin":
        return RedirectResponse(url="/", status_code=303)
    if not EXAM_CONFIG["is_live"]:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>Exam Unavailable</title>
          <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="min-h-screen bg-slate-50 text-slate-800 flex items-center justify-center">
          <div class="bg-white rounded-3xl border border-slate-200 p-10 shadow-sm text-center">
            <h1 class="text-2xl font-bold mb-4">Exam is currently unavailable</h1>
            <p class="text-slate-600">The exam is not live yet. Please check back later.</p>
            <a href="/" class="mt-6 inline-block bg-slate-800 text-white px-6 py-3 rounded-xl">Back to Home</a>
          </div>
        </body>
        </html>
        """, status_code=200)

    pdf_filename = QUESTION_PAPER_FILENAME or "question-paper.pdf"
    pdf_path = os.path.join(os.getcwd(), pdf_filename)
    if os.path.exists(pdf_path):
        pdf_viewer = f"""
            <iframe src="/static/{pdf_filename}" class="w-full h-full"></iframe>
        """
    else:
        pdf_viewer = """
            <div class='w-full h-full grid place-items-center bg-slate-50 text-slate-500 rounded-3xl border border-dashed border-slate-300'>
              <div class='text-center'>
                <p class='text-lg font-semibold mb-2'>No question paper uploaded yet.</p>
                <p class='text-sm'>Please ask the admin to upload the exam PDF.</p>
              </div>
            </div>
        """

    answer_indicators = ""
    for i in range(1, len(QUESTIONS) + 1):
        answer_indicators += f"""
        <div class='bg-slate-50 rounded-3xl border border-slate-200 p-3'>
            <div class='text-sm font-semibold mb-2'>Q{i}</div>
            <div class='grid grid-cols-4 gap-2'>
        """
        for idx in range(4):
            opt_letter = chr(65 + idx)
            answer_indicators += f"""
                <label class='flex items-center justify-center gap-2 rounded-xl border border-slate-200 p-2 text-xs cursor-pointer hover:bg-slate-100'>
                    <input type='radio' name='q_{i}' value='{opt_letter}' class='answer-option' onchange="updateAnswerSheet('{i}', '{opt_letter}')">
                    <span>{opt_letter}</span>
                </label>
            """
        answer_indicators += """
            </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>KSP Exam - Student Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="min-h-screen bg-slate-100">
        <div class="flex h-screen gap-4 p-4">
            <div class="w-64 bg-white rounded-lg shadow-md border border-slate-200 p-6 flex flex-col">
                <div class="mb-6">
                    <div class="flex items-center gap-3 mb-3">
                        <div class="w-10 h-10 bg-slate-800 text-white rounded-full flex items-center justify-center text-lg">👤</div>
                        <div>
                            <p class="font-semibold">Student</p>
                            <p class="text-sm text-slate-500">Role: Student</p>
                        </div>
                    </div>
                </div>

                <div class="bg-gradient-to-br from-blue-900 to-blue-800 text-white rounded-lg p-6 mb-6 text-center">
                    <p class="text-xs font-semibold uppercase tracking-wider text-blue-100 mb-2">TIME REMAINING</p>
                    <p class="text-4xl font-bold" id="timer">{EXAM_CONFIG['time_limit']:02}:00</p>
                </div>

                <div class="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-6 text-center">
                    <p class="text-xs text-slate-500 mb-1">Answered</p>
                    <p class="text-3xl font-semibold"><span id="answered-count">0</span>/{len(QUESTIONS)}</p>
                </div>

                <button onclick="logout()" class="mt-auto bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg w-full">
                    🚪 Logout
                </button>
            </div>

            <div class="flex-1 bg-white rounded-lg shadow-md border border-slate-200 p-6 overflow-hidden flex flex-col">
                <div class="mb-4">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-sm font-semibold text-slate-500">Question Paper</p>
                            <h2 class="text-2xl font-bold">Review the uploaded PDF</h2>
                        </div>
                    </div>
                </div>
                <div class="flex-1 rounded-3xl overflow-hidden border border-slate-200">
                    {pdf_viewer}
                </div>
            </div>

            <div class="w-96 bg-white rounded-lg shadow-md border border-slate-200 p-6 flex flex-col overflow-y-auto">
                <div class="mb-4">
                    <div class="text-sm font-semibold mb-3">📋 Answer Sheet</div>
                    <p class="text-sm text-slate-600 mb-2">Select the answers from the PDF and submit.</p>
                    <p class="text-xs text-slate-500">Admin will manually review and release your result.</p>
                </div>

                <div class="grid grid-cols-2 gap-3 mb-4">
                    <div class="rounded-3xl bg-slate-50 p-4 text-center">
                        <p class="text-xs text-slate-500">Answered</p>
                        <p class="text-3xl font-semibold" id="ans-count">0</p>
                    </div>
                    <div class="rounded-3xl bg-slate-50 p-4 text-center">
                        <p class="text-xs text-slate-500">Total Questions</p>
                        <p class="text-3xl font-semibold">{len(QUESTIONS)}</p>
                    </div>
                </div>

                <div class="flex-1 overflow-y-auto">
                    <div class="grid grid-cols-1 gap-3">
                        {answer_indicators}
                    </div>
                </div>

                <div class="mt-4 pt-4 border-t border-slate-200">
                    <button onclick="submitExam()" class="w-full bg-green-600 hover:bg-green-700 text-white py-3 rounded-lg font-semibold">
                        ✓ Submit Answers
                    </button>
                </div>
            </div>
        </div>

        <form id="exam-form" action="/submit" method="post" style="display:none;">
            <input type="hidden" name="username" id="username" value="{current_user}">
            <input type="hidden" name="started_at" id="started_at" value="{datetime.utcnow().isoformat()}">
            <div id="answer-inputs"></div>
        </form>

        <script>
            function updateAnswerSheet(qid, answer) {{
                const answered = document.querySelectorAll('input[type="radio"]:checked').length;
                document.getElementById('answered-count').textContent = answered;
                document.getElementById('ans-count').textContent = answered;
            }}
            function submitExam() {{
                const form = document.getElementById('exam-form');
                const answersDiv = document.getElementById('answer-inputs');
                answersDiv.innerHTML = '';
                document.querySelectorAll('input[type="radio"]:checked').forEach(input => {{
                    const hiddenInput = document.createElement('input');
                    hiddenInput.type = 'hidden';
                    hiddenInput.name = input.name;
                    hiddenInput.value = input.value;
                    answersDiv.appendChild(hiddenInput);
                }});
                form.submit();
            }}
            function logout() {{
                if (confirm('Are you sure you want to logout?')) {{
                    window.location.href = '/';
                }}
            }}
            const timerEl = document.getElementById('timer');
            const deadline = Date.now() + {EXAM_CONFIG['time_limit']} * 60 * 1000;
            const tick = () => {{
                const secondsLeft = Math.max(0, Math.floor((deadline - Date.now()) / 1000));
                const m = String(Math.floor(secondsLeft / 60)).padStart(2, '0');
                const s = String(secondsLeft % 60).padStart(2, '0');
                timerEl.textContent = m + ':' + s;
                if (secondsLeft <= 0) submitExam();
            }};
            tick();
            setInterval(tick, 1000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.post("/submit", response_class=HTMLResponse)
async def submit_exam(request: Request):
    form = await request.form()
    started_at = form.get("started_at")
    username = form.get("username", "student")
    submitted = {key: value for key, value in form.items() if key.startswith("q_")}
    answers = {}

    for i in range(1, len(QUESTIONS) + 1):
        key = f"q_{i}"
        chosen = submitted.get(key)
        answers[str(i)] = str(chosen).upper() if chosen else None

    submission = {
        "id": len(SUBMISSIONS) + 1,
        "username": username,
        "date": datetime.now().isoformat(),
        "started_at": started_at,
        "score": None,
        "percent": None,
        "correct": None,
        "incorrect": None,
        "unattempted": None,
        "total_questions": len(QUESTIONS),
        "answers": json.dumps(answers),
        "status": "pending",
        "graded": False,
    }
    SUBMISSIONS.append(submission)
    # persist to DB so submissions are available across processes
    try:
      save_submission_to_db(submission)
    except Exception:
      pass

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Submission Received</title>
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="min-h-screen bg-slate-50 text-slate-800">
      <div class="max-w-3xl mx-auto px-4 py-12">
        <div class="bg-white rounded-3xl shadow-sm border border-slate-200 p-8 text-center">
          <h1 class="text-3xl font-bold mb-4">Answers submitted successfully</h1>
          <p class="text-slate-600 mb-4">Your answer sheet has been saved. Admin will manually review and release the result.</p>
          <div class="bg-slate-50 rounded-3xl border border-slate-200 p-6">
            <p class="text-sm text-slate-500">Username</p>
            <p class="text-xl font-semibold">{username}</p>
            <p class="text-sm text-slate-500 mt-3">Submitted at</p>
            <p class="text-lg font-semibold">{started_at or datetime.now().isoformat()}</p>
          </div>
          <a href="/" class="mt-8 inline-flex items-center justify-center bg-slate-800 hover:bg-slate-900 text-white px-6 py-3 rounded-xl">Back to Home</a>
        </div>
      </div>
    </body>
    </html>
    """)


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    deny = require_admin(request)
    if deny:
        return deny
    # Build answer key editor dropdowns
    answer_editor = ""
    for i in range(1, min(101, len(QUESTIONS) + 1)):
        if i <= len(QUESTIONS):
            q = QUESTIONS[i - 1]
            current_answer = q["answer"]
            options = "".join([f"<option value='{opt}' {'selected' if current_answer == opt else ''}>{opt}</option>" for opt in ['A', 'B', 'C', 'D']])
            answer_editor += f"<div class='flex items-center gap-3'><span class='w-12 text-sm font-semibold'>Q{i}</span><select class='border rounded px-2 py-1 answer-select' data-q='{i}'>{options}</select></div>"
    
    # Build results table
    results_rows = ""
    for idx, sub in enumerate(SUBMISSIONS):
        status_label = "Released" if sub.get("status") == "released" else "Pending"
        status_classes = "text-emerald-700 bg-emerald-100" if sub.get("status") == "released" else "text-amber-700 bg-amber-100"
        action = f"<a href='/grade/{idx}' class='text-sky-600 hover:text-sky-800 font-semibold'>Review</a>" if sub.get("status") != "released" else "<span class='text-slate-500'>Released</span>"
        results_rows += f"""
        <tr class='border-b border-slate-200 hover:bg-slate-50'>
            <td class='px-4 py-3'>{idx}</td>
            <td class='px-4 py-3'>{sub['username']}</td>
            <td class='px-4 py-3 text-sm'>{sub['date']}</td>
            <td class='px-4 py-3 font-semibold'>{sub['score'] if sub['score'] is not None else '—'}</td>
            <td class='px-4 py-3 text-green-600'>{sub['correct'] if sub['correct'] is not None else '—'}</td>
            <td class='px-4 py-3 text-red-600'>{sub['incorrect'] if sub['incorrect'] is not None else '—'}</td>
            <td class='px-4 py-3 text-slate-500'>{sub['unattempted'] if sub['unattempted'] is not None else '—'}</td>
            <td class='px-4 py-3'>{sub['total_questions']}</td>
            <td class='px-4 py-3'><span class='px-3 py-1 rounded-full text-xs font-semibold {status_classes}'>{status_label}</span></td>
            <td class='px-4 py-3'>{action}</td>
        </tr>
        """
    
    status_color = "green" if EXAM_CONFIG["is_live"] else "slate"
    status_text = "LIVE" if EXAM_CONFIG["is_live"] else "POSTED"
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Admin Panel</title>
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="min-h-screen bg-slate-50 text-slate-800">
      <div class="max-w-7xl mx-auto px-4 py-8">
        <div class="bg-gradient-to-r from-blue-900 to-blue-800 text-white rounded-3xl p-8 mb-6">
          <div class="flex items-center gap-3 mb-2">
            <span class="text-3xl">⚙️</span>
            <h1 class="text-3xl font-bold">Admin Dashboard</h1>
          </div>
          <p class="text-blue-100">KSP Mock Exam Management</p>
        </div>

        <div class="bg-white rounded-3xl border border-slate-200 p-6 mb-6">
          <div class="flex gap-4 border-b border-slate-200">
            <button class="tab-btn active px-4 py-3 font-semibold border-b-2 border-sky-600 text-sky-600" data-tab="papers">📄 Question Paper & Answer Key</button>
            <button class="tab-btn px-4 py-3 font-semibold text-slate-600 hover:text-slate-800" data-tab="settings">⚙️ Exam Settings</button>
            <button class="tab-btn px-4 py-3 font-semibold text-slate-600 hover:text-slate-800" data-tab="results">📊 Student Results</button>
          </div>

          <!-- Tab: Question Paper & Answer Key -->
          <div id="papers" class="tab-content mt-6">
            <h2 class="text-2xl font-semibold mb-6">Upload Question Paper PDF</h2>
            <div class="bg-slate-50 border border-slate-200 rounded-2xl p-6 mb-6">
              <p class="text-slate-600 mb-4">Upload your KSP Question Paper (PDF)</p>
              <form action="/upload-pdf" method="post" enctype="multipart/form-data" class="flex gap-3">
                <input type="file" name="file" accept="application/pdf" class="flex-1 border rounded-xl px-3 py-2" />
                <button class="bg-sky-600 hover:bg-sky-700 text-white px-6 py-2 rounded-xl">Upload PDF</button>
              </form>
            </div>

            <h2 class="text-2xl font-semibold mb-6">Set Answer Key</h2>
            <div class="bg-slate-50 border border-slate-200 rounded-2xl p-6 mb-6">
              <p class="text-slate-600 mb-4">Enter the correct option (A/B/C/D) for each of the 100 questions.</p>
              <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4" id="answer-grid">
                {answer_editor}
              </div>
              <div class="flex gap-3 mt-4">
                <button class="bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-2 rounded-xl" onclick="saveAnswerKey()">Save Answer Key</button>
                <button class="bg-slate-400 hover:bg-slate-500 text-white px-6 py-2 rounded-xl" onclick="resetAnswerKey()">Reset</button>
              </div>
            </div>

            <h2 class="text-2xl font-semibold mb-4">Or Upload Answer Key via CSV</h2>
            <div class="bg-slate-50 border border-slate-200 rounded-2xl p-6">
              <p class="text-slate-600 mb-4">CSV must have two columns: question_no (1-100) and answer (A/B/C/D)</p>
              <form action="/upload-csv" method="post" enctype="multipart/form-data" class="flex gap-3">
                <input type="file" name="file" accept="text/csv" class="flex-1 border rounded-xl px-3 py-2" />
                <button class="bg-slate-800 hover:bg-slate-900 text-white px-6 py-2 rounded-xl">Upload CSV</button>
              </form>
            </div>
          </div>

          <!-- Tab: Exam Settings -->
          <div id="settings" class="tab-content mt-6 hidden">
            <h2 class="text-2xl font-semibold mb-6">Exam Configuration</h2>
            <div class="bg-white rounded-2xl border border-slate-200 p-6 mb-6">
              <div class="grid md:grid-cols-2 gap-6">
                <div>
                  <label class="block text-sm font-semibold mb-2">Total Questions</label>
                  <input type="number" id="total_questions" value="{EXAM_CONFIG['total_questions']}" class="w-full border rounded-xl px-3 py-2" />
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Time Limit (minutes)</label>
                  <input type="number" id="time_limit" value="{EXAM_CONFIG['time_limit']}" class="w-full border rounded-xl px-3 py-2" />
                </div>
              </div>
              <button class="mt-4 bg-sky-600 hover:bg-sky-700 text-white px-6 py-2 rounded-xl" onclick="saveExamConfig()">Save Settings</button>
            </div>

            <h2 class="text-2xl font-semibold mb-6">Exam Visibility</h2>
            <div class="bg-{'green' if EXAM_CONFIG['is_live'] else 'slate'}-50 border border-{'green' if EXAM_CONFIG['is_live'] else 'slate'}-200 rounded-2xl p-6">
              <div class="flex items-center gap-3 mb-4">
                <span class="text-2xl">✅</span>
                <div>
                  <p class="text-sm text-slate-500">Exam Status</p>
                  <p class="text-xl font-semibold text-{'green' if EXAM_CONFIG['is_live'] else 'slate'}-700">Exam is currently {status_text} and visible to students.</p>
                </div>
              </div>
              <button class="bg-{'red' if EXAM_CONFIG['is_live'] else 'emerald'}-600 hover:bg-{'red' if EXAM_CONFIG['is_live'] else 'emerald'}-700 text-white px-6 py-2 rounded-xl" onclick="toggleExamStatus()">
                {'Un-post Exam' if EXAM_CONFIG['is_live'] else 'Post Exam'}
              </button>
            </div>
          </div>

          <!-- Tab: Student Results -->
          <div id="results" class="tab-content mt-6 hidden">
            <h2 class="text-2xl font-semibold mb-6">Student Results</h2>
            <div class="overflow-x-auto mb-6">
              <table class="w-full">
                <thead class="bg-slate-100 border-b border-slate-200">
                  <tr>
                    <th class="px-4 py-3 text-left text-sm font-semibold">#</th>
                    <th class="px-4 py-3 text-left text-sm font-semibold">Username</th>
                    <th class="px-4 py-3 text-left text-sm font-semibold">Date</th>
                    <th class="px-4 py-3 text-left text-sm font-semibold">Score</th>
                    <th class="px-4 py-3 text-left text-sm font-semibold">Correct</th>
                    <th class="px-4 py-3 text-left text-sm font-semibold">Incorrect</th>
                    <th class="px-4 py-3 text-left text-sm font-semibold">Unattempted</th>
                    <th class="px-4 py-3 text-left text-sm font-semibold">Total</th>
                    <th class="px-4 py-3 text-left text-sm font-semibold">Status</th>
                    <th class="px-4 py-3 text-left text-sm font-semibold">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {results_rows if results_rows else '<tr><td colspan="10" class="px-4 py-6 text-center text-slate-500">No submissions yet</td></tr>'}
                </tbody>
              </table>
            </div>
            <button class="bg-sky-600 hover:bg-sky-700 text-white px-6 py-2 rounded-xl" onclick="downloadResults()">📥 Download Results CSV</button>
          </div>
        </div>

        <div class="text-center mt-6">
          <a href="/" class="text-slate-600 hover:text-slate-800">← Back to Home</a>
        </div>
      </div>

      <script>
        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {{
          btn.addEventListener('click', () => {{
            document.querySelectorAll('.tab-btn').forEach(b => {{
              b.classList.remove('active', 'border-b-2', 'border-sky-600', 'text-sky-600');
              b.classList.add('text-slate-600');
            }});
            document.querySelectorAll('.tab-content').forEach(t => t.classList.add('hidden'));
            btn.classList.add('active', 'border-b-2', 'border-sky-600', 'text-sky-600');
            btn.classList.remove('text-slate-600');
            document.getElementById(btn.dataset.tab).classList.remove('hidden');
          }});
        }});

        function saveAnswerKey() {{
          const answers = {{}};
          document.querySelectorAll('.answer-select').forEach(sel => {{
            answers[sel.dataset.q] = sel.value;
          }});
          fetch('/update-answer-key', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(answers)
          }}).then(() => alert('Answer key saved!'));
        }}

        function resetAnswerKey() {{
          if(confirm('Reset all answers?')) location.reload();
        }}

        function saveExamConfig() {{
          const config = {{
            total_questions: parseInt(document.getElementById('total_questions').value),
            time_limit: parseInt(document.getElementById('time_limit').value)
          }};
          fetch('/update-exam-config', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(config)
          }}).then(() => alert('Exam settings saved!'));
        }}

        function toggleExamStatus() {{
          fetch('/toggle-exam-status', {{method: 'POST'}}).then(() => location.reload());
        }}

        function downloadResults() {{
          window.location.href = '/download-results';
        }}
      </script>
    </body>
    </html>
    """)


@app.post("/upload-pdf")
def upload_pdf(request: Request, file: UploadFile = File(...)):
    deny = require_admin(request)
    if deny:
        return deny
    global QUESTION_PAPER_FILENAME
    filename = file.filename or "question-paper.pdf"
    filename = os.path.basename(filename)
    target_name = "question-paper.pdf"
    path = os.path.join(os.getcwd(), target_name)
    with open(path, "wb") as f:
        f.write(file.file.read())
    QUESTION_PAPER_FILENAME = target_name
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/grade/{submission_index}", response_class=HTMLResponse)
def grade_submission_page(request: Request, submission_index: int):
    deny = require_admin(request)
    if deny:
        return deny
    if submission_index < 0 or submission_index >= len(SUBMISSIONS):
        return HTMLResponse("<h2>Submission not found</h2>", status_code=404)

    submission = SUBMISSIONS[submission_index]
    answers = json.loads(submission["answers"])
    answer_rows = "".join([
        f"<tr class='border-b border-slate-200'><td class='px-4 py-3'>Q{question}</td><td class='px-4 py-3'>{answer or 'Unanswered'}</td></tr>"
        for question, answer in answers.items()
    ])

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Grade Submission</title>
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="min-h-screen bg-slate-50 text-slate-800">
      <div class="max-w-6xl mx-auto px-4 py-10">
        <div class="bg-white rounded-3xl border border-slate-200 p-8 shadow-sm mb-6">
          <div class="flex items-center justify-between gap-4 mb-6">
            <div>
              <h1 class="text-3xl font-bold">Grade Submission</h1>
              <p class="text-slate-600 mt-2">Review answers and release the result for {submission['username']}.</p>
            </div>
            <a href="/admin" class="bg-slate-800 text-white px-5 py-3 rounded-xl">Back to Admin</a>
          </div>
          <div class="grid md:grid-cols-3 gap-4">
            <div class="rounded-3xl border border-slate-200 p-4 bg-slate-50">
              <p class="text-sm text-slate-500">Username</p>
              <p class="font-semibold">{submission['username']}</p>
            </div>
            <div class="rounded-3xl border border-slate-200 p-4 bg-slate-50">
              <p class="text-sm text-slate-500">Submitted</p>
              <p class="font-semibold">{submission['date']}</p>
            </div>
            <div class="rounded-3xl border border-slate-200 p-4 bg-slate-50">
              <p class="text-sm text-slate-500">Status</p>
              <p class="font-semibold">{submission['status'].title()}</p>
            </div>
          </div>
        </div>

        <div class="grid lg:grid-cols-2 gap-6">
          <div class="bg-white rounded-3xl border border-slate-200 p-6 overflow-hidden">
            <h2 class="text-xl font-semibold mb-4">Student Answers</h2>
            <div class="overflow-x-auto">
              <table class="w-full text-left">
                <thead class="bg-slate-100 border-b border-slate-200">
                  <tr>
                    <th class="px-4 py-3 text-sm font-semibold">Question</th>
                    <th class="px-4 py-3 text-sm font-semibold">Answer</th>
                  </tr>
                </thead>
                <tbody>
                  {answer_rows}
                </tbody>
              </table>
            </div>
          </div>

          <div class="bg-white rounded-3xl border border-slate-200 p-6">
            <h2 class="text-xl font-semibold mb-4">Manual Grade</h2>
            <form action="/grade-submission" method="post" class="space-y-4">
              <input type="hidden" name="submission_index" value="{submission_index}" />
              <div>
                <label class="block text-sm font-semibold mb-2">Score</label>
                <input name="score" type="number" step="0.25" min="0" value="{submission.get('score') or ''}" class="w-full border rounded-xl px-3 py-2" required />
              </div>
              <div class="grid grid-cols-3 gap-3">
                <div>
                  <label class="block text-sm font-semibold mb-2">Correct</label>
                  <input name="correct" type="number" min="0" value="{submission.get('correct') or 0}" class="w-full border rounded-xl px-3 py-2" required />
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Incorrect</label>
                  <input name="incorrect" type="number" min="0" value="{submission.get('incorrect') or 0}" class="w-full border rounded-xl px-3 py-2" required />
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Unattempted</label>
                  <input name="unattempted" type="number" min="0" value="{submission.get('unattempted') or 0}" class="w-full border rounded-xl px-3 py-2" required />
                </div>
              </div>
              <button class="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3 rounded-xl font-semibold">Release Result</button>
            </form>
          </div>
        </div>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.post("/grade-submission")
def grade_submission(request: Request, submission_index: int = Form(...), score: float = Form(...), correct: int = Form(...), incorrect: int = Form(...), unattempted: int = Form(...)):
    deny = require_admin(request)
    if deny:
        return deny
    if submission_index < 0 or submission_index >= len(SUBMISSIONS):
        return HTMLResponse("<h2>Submission not found</h2>", status_code=404)

    submission = SUBMISSIONS[submission_index]
    submission["score"] = round(score, 2)
    submission["correct"] = correct
    submission["incorrect"] = incorrect
    submission["unattempted"] = unattempted
    submission["percent"] = round((submission["score"] / submission["total_questions"]) * 100, 2) if submission["total_questions"] else 0.0
    submission["status"] = "released"
    submission["graded"] = True
    # persist updates to DB
    try:
      update_submission_in_db(submission)
    except Exception:
      pass
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/upload-csv")
def upload_csv(request: Request, file: UploadFile = File(...)):
    deny = require_admin(request)
    if deny:
        return deny
    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        qid = row.get("id") or row.get("question_id")
        answer = (row.get("answer") or row.get("correct") or "").strip().upper()
        if qid:
            for q in QUESTIONS:
                if str(q["id"]) == str(qid):
                    q["answer"] = answer
                    break
    return HTMLResponse("<h2>Answer key uploaded successfully</h2>")


@app.post("/manual-answer-key")
def manual_answer_key(request: Request, key: str = Form(...)):
    deny = require_admin(request)
    if deny:
        return deny
    for line in key.splitlines():
        if ":" not in line:
            continue
        qid, answer = [part.strip() for part in line.split(":", 1)]
        for q in QUESTIONS:
            if str(q["id"]) == qid:
                q["answer"] = answer.upper()
                break
    return HTMLResponse("<h2>Manual answer key saved</h2>")


@app.post("/update-answer-key")
async def update_answer_key(request: Request):
    deny = require_admin(request)
    if deny:
        return deny
    data = await request.json()
    for qid, answer in data.items():
        for q in QUESTIONS:
            if str(q["id"]) == str(qid):
                q["answer"] = answer.upper()
                break
    return JSONResponse({"status": "ok"})


@app.post("/update-exam-config")
async def update_exam_config(request: Request):
    deny = require_admin(request)
    if deny:
        return deny
    data = await request.json()
    EXAM_CONFIG["total_questions"] = data.get("total_questions", 100)
    EXAM_CONFIG["time_limit"] = data.get("time_limit", 90)
    return JSONResponse({"status": "ok"})


@app.post("/toggle-exam-status")
def toggle_exam_status(request: Request):
    deny = require_admin(request)
    if deny:
        return deny
    EXAM_CONFIG["is_live"] = not EXAM_CONFIG["is_live"]
    return JSONResponse({"status": "ok", "is_live": EXAM_CONFIG["is_live"]})


@app.get("/download-results")
def download_results(request: Request):
    deny = require_admin(request)
    if deny:
        return deny
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Username", "Date", "Score", "Correct", "Incorrect", "Unattempted", "Total Questions"])
    
    for sub in SUBMISSIONS:
        writer.writerow([
            sub["username"],
            sub["date"],
            sub["score"],
            sub["correct"],
            sub["incorrect"],
            sub["unattempted"],
            sub["total_questions"]
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=exam_results.csv"}
    )


# Debug endpoint to inspect submissions in-memory (for troubleshooting only)
@app.get("/_debug/submissions")
def debug_submissions(request: Request):
  # Allow requests from localhost without auth so local debugging tools/curl can access this.
  client_host = None
  try:
    client_host = request.client.host
  except Exception:
    client_host = None

  if client_host not in ("127.0.0.1", "::1", "localhost"):
    deny = require_admin(request)
    if deny:
      return deny

  return JSONResponse({"count": len(SUBMISSIONS), "submissions": SUBMISSIONS})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
