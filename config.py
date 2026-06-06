import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'codeforge-secret-key-2024-xK9mP2nQ')
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/flask_sessions'

    # Razorpay (editable from admin panel)
    RAZORPAY_KEY_ID = "rzp_test_YOUR_KEY_ID"
    RAZORPAY_KEY_SECRET = "YOUR_KEY_SECRET"

    # Firebase (frontend only — for template injection)
    FIREBASE_CONFIG = {
        "apiKey": "AIzaSyD3ML9k7RSbeoVze0su8PoE69llfgeqr1k",
        "authDomain": "codeforge-d3aa2.firebaseapp.com",
        "databaseURL": "https://codeforge-d3aa2-default-rtdb.firebaseio.com",
        "projectId": "codeforge-d3aa2",
        "storageBucket": "codeforge-d3aa2.firebasestorage.app",
        "messagingSenderId": "907268826856",
        "appId": "1:907268826856:web:aedb8eb1c674bad9ab4b5d",
        "measurementId": "G-BYDW3TQVV7"
    }

    # Authorized admin emails — sirf yahi log /admin panel access kar sakte hain
    SUPER_ADMINS = [
        "mdmajidansari33640@gmail.com",
    ]
