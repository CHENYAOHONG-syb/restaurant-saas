import sqlite3
from flask import g

DATABASE = "database.db"

def get_db():
    
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row

    return conn


def close_db(exception=None):

    db = g.pop("db", None)

    if db is not None:
        db.close()
        