import jwt
from functools import wraps
from flask import request, jsonify
from modules.jwt_module.encryption_helper import EncryptionHelper

SECRET_KEY = "AY4B42SH34MC5XL9UR64AVRM4JR9QZK33VXFZ6DUE02UML1319AWBSYN7423NWJN"

def decrypt_payload(payload):
    """
    Function to decrypt each field in the JWT payload using the decryption helper.
    """
    decrypted_payload = {}
    for key, value in payload.items():
        try:
            # Base64 decode the key and value (add padding if necessary)
            decrypted_key = EncryptionHelper.decrypt(base64_pad(key)) if isinstance(key, str) else key
            decrypted_value = EncryptionHelper.decrypt(base64_pad(value)) if isinstance(value, str) else value
            
            # Add to the decrypted payload dictionary
            decrypted_payload[decrypted_key] = decrypted_value
        except Exception as e:
            print(f"Error while decrypting key-value pair ({key}: {value}): {str(e)}")
            decrypted_payload[None] = value  # Leave the value as is if it fails
    return decrypted_payload

def base64_pad(data):
    """
    Add padding to base64 string if necessary.
    """
    return data + '=' * (4 - len(data) % 4)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization']

        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            # Remove "Bearer" if it exists in the token
            token = token.split()[1] if "Bearer " in token else token

            # Decode the JWT token using the correct secret key
            decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            
            # Decrypt the payload fields
            decrypted_payload = decrypt_payload(decoded_token)
            print(f"Decrypted Payload: {decrypted_payload}")

            # Attach the decrypted payload to the request context
            request.tenant = decrypted_payload.get('tenant')
            request.role = decrypted_payload.get('role')

        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401

        except jwt.InvalidTokenError as e:
            return jsonify({'message': f'Invalid token: {str(e)}'}), 401

        return f(*args, **kwargs)

    return decorated