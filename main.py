# main.py

import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from photo_processing import process_and_save_image, allowed_file
import json
import logging
import random

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key

# Configuration
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TESTS_DIR = os.path.join(BASE_DIR, 'tests')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
app.config['TESTS_DIR'] = TESTS_DIR
app.config['STATIC_DIR'] = STATIC_DIR
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB upload limit

# Ensure necessary directories exist
os.makedirs(TESTS_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, 'uploads'), exist_ok=True)  # General uploads folder

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# Helper function to get available tests
def get_available_tests():
    return [name for name in os.listdir(TESTS_DIR)
            if os.path.isdir(os.path.join(TESTS_DIR, name))]


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/create_test', methods=['GET', 'POST'])
def create_test():
    if request.method == 'POST':
        test_name = request.form.get('test_name')
        if not test_name:
            flash('Test name is required!', 'error')
            return redirect(url_for('create_test'))

        # Secure the test name
        test_name_secure = secure_filename(test_name)
        test_path = os.path.join(TESTS_DIR, test_name_secure)

        if not os.path.exists(test_path):
            os.makedirs(test_path)
            # Create uploads folder within the test directory inside static
            test_upload_folder = os.path.join(app.config['STATIC_DIR'], 'uploads', test_name_secure)
            os.makedirs(test_upload_folder, exist_ok=True)
            flash(f'Test "{test_name}" created successfully!', 'success')
            return redirect(url_for('add_question', test_name=test_name_secure))
        else:
            flash('Test already exists!', 'error')
            return redirect(url_for('create_test'))
    return render_template('create_test.html')


@app.route('/add_question/<test_name>', methods=['GET', 'POST'])
def add_question(test_name):
    test_path = os.path.join(TESTS_DIR, test_name)
    if not os.path.exists(test_path):
        flash('Test does not exist!', 'error')
        return redirect(url_for('home'))

    json_path = os.path.join(test_path, 'questions.json')
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            questions = json.load(f)
    else:
        questions = []

    if request.method == 'POST':
        question_text = request.form.get('question')
        answer_text = request.form.get('answer')
        file = request.files.get('photo')

        if not question_text or not answer_text:
            flash('Both question and answer are required!', 'error')
            return redirect(url_for('add_question', test_name=test_name))

        photo_filename = None
        if file and file.filename != '':
            try:
                # Define the uploads folder inside the specific test's directory within static
                test_upload_folder = os.path.join(app.config['STATIC_DIR'], 'uploads', test_name)
                os.makedirs(test_upload_folder, exist_ok=True)

                # Process and save the image
                photo_filename = process_and_save_image(
                    file=file,
                    save_directory=test_upload_folder,
                    question_number=len(questions) + 1
                )
                logger.debug(f"Photo saved as {photo_filename}")
            except ValueError as ve:
                flash(str(ve), 'error')
                return redirect(url_for('add_question', test_name=test_name))
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                flash('An unexpected error occurred while processing the image.', 'error')
                return redirect(url_for('add_question', test_name=test_name))

        # Append the new question
        question_entry = {
            'question': question_text,
            'answer': answer_text,
            'photo': photo_filename
        }
        questions.append(question_entry)

        # Save to JSON
        try:
            with open(json_path, 'w') as f:
                json.dump(questions, f, indent=4)
            flash('Question added successfully!', 'success')
        except Exception as e:
            logger.error(f"Error saving question to JSON: {e}")
            flash('Error saving question. Please try again.', 'error')

        return redirect(url_for('add_question', test_name=test_name))

    return render_template('add_question.html', test_name=test_name, questions=questions)


@app.route('/take_test', methods=['GET', 'POST'])
def select_test():
    available_tests = get_available_tests()
    if request.method == 'POST':
        selected_test = request.form.get('selected_test')
        if not selected_test:
            flash('Please select a test to take.', 'error')
            return redirect(url_for('select_test'))

        # Load questions
        test_path = os.path.join(TESTS_DIR, selected_test)
        json_path = os.path.join(test_path, 'questions.json')
        if not os.path.exists(json_path):
            flash('Selected test has no questions.', 'error')
            return redirect(url_for('select_test'))

        with open(json_path, 'r') as f:
            questions = json.load(f)

        if not questions:
            flash('Selected test has no questions.', 'error')
            return redirect(url_for('select_test'))

        # Shuffle questions
        random.shuffle(questions)

        # Initialize session variables
        session['selected_test'] = selected_test
        session['questions'] = questions
        session['current_question'] = 0
        session['correct'] = 0
        session['incorrect'] = 0
        session['answers'] = []  # To store user's answers and grading
        session['pending_questions'] = []  # To store questions to be repeated

        return redirect(url_for('question'))

    return render_template('select_test.html', tests=available_tests)


