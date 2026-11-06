import os
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, create_engine
from sqlalchemy.orm import Session, relationship, declarative_base, sessionmaker

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./taskmaster.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Database Models
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, default="employee")
    skills = Column(JSON, default=[])
    points = Column(Integer, default=0)

    tasks = relationship("Task", back_populates="assigned_to")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    required_skill = Column(String, nullable=False)
    points = Column(Integer, default=10)
    status = Column(String, default="TODO")
    deadline = Column(String, nullable=True, default="ASAP")
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    assigned_to = relationship("User", back_populates="tasks")


# Rebuild tables to match updated schema
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

# Seed Default Manager
def seed_initial_manager():
    db = SessionLocal()
    try:
        manager = db.query(User).filter(User.username == "admin").first()
        if not manager:
            admin_user = User(
                name="System Manager",
                username="admin",
                password="password123",
                role="manager",
                skills=["Management"],
                points=100
            )
            db.add(admin_user)
            db.commit()
    finally:
        db.close()

seed_initial_manager()

app = FastAPI(title="TaskMaster Production API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class LoginRequest(BaseModel):
    username: str
    password: str

class EmployeeCreate(BaseModel):
    name: str
    username: str
    password: str
    skills: List[str]

class TaskCreate(BaseModel):
    title: str
    required_skill: str
    points: int = 10
    deadline: Optional[str] = "ASAP"

class StatusUpdate(BaseModel):
    status: str


@app.get("/")
def root():
    return {"status": "online", "message": "TaskMaster Cloud API is live!"}

@app.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or user.password != req.password:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "role": user.role,
        "skills": user.skills or [],
        "points": user.points
    }

@app.get("/employees")
def get_employees(db: Session = Depends(get_db)):
    employees = db.query(User).filter(User.role == "employee").order_by(User.points.desc()).all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "username": e.username,
            "skills": e.skills or [],
            "points": e.points,
            "active_tasks_count": len([t for t in e.tasks if t.status != "Completed"])
        }
        for e in employees
    ]

@app.post("/employees")
def create_employee(emp: EmployeeCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == emp.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    new_emp = User(
        name=emp.name,
        username=emp.username,
        password=emp.password,
        role="employee",
        skills=[s.strip() for s in emp.skills],
        points=0
    )
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)
    return {
        "id": new_emp.id,
        "name": new_emp.name,
        "username": new_emp.username,
        "skills": new_emp.skills,
        "points": new_emp.points
    }

@app.get("/tasks")
def get_tasks(assigned_to_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Task)
    if assigned_to_id is not None:
        query = query.filter(Task.assigned_to_id == assigned_to_id)
    tasks = query.all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "required_skill": t.required_skill,
            "points": t.points,
            "status": t.status,
            "deadline": t.deadline or "ASAP",
            "assigned_to_id": t.assigned_to_id,
            "assigned_to_name": t.assigned_to.name if t.assigned_to else "Unassigned"
        }
        for t in tasks
    ]

@app.get("/tasks/{task_id}")
def get_task_detail(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.id,
        "title": task.title,
        "required_skill": task.required_skill,
        "points": task.points,
        "status": task.status,
        "deadline": task.deadline or "ASAP",
        "assigned_to_id": task.assigned_to_id,
        "assigned_to_name": task.assigned_to.name if task.assigned_to else "Unassigned",
        "assigned_to_skills": task.assigned_to.skills if task.assigned_to else []
    }

@app.post("/tasks/auto-assign")
def auto_assign_task(task: TaskCreate, db: Session = Depends(get_db)):
    all_employees = db.query(User).filter(User.role == "employee").all()
    
    # Flexible, case-insensitive skill matching
    req_skill = task.required_skill.strip().lower()
    qualified = [
        e for e in all_employees 
        if any(s.strip().lower() == req_skill for s in (e.skills or []))
    ]

    if not qualified:
        raise HTTPException(
            status_code=404,
            detail=f"No employee found with skill '{task.required_skill}'"
        )

    chosen_employee = min(
        qualified,
        key=lambda e: len([t for t in e.tasks if t.status != "Completed"])
    )

    new_task = Task(
        title=task.title,
        required_skill=task.required_skill,
        points=task.points,
        status="TODO",
        deadline=task.deadline or "ASAP",
        assigned_to_id=chosen_employee.id
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return {
        "id": new_task.id,
        "title": new_task.title,
        "required_skill": new_task.required_skill,
        "points": new_task.points,
        "status": new_task.status,
        "deadline": new_task.deadline,
        "assigned_to_id": chosen_employee.id,
        "assigned_to_name": chosen_employee.name
    }

@app.post("/tasks/{task_id}/status")
def update_task_status(task_id: int, status_update: StatusUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_status = status_update.status
    if new_status not in ["TODO", "IN_PROGRESS", "Completed"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    if new_status == "Completed" and task.status != "Completed":
        if task.assigned_to:
            task.assigned_to.points += task.points

    task.status = new_status
    db.commit()
    return {"message": "Status updated successfully", "task_id": task.id, "status": new_status}
