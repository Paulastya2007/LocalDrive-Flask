#!/usr/bin/env python3
"""
Database management script for the Flask authentication system.
Run this script to perform database operations.
"""

import sys
from utils.auth import (
    init_database, create_user, delete_user, get_all_users, 
    get_user_info, update_password, validate_email, validate_password
)

def show_help():
    """Display help information."""
    print("""
Database Manager for Flask Auth System
=====================================

Usage: python db_manager.py [command] [arguments]

Commands:
  init              Initialize the database
  create <email>    Create a new user (will prompt for password)
  delete <email>    Delete a user
  list              List all users
  info <email>      Show user information
  password <email>  Update user password
  help              Show this help message

Examples:
  python db_manager.py init
  python db_manager.py create user@example.com
  python db_manager.py list
  python db_manager.py delete user@example.com
    """)

def create_user_interactive(email):
    """Create a user with interactive password input."""
    if not validate_email(email):
        print(f"Error: Invalid email format: {email}")
        return
    
    import getpass
    password = getpass.getpass("Enter password: ")
    
    # Validate password
    valid, message = validate_password(password)
    if not valid:
        print(f"Error: {message}")
        return
    
    success, message = create_user(email, password)
    if success:
        print(f"Success: {message}")
    else:
        print(f"Error: {message}")

def delete_user_confirm(email):
    """Delete a user with confirmation."""
    user_info = get_user_info(email)
    if not user_info:
        print(f"Error: User {email} not found")
        return
    
    confirm = input(f"Are you sure you want to delete user '{email}'? (y/N): ")
    if confirm.lower() == 'y':
        success, message = delete_user(email)
        if success:
            print(f"Success: {message}")
        else:
            print(f"Error: {message}")
    else:
        print("Operation cancelled")

def list_users():
    """List all users."""
    users = get_all_users()
    if not users:
        print("No users found")
        return
    
    print("\nRegistered Users:")
    print("-" * 50)
    for email, created_at in users:
        print(f"Email: {email}")
        print(f"Created: {created_at}")
        print("-" * 50)

def show_user_info(email):
    """Show detailed user information."""
    user_info = get_user_info(email)
    if not user_info:
        print(f"Error: User {email} not found")
        return
    
    print(f"\nUser Information:")
    print(f"ID: {user_info['id']}")
    print(f"Email: {user_info['email']}")
    print(f"Created: {user_info['created_at']}")

def update_user_password(email):
    """Update user password."""
    user_info = get_user_info(email)
    if not user_info:
        print(f"Error: User {email} not found")
        return
    
    import getpass
    new_password = getpass.getpass("Enter new password: ")
    
    # Validate password
    valid, message = validate_password(new_password)
    if not valid:
        print(f"Error: {message}")
        return
    
    success, message = update_password(email, new_password)
    if success:
        print(f"Success: {message}")
    else:
        print(f"Error: {message}")

def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'help':
        show_help()
    elif command == 'init':
        init_database()
        print("Database initialized successfully")
    elif command == 'create':
        if len(sys.argv) < 3:
            print("Error: Email required")
            print("Usage: python db_manager.py create <email>")
            return
        create_user_interactive(sys.argv[2])
    elif command == 'delete':
        if len(sys.argv) < 3:
            print("Error: Email required")
            print("Usage: python db_manager.py delete <email>")
            return
        delete_user_confirm(sys.argv[2])
    elif command == 'list':
        list_users()
    elif command == 'info':
        if len(sys.argv) < 3:
            print("Error: Email required")
            print("Usage: python db_manager.py info <email>")
            return
        show_user_info(sys.argv[2])
    elif command == 'password':
        if len(sys.argv) < 3:
            print("Error: Email required")
            print("Usage: python db_manager.py password <email>")
            return
        update_user_password(sys.argv[2])
    else:
        print(f"Error: Unknown command '{command}'")
        show_help()

if __name__ == '__main__':
    main()