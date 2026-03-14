import sqlite3

conn = sqlite3.connect("database.db")
c = conn.cursor()

# restaurants
c.execute("""
CREATE TABLE IF NOT EXISTS restaurants(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
slug TEXT,
owner_id INTEGER
)
""")

# users
c.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT UNIQUE,
password TEXT
)
""")

# menu
c.execute("""
CREATE TABLE IF NOT EXISTS menu(
id INTEGER PRIMARY KEY AUTOINCREMENT,
restaurant_id INTEGER,
name TEXT,
price REAL,
category TEXT,
image TEXT
)
""")

# orders
c.execute("""
CREATE TABLE IF NOT EXISTS orders(
id INTEGER PRIMARY KEY AUTOINCREMENT,
restaurant_id INTEGER,
table_number INTEGER,
status TEXT,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# order items
c.execute("""
CREATE TABLE IF NOT EXISTS order_items(
id INTEGER PRIMARY KEY AUTOINCREMENT,
order_id INTEGER,
food_id INTEGER,
qty INTEGER
)
""")

# cart
c.execute("""
CREATE TABLE IF NOT EXISTS cart(
id INTEGER PRIMARY KEY AUTOINCREMENT,
restaurant_id INTEGER,
food_id INTEGER,
table_number INTEGER,
qty INTEGER
)
""")

# inventory
c.execute("""
CREATE TABLE IF NOT EXISTS inventory(
id INTEGER PRIMARY KEY AUTOINCREMENT,
restaurant_id INTEGER,
name TEXT,
stock INTEGER
)
""")

# categories
c.execute("""
CREATE TABLE IF NOT EXISTS categories(
id INTEGER PRIMARY KEY AUTOINCREMENT,
restaurant_id INTEGER,
name TEXT
)
""")

# demo restaurant
c.execute("INSERT INTO restaurants (name) VALUES ('Demo Restaurant')")

# demo menu
c.execute("INSERT INTO menu (restaurant_id,name,price) VALUES (1,'Fried Rice',8)")
c.execute("INSERT INTO menu (restaurant_id,name,price) VALUES (1,'Noodles',7)")
c.execute("INSERT INTO menu (restaurant_id,name,price) VALUES (1,'Milk Tea',5)")

conn.commit()
conn.close()

print("Database created successfully")