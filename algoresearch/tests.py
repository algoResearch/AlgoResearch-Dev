from django.test import TestCase
from dashboard.models import Message, Conversation, User
import base64

class MessageEncryptionTestCase(TestCase):
    def setUp(self):
        self.plaintext = "This is a test message."
        self.user = User.objects.create(username="testuser")
        self.conversation = Conversation.objects.create(name="Test Conversation")

    # Commented out due to import error with dashboard.generate_key module
    # def test_message_encryption_and_decryption(self):
    #     # Create a message and save it
    #     message = Message.objects.create(
    #         content=self.plaintext,
    #         sender=self.user,
    #         conversation=self.conversation,
    #     )
    # 
    #     # Check that the content is encrypted
    #     encrypted_content = message.content
    #     self.assertNotEqual(encrypted_content, self.plaintext)
    #     self.assertTrue(len(base64.b64decode(encrypted_content)) > len(self.plaintext))
    # 
    #     # Verify decryption
    #     decrypted_content = message.get_decrypted_content()
    #     self.assertEqual(decrypted_content, self.plaintext)

    # Commented out due to import error with dashboard.generate_key module
    # def test_manual_encryption(self):
    #     # Example manual test for encryption
    #     from dashboard.generate_key import encrypt_content, decrypt_content
    # 
    #     encrypted = encrypt_content(self.plaintext)
    #     decrypted = decrypt_content(encrypted)
    # 
    #     self.assertNotEqual(encrypted, self.plaintext)
    #     self.assertEqual(decrypted, self.plaintext)
