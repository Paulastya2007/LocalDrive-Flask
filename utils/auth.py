import hashlib
import sqlite3
import os
from contextlib import contextmanager

DATA_DIR = '/app/data'
DATABASE_FILE = os.path.join(DATA_DIR, 'users.db')

def init_database():
    """Initialize the SQLite database with users table."""
    # Ensure the data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        yield conn
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def hash_password(password):
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed_password):
    """Verify if password matches the hashed password."""
    return hash_password(password) == hashed_password

def user_exists(email):
    """Check if user exists in the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE email = ?", (email,))
            return cursor.fetchone() is not None
    except sqlite3.Error:
        return False

def create_user(email, password):
    """Create a new user account."""
    # Initialize database if it doesn't exist
    init_database()
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user already exists
            cursor.execute("SELECT 1 FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                return False, "User already exists"
            
            # Insert new user
            password_hash = hash_password(password)
            cursor.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email, password_hash)
            )
            conn.commit()
            return True, "User created successfully"
            
    except sqlite3.IntegrityError:
        return False, "User already exists"
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"

def authenticate_user(email, password):
    """Authenticate user with email and password."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password_hash FROM users WHERE email = ?", 
                (email,)
            )
            result = cursor.fetchone()
            
            if not result:
                return False, "User not found"
            
            stored_hash = result[0]
            if verify_password(password, stored_hash):
                return True, "Authentication successful"
            else:
                return False, "Invalid password"
                
    except sqlite3.Error:
        return False, "Database error occurred"

def get_user_info(email):
    """Get user information by email."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, email, created_at FROM users WHERE email = ?",
                (email,)
            )
            result = cursor.fetchone()
            
            if result:
                return {
                    'id': result[0],
                    'email': result[1],
                    'created_at': result[2]
                }
            return None
            
    except sqlite3.Error:
        return None

def delete_user(email):
    """Delete a user account."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE email = ?", (email,))
            
            if cursor.rowcount > 0:
                conn.commit()
                return True, "User deleted successfully"
            else:
                return False, "User not found"
                
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"

def update_password(email, new_password):
    """Update user password."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            new_hash = hash_password(new_password)
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE email = ?",
                (new_hash, email)
            )
            
            if cursor.rowcount > 0:
                conn.commit()
                return True, "Password updated successfully"
            else:
                return False, "User not found"
                
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"

def get_all_users():
    """Get all users (for admin purposes) - returns emails only for privacy."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email, created_at FROM users ORDER BY created_at DESC")
            return cursor.fetchall()
    except sqlite3.Error:
        return []

def validate_email(email):
    """Basic email validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Basic password validation."""
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    if len(password) > 128:
        return False, "Password is too long"
    return True, "Password is valid"

def admin_set_user_password(email, new_password):
    """Set a user's password by an admin. No old password verification needed."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            new_hash = hash_password(new_password)
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE email = ?",
                (new_hash, email)
            )

            if cursor.rowcount > 0:
                conn.commit()
                return True, "Password updated successfully by admin."
            else:
                # This case implies the user email does not exist, which shouldn't happen
                # if the admin panel is listing existing users.
                return False, "User not found. Password not updated."

    except sqlite3.Error as e:
        return False, f"Database error during admin password update: {str(e)}"

# Initialize database when module is imported
init_database()