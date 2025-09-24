from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import random
import sqlite3

app = FastAPI()

# Root endpoint (homepage)
@app.get("/")
def home():
    return {"message": "Random Group App is running. Go to /docs to try the API."}

# Database setup
conn = sqlite3.connect("groups.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    reg_no TEXT NOT NULL UNIQUE
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS past_pairs (
    user1 TEXT,
    user2 TEXT
)
""")
conn.commit()

class RegisterUser(BaseModel):
    name: str
    reg_no: str

class GroupRequest(BaseModel):
    size: int  # group size 2 or 3

@app.post("/register")
def register_user(data: RegisterUser):
    try:
        cursor.execute("INSERT INTO users (name, reg_no) VALUES (?, ?)", (data.name, data.reg_no))
        conn.commit()
        return {"message": "Registered successfully"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Registration number already exists")

@app.get("/users")
def list_users():
    cursor.execute("SELECT name, reg_no FROM users")
    rows = cursor.fetchall()
    return [{"name": r[0], "reg_no": r[1]} for r in rows]

@app.post("/make_groups")
def make_groups(req: GroupRequest):
    cursor.execute("SELECT reg_no FROM users")
    users = [row[0] for row in cursor.fetchall()]
    random.shuffle(users)

    groups = []
    used_pairs = set()
    cursor.execute("SELECT user1, user2 FROM past_pairs")
    for u1, u2 in cursor.fetchall():
        used_pairs.add(tuple(sorted([u1, u2])))

    i = 0
    while i < len(users):
        group = users[i:i+req.size]
        # check for repetition
        valid = True
        for j in range(len(group)):
            for k in range(j+1, len(group)):
                if tuple(sorted([group[j], group[k]])) in used_pairs:
                    valid = False
                    break
        if valid:
            groups.append(group)
            for j in range(len(group)):
                for k in range(j+1, len(group)):
                    cursor.execute("INSERT INTO past_pairs (user1, user2) VALUES (?, ?)", (group[j], group[k]))
            conn.commit()
            i += req.size
        else:
            random.shuffle(users)  # reshuffle if invalid
            groups = []
            i = 0

    return {"groups": groups}
