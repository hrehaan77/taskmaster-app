import os
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, create_engine
from sqlalchemy.orm import Session, relationship, declarative_base, sessionmaker

# Database Setup (Supports local SQLite & cloud PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./taskmaster.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Database Models
class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    skills = Column(JSON, default=[])
    points = Column(Integer, default=0)

    tasks = relationship("Task", back_populates="assigned_to")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    required_skill = Column(String, nullable=False)
    points = Column(Integer, default=10)
    status = Column(String, default="TODO")  # TODO, IN_PROGRESS, Completed
    assigned_to_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    assigned_to = relationship("Employee", back_populates="tasks")


Base.metadata.create_all(bind=engine)

app = FastAPI(title="TaskMaster Cloud API")

# Enable CORS for cross-device browser access
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

# Pydantic Schemas
class EmployeeCreate(BaseModel):
    name: str
    skills: List[str]

class TaskCreate(BaseModel):
    title: str
    required_skill: str
    points: int = 10

class StatusUpdate(BaseModel):
    status: str


# API Endpoints
@app.get("/")
def root():
    return {"status": "online", "message": "TaskMaster Cloud API is live!"}

@app.get("/employees")
def get_employees(db: Session = Depends(get_db)):
    """Fetch all employees ordered by leaderboard rank."""
    employees = db.query(Employee).order_by(Employee.points.desc()).all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "skills": e.skills or [],
            "points": e.points,
            "active_tasks_count": len([t for t in e.tasks if t.status != "Completed"])
        }
        for e in employees
    ]

@app.post("/employees")
def create_employee(emp: EmployeeCreate, db: Session = Depends(get_db)):
    """Add a new employee to the organization."""
    new_emp = Employee(name=emp.name, skills=emp.skills, points=0)
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)
    return new_emp

@app.get("/tasks")
def get_tasks(assigned_to_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """Fetch tasks (optionally filtered by assigned employee)."""
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
            "assigned_to_id": t.assigned_to_id,
            "assigned_to_name": t.assigned_to.name if t.assigned_to else "Unassigned"
        }
        for t in tasks
    ]

@app.post("/tasks/auto-assign")
def auto_assign_task(task: TaskCreate, db: Session = Depends(get_db)):
    """Auto-route task to qualified employee with lowest current active workload."""
    all_employees = db.query(Employee).all()
    qualified = [e for e in all_employees if task.required_skill in (e.skills or [])]

    if not qualified:
        raise HTTPException(
            status_code=404,
            detail=f"No employee found with required skill '{task.required_skill}'"
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
        "assigned_to_id": chosen_employee.id,
        "assigned_to_name": chosen_employee.name
    }

@app.post("/tasks/{task_id}/status")
def update_task_status(task_id: int, status_update: StatusUpdate, db: Session = Depends(get_db)):
    """Update task status (TODO -> IN_PROGRESS -> Completed) and award points on completion."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_status = status_update.status
    if new_status not in ["TODO", "IN_PROGRESS", "Completed"]:
        raise HTTPException(status_code=400, detail="Status must be TODO, IN_PROGRESS, or Completed")

    # Award points when task transitions to Completed
    if new_status == "Completed" and task.status != "Completed":
        if task.assigned_to:
            task.assigned_to.points += task.points

    task.status = new_status
    db.commit()
    return {"message": f"Task status updated to {new_status}", "task_id": task.id, "status": new_status}

@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, db: Session = Depends(get_db)):
    """Legacy route for single-click completion."""
    return update_task_status(task_id, StatusUpdate(status="Completed"), db)