@app.route('/question', methods=['GET', 'POST'])
def question():
    if 'selected_test' not in session or 'questions' not in session:
        flash('No test selected. Please select a test to take.', 'error')
        return redirect(url_for('select_test'))

    questions = session['questions']
    current_index = session['current_question']

    if current_index >= len(questions):
        if session['pending_questions']:
            session['questions'] = session['pending_questions']
            session['pending_questions'] = []
            session['current_question'] = 0
            current_index = 0
            questions = session['questions']
            flash('Repeating questions you marked as incorrect.', 'info')
        else:
            return redirect(url_for('results'))

    current_question = questions[current_index]

    if request.method == 'POST':
        user_answer = request.form.get('answer').strip()
        correct_answer = current_question['answer'].strip()
        is_correct = user_answer.lower() == correct_answer.lower()

        # Store the user’s answer, including the photo reference
        session['answers'].append({
            'question': current_question['question'],
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'photo': current_question.get('photo')
        })

        if is_correct:
            session['correct'] += 1
            flash('Correct!', 'success')
            session['current_question'] += 1
            return redirect(url_for('question'))
        else:
            session['incorrect'] += 1
            flash('Incorrect. Please review your answer.', 'error')
            return redirect(url_for('review_answer', question_index=len(session['answers']) - 1))

    photo_url = None
    if current_question.get('photo'):
        photo_url = url_for('static', filename=f'uploads/{session["selected_test"]}/{current_question["photo"]}')

    return render_template('question.html',
                           question_number=current_index + 1,
                           total_questions=len(questions),
                           question=current_question['question'],
                           photo_url=photo_url)



@app.route('/review_answer/<int:question_index>', methods=['GET', 'POST'])
def review_answer(question_index):
    if 'selected_test' not in session or 'answers' not in session:
        flash('No test selected. Please select a test to take.', 'error')
        return redirect(url_for('select_test'))

    answers = session['answers']
    if question_index >= len(answers):
        flash('Invalid question index.', 'error')
        return redirect(url_for('question'))

    answer_entry = answers[question_index]

    if request.method == 'POST':
        grading = request.form.get('grading')
        if grading == 'right':
            # Update the answer entry to reflect user confirmation
            answer_entry['is_correct'] = True
            session['correct'] += 1
            session['incorrect'] -= 1
            flash('Marked as correct.', 'success')
        elif grading == 'wrong':
            # Add the question back to pending_questions
            current_question = {
                'question': answer_entry['question'],
                'answer': answer_entry['correct_answer'],
                'photo': get_photo_filename(answer_entry['question'])
            }
            session['pending_questions'].append(current_question)
            flash('Question will be repeated at the end.', 'info')
        else:
            flash('Invalid grading option.', 'error')
            return redirect(url_for('review_answer', question_index=question_index))

        # Update the answers in the session
        session['answers'] = answers
        session['current_question'] += 1
        return redirect(url_for('question'))

    # Retrieve the photo URL if available
    photo_url = None
    photo_filename = get_photo_filename(answer_entry['question'])
    if photo_filename:
        photo_url = url_for('static', filename=f'uploads/{session["selected_test"]}/{photo_filename}')

    return render_template('review_answer.html',
                           question_number=question_index + 1,
                           question=answer_entry['question'],
                           user_answer=answer_entry['user_answer'],
                           correct_answer=answer_entry['correct_answer'],
                           photo_url=photo_url)


def get_photo_filename(question_text):
    for question in session['questions'] + session.get('pending_questions', []):
        if question['question'] == question_text:
            return question.get('photo')
    return None



@app.route('/results')
def results():
    if 'selected_test' not in session or 'questions' not in session:
        flash('No test selected. Please select a test to take.', 'error')
        return redirect(url_for('select_test'))

    correct = session.get('correct', 0)
    incorrect = session.get('incorrect', 0)
    total = correct + incorrect
    percentage = round((correct / total) * 100 if total > 0 else 0, 2)

    answers = session.get('answers', [])

    # Clear session after displaying results
    session.clear()

    return render_template('results.html',
                           correct=correct,
                           incorrect=incorrect,
                           total=total,
                           percentage=percentage,
                           answers=answers)


@app.route('/finish_test', methods=['POST'])
def finish_test():
    # Clear session and redirect to home
    session.clear()
    flash('Test creation finished.', 'success')
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True)

