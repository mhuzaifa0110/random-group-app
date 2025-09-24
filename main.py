from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import random
import sqlite3

app = FastAPI()

# Database setup
conn = sqlite3.connect("groups.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    reg_no TEXT NOT NULL UNIQUE,
    group_size INTEGER DEFAULT 2
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS past_pairs (
    user1 TEXT,
    user2 TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    group_no INTEGER,
    members TEXT
)
""")
conn.commit()

class RegisterUser(BaseModel):
    name: str
    reg_no: str
    group_size: int

class GroupRequest(BaseModel):
    title: str
    size: int

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>Random Group App for IMR Assignments</title>
            <style>
                body { font-family: Arial; margin: 20px; }
                .container { display: flex; gap: 40px; }
                .column { flex: 1; }
                h2 { margin-top: 20px; }
            </style>
        </head>
        <body>
            <h1>Random Group App for IMR Assignments</h1>
            
            <form id="registerForm">
                <input type="text" id="name" placeholder="Name" required>
                <input type="text" id="reg_no" placeholder="Registration No" required>
                <select id="groupSize">
                    <option value="2">Group of 2</option>
                    <option value="3">Group of 3</option>
                </select>
                <button type="submit">Register / Update</button>
            </form>

            <div class="container">
                <div class="column">
                    <h2>Registered Users</h2>
                    <ul id="usersList"></ul>
                </div>

                <div class="column">
                    <div id="controllerPanel" style="display:none;">
                        <h2>Controller Panel</h2>
                        <input type="text" id="groupTitle" placeholder="Enter Group Title">
                        <button onclick="makeGroups()">Make Groups</button>
                    </div>

                    <h2>Groups</h2>
                    <div id="groups"></div>
                </div>
            </div>

            <script>
                async function fetchUsers() {
                    let res = await fetch('/users');
                    let data = await res.json();
                    let list = document.getElementById('usersList');
                    list.innerHTML = '';
                    data.forEach(u => {
                        let li = document.createElement('li');
                        li.innerText = u.name + " (" + u.reg_no + ") - prefers group of " + u.group_size;
                        list.appendChild(li);
                    });
                }

                async function fetchGroups() {
                    let res = await fetch('/groups');
                    let data = await res.json();
                    let div = document.getElementById('groups');
                    div.innerHTML = '';
                    data.forEach(glist => {
                        let h3 = document.createElement('h3');
                        h3.innerText = glist.title;
                        div.appendChild(h3);

                        glist.groups.forEach((g, i) => {
                            let p = document.createElement('p');
                            p.innerText = "Group " + (i+1) + ": " + g.join(", ");
                            div.appendChild(p);
                        });
                    });
                }

                document.getElementById('registerForm').addEventListener('submit', async (e) => {
                    e.preventDefault();
                    let name = document.getElementById('name').value;
                    let reg_no = document.getElementById('reg_no').value;
                    let group_size = document.getElementById('groupSize').value;

                    let res = await fetch('/register', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({name, reg_no, group_size: parseInt(group_size)})
                    });
                    let msg = await res.json();
                    alert(msg.message || msg.detail);

                    if (reg_no === "98100") {
                        document.getElementById('controllerPanel').style.display = 'block';
                    }

                    fetchUsers();
                    fetchGroups();
                });

                async function makeGroups() {
                    let title = document.getElementById('groupTitle').value;
                    if (!title) {
                        alert("Please enter a group title before making groups!");
                        return;
                    }
                    let res = await fetch('/make_groups', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({title, size: 2})
                    });
                    let data = await res.json();
                    if (data.detail) {
                        alert(data.detail);
                        return;
                    }
                    fetchGroups();
                }

                // Load users and groups on page start
                fetchUsers();
                fetchGroups();
            </script>
        </body>
    </html>
    """

@app.post("/register")
def register_user(data: RegisterUser):
    # Prevent controller from being registered
    if data.name.lower() == "controller" and data.reg_no == "98100":
        raise HTTPException(status_code=400, detail="Controller cannot be registered as a user")

    try:
        cursor.execute("INSERT INTO users (name, reg_no, group_size) VALUES (?, ?, ?)", 
                       (data.name, data.reg_no, data.group_size))
        conn.commit()
        return {"message": "Registered successfully"}
    except sqlite3.IntegrityError:
        cursor.execute("UPDATE users SET name=?, group_size=? WHERE reg_no=?", 
                       (data.name, data.group_size, data.reg_no))
        conn.commit()
        return {"message": "Updated successfully"}

@app.get("/users")
def list_users():
    cursor.execute("SELECT name, reg_no, group_size FROM users")
    rows = cursor.fetchall()
    return [{"name": r[0], "reg_no": r[1], "group_size": r[2]} for r in rows]

@app.delete("/delete_user/{reg_no}")
def delete_user(reg_no: str):
    # Only controller can delete
    if reg_no == "98100":
        raise HTTPException(status_code=400, detail="Controller cannot be deleted")

    cursor.execute("DELETE FROM users WHERE reg_no = ?", (reg_no,))
    conn.commit()
    return {"message": f"User with reg_no {reg_no} deleted successfully"}

@app.post("/make_groups")
def make_groups(req: GroupRequest):
    if not req.title:
        raise HTTPException(status_code=400, detail="Title is required")

    # Get users with their names + reg_no
    cursor.execute("SELECT name, reg_no, group_size FROM users")
    users = cursor.fetchall()
    if not users:
        raise HTTPException(status_code=400, detail="No users registered")

    # Use majority preferred group size
    sizes = [u[2] for u in users]
    size = max(set(sizes), key=sizes.count) if sizes else req.size

    regnos = [u[1] for u in users]
    random.shuffle(regnos)

    groups = []
    used_pairs = set()
    cursor.execute("SELECT user1, user2 FROM past_pairs")
    for u1, u2 in cursor.fetchall():
        used_pairs.add(tuple(sorted([u1, u2])))

    i = 0
    while i < len(regnos):
        group = regnos[i:i+size]
        valid = True
        for j in range(len(group)):
            for k in range(j+1, len(group)):
                if tuple(sorted([group[j], group[k]])) in used_pairs:
                    valid = False
                    break
        if valid:
            display_group = []
            for reg in group:
                cursor.execute("SELECT name FROM users WHERE reg_no=?", (reg,))
                name = cursor.fetchone()[0]
                display_group.append(f"{name} ({reg})")

            groups.append(display_group)

            for j in range(len(group)):
                for k in range(j+1, len(group)):
                    cursor.execute("INSERT INTO past_pairs (user1, user2) VALUES (?, ?)", (group[j], group[k]))
            conn.commit()
            i += size
        else:
            random.shuffle(regnos)
            groups = []
            i = 0

    # Save or update groups in DB
    cursor.execute("DELETE FROM groups WHERE title=?", (req.title,))
    for idx, g in enumerate(groups, start=1):
        cursor.execute("INSERT INTO groups (title, group_no, members) VALUES (?, ?, ?)", 
                       (req.title, idx, ", ".join(g)))
    conn.commit()

    return {"groups": groups, "title": req.title}

@app.get("/groups")
def get_groups():
    cursor.execute("SELECT title, group_no, members FROM groups ORDER BY id")
    rows = cursor.fetchall()

    grouped = {}
    for title, group_no, members in rows:
        if title not in grouped:
            grouped[title] = []
        grouped[title].append(members.split(", "))

    return [{"title": t, "groups": g} for t, g in grouped.items()]
