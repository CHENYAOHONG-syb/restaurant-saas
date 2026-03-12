import sqlite3

conn = sqlite3.connect("database.db")
c = conn.cursor()

c.execute("""
CREATE TABLE restaurants(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT
)
""")

c.execute("""
CREATE TABLE menu(
id INTEGER PRIMARY KEY AUTOINCREMENT,
restaurant_id INTEGER,
name TEXT,
price REAL
)
""")

c.execute("""
CREATE TABLE orders(
id INTEGER PRIMARY KEY AUTOINCREMENT,
restaurant_id INTEGER,
food_id INTEGER,
table_number INTEGER,
status TEXT
)
""")
# 购物车表
c.execute("""
CREATE TABLE IF NOT EXISTS cart (
id INTEGER PRIMARY KEY AUTOINCREMENT,
food_id INTEGER,
table_number INTEGER
)
""")
c.execute("INSERT INTO restaurants VALUES (1,'Demo Restaurant')")

c.execute("INSERT INTO menu VALUES (1,1,'Fried Rice',8)")
c.execute("INSERT INTO menu VALUES (2,1,'Noodles',7)")
c.execute("INSERT INTO menu VALUES (3,1,'Milk Tea',5)")

conn.commit()
conn.close()

print("Database created")
