import base64
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util.Padding import unpad

secret_key = "Lydi@Lawencon"
salt = "@lbertLinovHR"

class EncryptionHelper:
    @staticmethod
    def decrypt(str_to_decrypt):
        try:
            # Ensure that the Base64 string is correctly padded
            str_to_decrypt = EncryptionHelper.add_base64_padding(str_to_decrypt)

            # Initialize the decryption key and IV (Initialization Vector)
            iv = b'\x00' * 16
            key = PBKDF2(secret_key, salt.encode(), dkLen=32, count=65536)

            # Create the AES cipher for decryption
            cipher = AES.new(key, AES.MODE_CBC, iv)

            # Decode the encrypted Base64 string
            encrypted_data = base64.b64decode(str_to_decrypt)

            # Decrypt and unpad the data
            decrypted_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)

            # Return the decrypted string
            return decrypted_data.decode('utf-8')

        except Exception as e:
            print(f"Error while decrypting: {str(e)}")
            return None

    @staticmethod
    def add_base64_padding(data):
        """Ensure the Base64 string is padded to the correct length."""
        return data + '=' * (4 - len(data) % 4)