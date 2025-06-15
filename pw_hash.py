from werkzeug.security import generate_password_hash

password = input("Enter the password to hash: ")
hashed_password = generate_password_hash(password)
print(f"Hashed password: {hashed_password}")