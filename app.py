from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from utils.auth import create_user, authenticate_user, validate_email, validate_password
from utils.filemanager import FileManager
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'my_secret_key'  # Change this to a more secure key in production

# Initialize file manager
file_manager = FileManager()

# Configure upload settings
UPLOAD_FOLDER = 'uploads'
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB max file size
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

@app.route('/')
def home():
    if 'user' in session:
        # Get user's PDFs
        user_pdfs = file_manager.get_user_files(session['user'])
        return render_template('home.html', user=session['user'], pdfs=user_pdfs)
    return redirect(url_for('login'))

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
    
    try:
        # Secure the filename
        filename = secure_filename(file.filename)
        
        # Save file to uploads directory
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        # Add to database
        success, message = file_manager.add_file(
            user_email=session['user'],
            filename=filename,
            file_path=file_path
        )
        
        if success:
            return jsonify({'success': True, 'message': 'File uploaded successfully'})
        else:
            # Clean up file if database insertion failed
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'error': message}), 500
            
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

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
    app.run(host=0.0.0.0)
