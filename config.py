import os

class Config:

    SECRET_KEY = os.getenv("SECRET_KEY","dev")

    SQLALCHEMY_DATABASE_URI = "postgresql://user:password@host:5432/db"