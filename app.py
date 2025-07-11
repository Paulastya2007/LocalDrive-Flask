from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from utils.auth import create_user, authenticate_user, validate_email, validate_password
from utils.filemanager import FileManager
import os
import shutil # Added for shutil.rmtree
from werkzeug.utils import secure_filename

import tempfile # For temporary file handling

app = Flask(__name__)
app.secret_key = 'my_secret_key'  # Change this to a more secure key in production

# Configure upload settings
UPLOAD_FOLDER = os.path.abspath('uploads') # Use absolute path
TEMP_FOLDER = os.path.join(UPLOAD_FOLDER, 'temp') # Temporary folder for uploads

MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB max file size
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create upload and temp directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

# Initialize file manager
file_manager = FileManager(upload_folder=UPLOAD_FOLDER)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

@app.route('/')
def home():
    if 'user' in session:
        page = request.args.get('page', 1, type=int)
        per_page = 5 # Files per page for initial load, can be same as infinite scroll

        user_pdfs, total_files = file_manager.get_user_files(session['user'], page=page, per_page=per_page)

        # Calculate total pages for frontend, though not strictly needed for infinite scroll
        # total_pages = (total_files + per_page - 1) // per_page

        return render_template('home.html', user=session['user'], pdfs=user_pdfs, current_page=page, total_files=total_files, per_page=per_page)
    return redirect(url_for('login'))

@app.route('/load_files')
def load_files():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    page = request.args.get('page', 1, type=int)
    per_page = 5 # Files per page for infinite scroll

    files, total_files = file_manager.get_user_files(session['user'], page=page, per_page=per_page)

    return jsonify({
        'files': files,
        'has_more': (page * per_page) < total_files,
        'next_page': page + 1 if (page * per_page) < total_files else None,
        'total_files': total_files
    })

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only PDF files are allowed'}), 400
    
    action = request.form.get('action', 'default') # Get action: 'default', 'replace', 'keep_both'
    original_filename = secure_filename(file.filename)

    # Save to a temporary location first
    temp_dir = tempfile.mkdtemp(dir=TEMP_FOLDER)
    temp_file_path = os.path.join(temp_dir, original_filename)

    try:
        file.save(temp_file_path)
        
        # Let FileManager handle moving to final destination and DB operations
        result = file_manager.add_file(
            user_email=session['user'],
            original_filename=original_filename,
            temp_uploaded_path=temp_file_path,
            action=action
        )
        
        # If successfully moved by file_manager, temp_file_path won't exist.
        # If status is 'duplicate', temp_file_path still exists and frontend will decide.
        # If status is 'error' before move, temp_file_path exists.
        # If status is 'error' after move (DB error), file_manager tries to clean up moved file.

        if result.get("status") == "duplicate":
            # Don't remove temp_file_path yet, client might need to retry with a different action.
            # The client will need to re-upload the file for 'replace' or 'keep_both' actions if this temp file is cleaned up too soon.
            # For simplicity in this iteration, we'll require re-upload. So, clean up here.
            # A more advanced implementation might keep the temp file alive based on a session or token.
            return jsonify(result), 200 # Send 200 OK with duplicate status

        elif result.get("status") == "success":
            return jsonify(result), 201
        else: # Error
            return jsonify(result), 500
            
    except Exception as e:
        # General exception during save or add_file call itself
        return jsonify({'status': 'error', 'message': f'Upload processing failed: {str(e)}'}), 500
    finally:
        # Clean up the temporary directory and its contents
        # This will remove temp_file_path if it wasn't moved or if an error occurred before moving.
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Error cleaning up temporary directory {temp_dir}: {e}")


@app.route('/download/<int:file_id>')
def download_file(file_id):
    if 'user' not in session:
        flash('Please log in to download files', 'error')
        return redirect(url_for('login'))
    
    file_info = file_manager.get_file_info(file_id, session['user'])
    if not file_info:
        flash('File not found or access denied', 'error')
        return redirect(url_for('home'))
    
    file_path = file_info[3]  # file_path is at index 3
    if not os.path.exists(file_path):
        flash('File not found on server', 'error')
        return redirect(url_for('home'))
    
    return send_file(file_path, as_attachment=True, download_name=file_info[2])

@app.route('/preview/<int:file_id>')
def preview_file(file_id):
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    file_info = file_manager.get_file_info(file_id, session['user'])
    if not file_info:
        return jsonify({'error': 'File not found or access denied'}), 404
    
    file_path = file_info[3]  # file_path is at index 3
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found on server'}), 404
    
    return send_file(file_path, mimetype='application/pdf')

@app.route('/delete/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    success, message = file_manager.delete_file(file_id, session['user'])
    
    if success:
        return jsonify({'success': True, 'message': 'File deleted successfully'})
    else:
        return jsonify({'error': message}), 400

@app.route('/search')
def search_files():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': []})
    
    results = file_manager.search_files(session['user'], query)
    return jsonify({'results': results})

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # Basic validation
        if not email or not password:
            error = "Please fill in all fields"
            return render_template('signup.html', error=error, email=email)
        
        # Validate email format
        if not validate_email(email):
            error = "Please enter a valid email address"
            return render_template('signup.html', error=error, email=email)
        
        # Validate password
        password_valid, password_message = validate_password(password)
        if not password_valid:
            error = password_message
            return render_template('signup.html', error=error, email=email)
        
        # Create user
        success, message = create_user(email, password)
        
        if success:
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for('login'))
        else:
            error = message
            return render_template('signup.html', error=error, email=email)

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # Basic validation
        if not email or not password:
            error = "Please fill in all fields"
            return render_template('login.html', error=error, email=email)
        
        # Authenticate user
        success, message = authenticate_user(email, password)
        
        if success:
            session['user'] = email
            flash(f"Welcome back, {email}!", "success")
            return redirect(url_for('home'))
        else:
            # Provide generic error message for security
            error = "Invalid email or password"
            return render_template('login.html', error=error, email=email)

    return render_template('login.html')

@app.route('/logout')
def logout():
    user = session.get('user')
    session.pop('user', None)
    if user:
        flash("You have been logged out successfully", "info")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0')
