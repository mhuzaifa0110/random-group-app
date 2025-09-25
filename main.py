from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from google.cloud import firestore
import random
import os

# Initialize Firebase
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "firebase-key.json"
db = firestore.Client()

app = FastAPI()

# ---------- MODELS ----------
class RegisterUser(BaseModel):
    name: str
    reg_no: str
    group_size: int

class GroupRequest(BaseModel):
    title: str
    size: int

# ---------- FIREBASE HELPERS ----------
def get_setting(key: str):
    doc = db.collection("settings").document(key).get()
    if doc.exists:
        return doc.to_dict().get("value")
    return None

def set_setting(key: str, value: str):
    db.collection("settings").document(key).set({"value": value})

# Initialize settings on first run
if get_setting("registration_open") is None:
    set_setting("registration_open", "1")

# ---------- HTML UI ----------
@app.get("/", response_class=HTMLResponse)
def home():
    return open("index.html").read()

# ---------- REGISTER USER ----------
@app.post("/register")
def register_user(data: RegisterUser):
    if data.name.lower() == "controller" and data.reg_no == "98100":
        raise HTTPException(status_code=400, detail="Controller cannot be registered as a user")

    if get_setting("registration_open") != "1":
        raise HTTPException(status_code=403, detail="Registration is currently closed")

    doc_ref = db.collection("users").document(data.reg_no)
    if doc_ref.get().exists:
        doc_ref.update({"name": data.name, "group_size": data.group_size})
        return {"message": "Updated successfully"}
    else:
        doc_ref.set({"name": data.name, "reg_no": data.reg_no, "group_size": data.group_size})
        return {"message": "Registered successfully"}

# ---------- LIST USERS ----------
@app.get("/users")
def list_users():
    users = db.collection("users").stream()
    return [u.to_dict() for u in users]

# ---------- DELETE USER ----------
@app.delete("/delete_user/{reg_no}")
def delete_user(reg_no: str):
    if reg_no == "98100":
        raise HTTPException(status_code=400, detail="Controller cannot be deleted")

    db.collection("users").document(reg_no).delete()
    return {"message": f"User with reg_no {reg_no} deleted successfully"}

# ---------- TOGGLE REGISTRATION ----------
@app.post("/toggle_registration")
def toggle_registration():
    current = get_setting("registration_open")
    new_value = "0" if current == "1" else "1"
    set_setting("registration_open", new_value)
    status = "opened" if new_value == "1" else "closed"
    return {"message": f"Registration has been {status}"}

# ---------- MAKE GROUPS ----------
@app.post("/make_groups")
def make_groups(req: GroupRequest):
    if not req.title:
        raise HTTPException(status_code=400, detail="Title is required")

    users_ref = db.collection("users").stream()
    users = [u.to_dict() for u in users_ref]
    if not users:
        raise HTTPException(status_code=400, detail="No users registered")

    sizes = [u["group_size"] for u in users]
    size = max(set(sizes), key=sizes.count) if sizes else req.size

    regnos = [u["reg_no"] for u in users]
    random.shuffle(regnos)

    past_pairs_ref = db.collection("past_pairs").stream()
    used_pairs = set(tuple(sorted([p.to_dict()["user1"], p.to_dict()["user2"]])) for p in past_pairs_ref)

    groups = []
    i = 0
    while i < len(regnos):
        group = regnos[i:i+size]
        valid = all(tuple(sorted([group[j], group[k]])) not in used_pairs for j in range(len(group)) for k in range(j+1, len(group)))
        if valid:
            display_group = []
            for reg in group:
                name = db.collection("users").document(reg).get().to_dict()["name"]
                display_group.append(f"{name} ({reg})")
            groups.append(display_group)
            for j in range(len(group)):
                for k in range(j+1, len(group)):
                    db.collection("past_pairs").add({"user1": group[j], "user2": group[k]})
            i += size
        else:
            random.shuffle(regnos)
            groups = []
            i = 0

    # Clear old groups of same title
    groups_query = db.collection("groups").where("title", "==", req.title).stream()
    for g in groups_query:
        g.reference.delete()

    for idx, g in enumerate(groups, start=1):
        db.collection("groups").add({
            "title": req.title,
            "group_no": idx,
            "members": g
        })

    return {"groups": groups, "title": req.title}

# ---------- GET GROUPS ----------
@app.get("/groups")
def get_groups():
    groups_ref = db.collection("groups").stream()
    grouped = {}
    for g in groups_ref:
        d = g.to_dict()
        grouped.setdefault(d["title"], []).append(d["members"])
    return [{"title": t, "groups": g} for t, g in grouped.items()]
