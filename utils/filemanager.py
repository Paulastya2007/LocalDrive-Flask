import sqlite3
import os
from datetime import datetime

class FileManager:
    def __init__(self, db_path='database.db'):
        self.db_path = db_path
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
    
    def add_file(self, user_email, filename, file_path):
        """Add a new file to the database"""
        try:
            # Get file size
            file_size = os.path.getsize(file_path)
            upload_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if file with same name already exists for this user
            cursor.execute(
                'SELECT id FROM files WHERE user_email = ? AND filename = ?',
                (user_email, filename)
            )
            
            if cursor.fetchone():
                conn.close()
                return False, "A file with this name already exists"
            
            # Insert new file record
            cursor.execute('''
                INSERT INTO files (user_email, filename, file_path, upload_date, file_size)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_email, filename, file_path, upload_date, file_size))
            
            conn.commit()
            conn.close()
            return True, "File added successfully"
            
        except Exception as e:
            return False, f"Database error: {str(e)}"
    
    def get_user_files(self, user_email):
        """Get all files for a specific user"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, filename, upload_date, file_size
                FROM files 
                WHERE user_email = ?
                ORDER BY upload_date DESC
            ''', (user_email,))
            
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
            
            return file_list
            
        except Exception as e:
            print(f"Error getting user files: {e}")
            return []
    
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