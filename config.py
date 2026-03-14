import os

class Config:

    SECRET_KEY = os.getenv("SECRET_KEY","dev")

    DATABASE = "database.db"