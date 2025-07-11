# generate_admin_hash.py
import hashlib
import getpass
import os

def generate_sha256_hash(password):
    """Generates a SHA256 hash for the given password."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def update_env_file(key, value):
    """Updates or appends a key-value pair to a .env file in the current directory."""
    env_file = '.env'
    lines = []
    key_found = False

    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            lines = f.readlines()

    # Ensure there's a newline before adding the new key if the file is not empty and doesn't end with one
    if lines and not lines[-1].endswith('\n') and not key_found:
      # Check if we are about to write the key or if it's already there.
      # This logic is tricky because we rewrite the whole file.
      # A simpler approach for append:
      pass # Handled by the loop logic more or less

    with open(env_file, 'w') as f:
        processed_key = False
        for line in lines:
            if line.startswith(key + '='):
                f.write(f"{key}={value}\n")
                processed_key = True
            else:
                f.write(line)
        if not processed_key:
            if lines and not lines[-1].endswith('\n'): # if file has content and no trailing newline
                 f.write('\n')
            f.write(f"{key}={value}\n")


if __name__ == "__main__":
    print("Admin Password Hash Generator")
    print("-----------------------------")

    # Get password securely
    password = getpass.getpass("Enter the admin password: ")
    confirm_password = getpass.getpass("Confirm the admin password: ")

    if password != confirm_password:
        print("Passwords do not match. Exiting.")
    elif not password:
        print("Password cannot be empty. Exiting.")
    else:
        hashed_password = generate_sha256_hash(password)
        print(f"\nGenerated SHA256 Hash: {hashed_password}")

        update_choice = input("Do you want to update/create a .env file with this hash for ADMIN_PASSWORD_HASH? (yes/no): ").strip().lower()
        if update_choice == 'yes':
            update_env_file('ADMIN_PASSWORD_HASH', hashed_password)
            print(f"'.env' file has been updated with ADMIN_PASSWORD_HASH.")
            print("Please ensure your application loads environment variables from '.env' (e.g., using python-dotenv).")
        else:
            print("'.env' file not updated. Please set the environment variable manually if needed.")
