import sqlite3
import os
import shutil # For moving files
from datetime import datetime

class FileManager:
    def __init__(self, db_path='/app/data/database.db', upload_folder='uploads'): # Changed default db_path
        self.db_path = db_path
        self.upload_folder = upload_folder # This will be /app/uploads when run in Docker via app.py

        # Ensure the directory for the database file exists
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)

        os.makedirs(self.upload_folder, exist_ok=True) # upload_folder is base, user dirs created inside
        self.init_db()
    
    def init_db(self):
        """Initialize the files table"""
        # Ensure the data directory for the database exists again, just in case
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                upload_date TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                is_global INTEGER DEFAULT 0,
                FOREIGN KEY (user_email) REFERENCES users (email)
            )
        ''')
        # Add is_global column if it doesn't exist (for existing databases)
        try:
            cursor.execute("SELECT is_global FROM files LIMIT 1")
        except sqlite3.OperationalError:
            # Column does not exist, so add it
            cursor.execute("ALTER TABLE files ADD COLUMN is_global INTEGER DEFAULT 0")
            print("Added is_global column to files table.")

        conn.commit()
        conn.close()

    def _get_file_by_name(self, user_email, filename):
        """Helper to get file details by user_email and filename."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, file_path FROM files WHERE user_email = ? AND filename = ?',
            (user_email, filename)
        )
        file_data = cursor.fetchone()
        conn.close()
        return file_data

    def _get_user_specific_upload_dir(self, user_email):
        """ Returns the specific upload directory path for a user. """
        # Sanitize user_email to make it a valid directory name if necessary,
        # though emails are generally safe. For extreme cases, consider hashing or encoding.
        # Using raw email for directory name as per user request.
        user_dir = os.path.join(self.upload_folder, user_email)
        return user_dir

    def _generate_new_filepath(self, user_email, filename):
        """
        Generates a new unique filename and its full path within the user's specific directory
        if the original filename exists.
        Checks both DB (for user+filename combo) and filesystem (full path) for uniqueness.
        Returns (new_filename, new_full_path_for_user_file)
        """
        user_specific_dir = self._get_user_specific_upload_dir(user_email)
        # No need to call os.makedirs here, as add_file will do it before moving.
        # This function is about finding a unique name and path.

        base, ext = os.path.splitext(filename)
        counter = 1
        new_filename = filename # This is just the filename, not the full path yet

        # Check against DB for user + new_filename combo
        # And check filesystem for the full path: user_specific_dir + new_filename
        new_full_path_for_user_file = os.path.join(user_specific_dir, new_filename)

        while self._get_file_by_name(user_email, new_filename) or os.path.exists(new_full_path_for_user_file):
            new_filename = f"{base} ({counter}){ext}"
            new_full_path_for_user_file = os.path.join(user_specific_dir, new_filename)
            counter += 1
        return new_filename, new_full_path_for_user_file # Return new name and its full path

    def add_file(self, user_email, original_filename, temp_uploaded_path, action="default"):
        """
        Adds a file to the system. The file is initially at temp_uploaded_path.
        Manages moving the file to its final destination in self.upload_folder.
        Handles duplicates based on 'action'.
        original_filename is the filename as submitted by the user.
        temp_uploaded_path is the path where the file was temporarily saved by the upload handler.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Define these early for potential use in finally or error handling, though their values change
        final_physical_path = None
        moved_successfully = False

        try:
            existing_file_record = self._get_file_by_name(user_email, original_filename)
            final_filename = original_filename
            
            user_specific_upload_dir = self._get_user_specific_upload_dir(user_email)

            if existing_file_record:
                if action == "default":
                    conn.close()
                    return {"status": "duplicate", "filename": original_filename, "message": "File already exists."}

                elif action == "replace":
                    old_db_id, old_physical_path = existing_file_record
                    cursor.execute('DELETE FROM files WHERE id = ?', (old_db_id,))
                    if os.path.exists(old_physical_path):
                        try:
                            os.remove(old_physical_path)
                        except OSError as e:
                            print(f"Warning: Error deleting old physical file {old_physical_path}: {e}")
                    # The new file will replace the old one using the original_filename in the user's specific directory
                    final_physical_path = os.path.join(user_specific_upload_dir, final_filename)

                elif action == "keep_both":
                    # Generate new unique name and its full path within the user's directory
                    final_filename, final_physical_path = self._generate_new_filepath(user_email, original_filename)
                    # _generate_new_filepath already gives the full path including user_specific_upload_dir

                else:
                    conn.close()
                    return {"status": "error", "message": "Invalid action for duplicate file."}
            else: # No existing record, this is a new file (for this user)
                final_physical_path = os.path.join(user_specific_upload_dir, final_filename)

            # Ensure the user-specific directory exists before moving the file
            os.makedirs(user_specific_upload_dir, exist_ok=True)
            
            if not temp_uploaded_path or not os.path.exists(temp_uploaded_path):
                 conn.close()
                 return {"status": "error", "message": "Temporary file not found or not provided."}

            try:
                shutil.move(temp_uploaded_path, final_physical_path)
                moved_successfully = True
            except Exception as e:
                conn.close()
                return {"status": "error", "message": f"Failed to move file to destination '{final_physical_path}': {str(e)}"}

            # Add to database with the potentially new final_filename and its full user-specific path
            file_size = os.path.getsize(final_physical_path)
            upload_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                INSERT INTO files (user_email, filename, file_path, upload_date, file_size)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_email, final_filename, final_physical_path, upload_date, file_size))
            
            conn.commit()
            return {"status": "success", "filename": final_filename, "message": "File processed successfully."}

        except Exception as e:
            if conn: # ensure conn is defined
                conn.rollback()

            # If file was moved but DB operation failed, try to remove the moved file to prevent orphans,
            # unless it was a replace action where the original was already deleted.
            if moved_successfully and final_physical_path and os.path.exists(final_physical_path):
                if not (action == "replace" and existing_file_record):
                    try:
                        os.remove(final_physical_path)
                        print(f"Cleaned up {final_physical_path} after DB error.")
                    except OSError as ose:
                        print(f"Error cleaning up file {final_physical_path} after DB error: {ose}")

            # If the temp_uploaded_path still exists (because move failed or happened before move)
            # The Flask route or system should handle cleaning this temp file.
            # Here, we're just reporting the main error.
            return {"status": "error", "message": f"An unexpected error occurred: {str(e)}"}
        finally:
            if conn: # ensure conn is defined
                conn.close()
            # Ensure temp_uploaded_path is cleaned up if it wasn't moved and still exists.
            # This is tricky because Flask might auto-clean it.
            # For now, rely on Flask's behavior for temp files if not explicitly moved.


    def get_user_files(self, user_email, page=1, per_page=5):
        """Get files for a specific user with pagination"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get total number of files for the user
            cursor.execute(
                'SELECT COUNT(id) FROM files WHERE user_email = ?',
                (user_email,)
            )
            total_files = cursor.fetchone()[0]

            # Calculate offset
            offset = (page - 1) * per_page

            # Select is_global along with other file details
            cursor.execute('''
                SELECT id, filename, upload_date, file_size, is_global
                FROM files 
                WHERE user_email = ?
                ORDER BY upload_date DESC
                LIMIT ? OFFSET ?
            ''', (user_email, per_page, offset))
            
            files_data = cursor.fetchall() # Renamed to avoid conflict
            conn.close()
            
            # Convert to list of dictionaries for easier template usage
            file_list = []
            for row in files_data: # Use new variable name
                file_list.append({
                    'id': row[0],
                    'filename': row[1],
                    'upload_date': row[2],
                    'file_size': self.format_file_size(row[3]),
                    'is_global': bool(row[4]) # Convert 0/1 to True/False
                })
            
            return file_list, total_files
            
        except Exception as e:
            print(f"Error getting user files: {e}")
            return [], 0
    
    def get_file_info(self, file_id, requesting_user_email=None):
        """
        Get file information for a specific file.
        If the file is global, any logged-in user can access its info.
        If the file is not global, only the owner (matched by requesting_user_email) can access it.
        Returns file_info tuple or None if not found or access denied.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # Fetch all necessary fields including owner's email (user_email) and is_global status
            cursor.execute('''
                SELECT id, user_email, filename, file_path, upload_date, file_size, is_global
                FROM files 
                WHERE id = ?
            ''', (file_id,))
            
            file_data = cursor.fetchone()
            conn.close()

            if not file_data:
                return None # File not found

            # file_data structure: (id, owner_email, filename, file_path, upload_date, file_size, is_global_db_val)
            is_global_status = bool(file_data[6]) # is_global is at index 6
            owner_email = file_data[1]

            if is_global_status:
                # If file is global, any authenticated user (requesting_user_email is not None) can access.
                # Or, if we allow unauthenticated access to global files info (e.g. for a public link later),
                # this check might be removed or modified. For now, let's assume only logged-in users.
                if requesting_user_email:
                    return file_data
                else: # No requesting user, but file is global. Decide policy. For now, deny if no user.
                    return None # Or handle as per specific requirement for unauthenticated global access.
            else:
                # File is not global, so check ownership
                if requesting_user_email and requesting_user_email == owner_email:
                    return file_data
                else:
                    return None # Access denied (not owner of private file)
            
        except Exception as e:
            print(f"Error getting file info for file_id {file_id}: {e}")
            if conn:
                conn.close()
            return None
    
    def delete_file(self, file_id, user_email):
        """Delete a file from database and filesystem"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get file info first
            cursor.execute('''
                SELECT file_path FROM files 
                WHERE id = ? AND user_email = ?
            ''', (file_id, user_email))
            
            result = cursor.fetchone()
            if not result:
                conn.close()
                return False, "File not found or access denied"
            
            file_path = result[0]
            
            # Delete from database
            cursor.execute('''
                DELETE FROM files 
                WHERE id = ? AND user_email = ?
            ''', (file_id, user_email))
            
            if cursor.rowcount == 0:
                conn.close()
                return False, "File not found or access denied"
            
            conn.commit()
            conn.close()
            
            # Delete actual file
            if os.path.exists(file_path):
                os.remove(file_path)
            
            return True, "File deleted successfully"
            
        except Exception as e:
            return False, f"Error deleting file: {str(e)}"
    
    def search_files(self, user_email, query):
        """Search files by filename"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Search for files with filename containing the query
            cursor.execute('''
                SELECT id, filename, upload_date, file_size
                FROM files 
                WHERE user_email = ? AND filename LIKE ?
                ORDER BY upload_date DESC
            ''', (user_email, f'%{query}%'))
            
            files = cursor.fetchall()
            conn.close()
            
            # Convert to list of dictionaries
            file_list = []
            for file_data in files:
                file_list.append({
                    'id': file_data[0],
                    'filename': file_data[1],
                    'upload_date': file_data[2],
                    'file_size': self.format_file_size(file_data[3])
                })
            
            return file_list
            
        except Exception as e:
            print(f"Error searching files: {e}")
            return []
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}"

    def set_file_global_status(self, file_id, user_email, is_global_flag):
        """
        Sets the is_global status for a file.
        Only the owner of the file can change its global status.
        is_global_flag should be a boolean (True for global, False for not global).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # First, verify ownership
            cursor.execute("SELECT user_email FROM files WHERE id = ?", (file_id,))
            result = cursor.fetchone()

            if not result:
                conn.close()
                return False, "File not found."

            if result[0] != user_email:
                conn.close()
                return False, "Access denied. You are not the owner of this file."

            # Ownership confirmed, update the status
            new_status = 1 if is_global_flag else 0
            cursor.execute("UPDATE files SET is_global = ? WHERE id = ?", (new_status, file_id))
            conn.commit()

            if cursor.rowcount > 0:
                status_text = "global" if is_global_flag else "private"
                conn.close()
                return True, f"File status successfully updated to {status_text}."
            else:
                # Should not happen if file was found and ownership confirmed,
                # but good to have a fallback.
                conn.close()
                return False, "Failed to update file status (file ID might be incorrect after check)."

        except sqlite3.Error as e:
            if conn:
                conn.rollback() # Rollback in case of error during transaction
                conn.close()
            return False, f"Database error: {str(e)}"
        finally:
            if conn and conn.in_transaction: # Ensure connection is closed if error happened before close
                 conn.close()
            elif conn: # Ensure connection is closed even if not in transaction from the start of try
                conn.close()

    def get_global_files(self, page=1, per_page=5):
        """Get all global files with pagination."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get total number of global files
            cursor.execute("SELECT COUNT(id) FROM files WHERE is_global = 1")
            total_global_files = cursor.fetchone()[0]

            # Calculate offset
            offset = (page - 1) * per_page

            # Fetch paginated global files, including the uploader's email
            cursor.execute('''
                SELECT id, filename, upload_date, file_size, user_email
                FROM files
                WHERE is_global = 1
                ORDER BY upload_date DESC
                LIMIT ? OFFSET ?
            ''', (per_page, offset))

            files_data = cursor.fetchall()
            conn.close()

            file_list = []
            for row in files_data:
                file_list.append({
                    'id': row[0],
                    'filename': row[1],
                    'upload_date': row[2],
                    'file_size': self.format_file_size(row[3]),
                    'user_email': row[4] # Uploader's email
                })

            return file_list, total_global_files

        except Exception as e:
            print(f"Error getting global files: {e}")
            if conn:
                conn.close()
            return [], 0