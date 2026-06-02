import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = "corelabtech"
DATABASE_PATH = os.path.join(BASE_DIR, "data", "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "research", "papers")