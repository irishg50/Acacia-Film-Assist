from werkzeug.security import generate_password_hash

def create_password_hash(password):
    """Create a password hash using Werkzeug's generate_password_hash"""
    return generate_password_hash(password)

if __name__ == "__main__":
    # Get password input from user
    password = input("Enter the password to encrypt: ")
    
    # Generate and print the hash
    hashed_password = create_password_hash(password)
    print("\nPassword Hash:")
    print(hashed_password)