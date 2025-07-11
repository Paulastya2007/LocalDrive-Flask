from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from dotenv import load_dotenv
from utils.auth import (
    create_user, authenticate_user, validate_email,
    validate_password, hash_password, verify_password,
    get_all_users, admin_set_user_password
)
from utils.filemanager import FileManager
import os

load_dotenv() # Load environment variables from .env file
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
    if 'user' not in session:
        return redirect(url_for('login'))

    page = request.args.get('page', 1, type=int)
    per_page = 5  # Files per page
    active_tab = request.args.get('tab', 'my_files') # Default to 'my_files'

    files_list = []
    total_files = 0

    if active_tab == 'global_files':
        files_list, total_files = file_manager.get_global_files(page=page, per_page=per_page)
    else: # Default to 'my_files'
        active_tab = 'my_files' # Ensure active_tab is correctly set if default
        files_list, total_files = file_manager.get_user_files(session['user'], page=page, per_page=per_page)

    total_pages = (total_files + per_page - 1) // per_page

    return render_template('home.html',
                           user=session['user'],
                           pdfs=files_list,
                           current_page=page,
                           total_files=total_files,
                           per_page=per_page,
                           total_pages=total_pages,
                           active_tab=active_tab)

# Removed /load_files route as it's no longer needed for button pagination

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
    # original_filename = secure_filename(file.filename) # Removed secure_filename call
    original_filename = file.filename # Use raw filename

    # Basic check for directory traversal attempts in the raw filename.
    # This is NOT as robust as secure_filename but is a minimal check.
    if ".." in original_filename or "/" in original_filename or "\\" in original_filename:
        return jsonify({'error': 'Invalid characters in filename.'}), 400

    # Save to a temporary location first
    # Note: temp_file_path will use the raw original_filename.
    # OS might have issues if filename is too long or has certain forbidden chars not caught above.
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

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'admin_logged_in' in session:
        return redirect(url_for('admin_panel')) # Redirect to admin panel if already logged in

    if request.method == 'POST':
        password = request.form.get('password')
        admin_password_hash = os.getenv('ADMIN_PASSWORD_HASH')

        if not admin_password_hash:
            flash('Admin functionality is not configured.', 'error')
            return render_template('admin_login.html'), 500 # Internal server error

        # Directly compare submitted password's hash with the stored hash
        # Assuming verify_password(submitted_plain_password, stored_hash)
        if password and verify_password(password, admin_password_hash):
            session['admin_logged_in'] = True
            session.permanent = True # Make admin session more persistent if desired
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_panel')) # Placeholder for admin panel route
        else:
            flash('Invalid admin password.', 'error')
            return render_template('admin_login.html'), 401 # Unauthorized

    return render_template('admin_login.html')

# Placeholder for admin_panel route - to be created in next step
@app.route('/admin/panel')
def admin_panel():
    if 'admin_logged_in' not in session:
        flash('Please log in as admin to access this page.', 'warning')
        return redirect(url_for('admin_login'))

    users = get_all_users() # Fetch all users (email, created_at)
    return render_template('admin_panel.html', users=users)

@app.route('/set_global_status/<int:file_id>', methods=['POST'])
def set_global_status(file_id):
    # Ensure this check happens first and explicitly returns JSON
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Authentication required. Please log in again.'}), 401

    try:
        data = request.get_json()
        if data is None: # More robust check for empty/non-json payload
            app.logger.warning(f"set_global_status: Received empty or non-JSON payload for file_id {file_id}")
            return jsonify({'status': 'error', 'message': 'Invalid request. Expected JSON payload.'}), 400

        if 'is_global' not in data or not isinstance(data['is_global'], bool):
            app.logger.warning(f"set_global_status: Missing or malformed 'is_global' for file_id {file_id}. Data: {data}")
            return jsonify({'status': 'error', 'message': 'Invalid request. Missing or malformed "is_global" boolean field in JSON body.'}), 400

        is_global_flag = data['is_global']

        success, message = file_manager.set_file_global_status(file_id, session['user'], is_global_flag)

        if success:
            return jsonify({'status': 'success', 'message': message}), 200
        else:
            if "Access denied" in message:
                return jsonify({'status': 'error', 'message': message}), 403
            elif "File not found" in message:
                return jsonify({'status': 'error', 'message': message}), 404
            else: # Includes other FileManager errors
                app.logger.error(f"set_file_global_status failed for file_id {file_id}, user {session['user']}: {message}")
                return jsonify({'status': 'error', 'message': message}), 500

    except Exception as e:
        app.logger.error(f"Unexpected error in /set_global_status for file_id {file_id}: {str(e)}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'An unexpected server error occurred.'}), 500

@app.route('/admin/reset-password/<path:user_email_for_reset>', methods=['POST'])
def admin_reset_password(user_email_for_reset):
    if 'admin_logged_in' not in session:
        flash('Admin access required.', 'error')
        return redirect(url_for('admin_login'))

    new_password = request.form.get('new_password')

    is_valid_password, password_message = validate_password(new_password)
    if not is_valid_password:
        flash(f'Error for user {user_email_for_reset}: {password_message}', 'error')
        return redirect(url_for('admin_panel'))

    success, message = admin_set_user_password(user_email_for_reset, new_password)
    if success:
        flash(f'Password for {user_email_for_reset} has been updated successfully.', 'success')
    else:
        flash(f'Failed to update password for {user_email_for_reset}: {message}', 'error')

    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('You have been logged out from the admin panel.', 'info')
    return redirect(url_for('admin_login'))


if __name__ == '__main__':
    app.run(host='0.0.0.0')
