from streamlit_authenticator.utilities.hasher import Hasher


passwords_to_hash = ['student_pass_123', 'teacher_pass_456']


hashed_passwords = Hasher.hash_list(passwords_to_hash)

print("\n--- Copy these hashed strings into your config.yaml ---")
for text, hashed in zip(passwords_to_hash, hashed_passwords):
    print(f"Plain: {text}  -->  Hash: {hashed}")