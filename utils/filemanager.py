import sqlite3
import os
import shutil # For moving files
from datetime import datetime

class FileManager:
    def __init__(self, db_path='database.db', upload_folder='uploads'):
        self.db_path = db_path
        self.upload_folder = upload_folder
        os.makedirs(self.upload_folder, exist_ok=True)
        self.init_db()
    
    def init_db(self):
        """Initialize the files table"""
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
                FOREIGN KEY (user_email) REFERENCES users (email)
            )
        ''')
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

    def _generate_new_filepath(self, user_email, filename):
        """
        Generates a new unique filename and its full path if the original filename exists.
        Checks both DB and filesystem for uniqueness.
        Returns (new_filename, new_full_path)
        """
        base, ext = os.path.splitext(filename)
        counter = 1
        new_filename = filename
        new_full_path = os.path.join(self.upload_folder, new_filename)

        while self._get_file_by_name(user_email, new_filename) or os.path.exists(new_full_path):
            new_filename = f"{base} ({counter}){ext}"
            new_full_path = os.path.join(self.upload_folder, new_filename)
            counter += 1
        return new_filename, new_full_path

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
            final_filename = original_filename # Default final name
            
            # Determine the final physical path based on action
            if action == "keep_both" and existing_file_record:
                # If keeping both and original exists, generate new name and path
                final_filename, final_physical_path = self._generate_new_filepath(user_email, original_filename)
            else:
                # For "default" (no conflict yet), "replace", or "default" (conflict but action is not keep_both)
                final_physical_path = os.path.join(self.upload_folder, final_filename)


            if existing_file_record:
                if action == "default":
                    conn.close()
                    # temp_uploaded_path should be cleaned by caller if user cancels upload process
                    return {"status": "duplicate", "filename": original_filename, "message": "File already exists."}

                elif action == "replace":
                    old_db_id, old_physical_path = existing_file_record
                    cursor.execute('DELETE FROM files WHERE id = ?', (old_db_id,))
                    if os.path.exists(old_physical_path):
                        try:
                            os.remove(old_physical_path)
                        except OSError as e:
                            print(f"Warning: Error deleting old physical file {old_physical_path}: {e}")
                    # final_filename and final_physical_path are already correct for replacing with original_filename

                elif action == "keep_both":
                    # final_filename and final_physical_path were already determined above
                    pass # Proceed to move and add

                else:
                    conn.close()
                    return {"status": "error", "message": "Invalid action for duplicate file."}
            
            # If temp_uploaded_path is None or empty, it means the file wasn't provided (e.g. programmatic error)
            if not temp_uploaded_path or not os.path.exists(temp_uploaded_path):
                 conn.close()
                 return {"status": "error", "message": "Temporary file not found or not provided."}


            # Move the uploaded file from temp_uploaded_path to final_physical_path
            try:
                # Ensure destination directory exists (should be covered by __init__, but good practice)
                os.makedirs(os.path.dirname(final_physical_path), exist_ok=True)
                shutil.move(temp_uploaded_path, final_physical_path)
                moved_successfully = True # Mark that the file has been moved
            except Exception as e:
                conn.close()
                return {"status": "error", "message": f"Failed to move file to destination: {str(e)}"}

            # Add to database
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

            cursor.execute('''
                SELECT id, filename, upload_date, file_size
                FROM files 
                WHERE user_email = ?
                ORDER BY upload_date DESC
                LIMIT ? OFFSET ?
            ''', (user_email, per_page, offset))
            
            files = cursor.fetchall()
            conn.close()
            
            # Convert to list of dictionaries for easier template usage
            file_list = []
            for file_data in files:
                file_list.append({
                    'id': file_data[0],
                    'filename': file_data[1],
                    'upload_date': file_data[2],
                    'file_size': self.format_file_size(file_data[3])
                })
            
            return file_list, total_files
            
        except Exception as e:
            print(f"Error getting user files: {e}")
            return [], 0
    
    def get_file_info(self, file_id, user_email):
        """Get file information for a specific file and user"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_email, filename, file_path, upload_date, file_size
                FROM files 
                WHERE id = ? AND user_email = ?
            ''', (file_id, user_email))
            
            file_info = cursor.fetchone()
            conn.close()
            return file_info
            
        except Exception as e:
            print(f"Error getting file info: {e}")
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