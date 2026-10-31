from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import app.models as models
from app.database import engine, SessionLocal

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="TaskMaster Cloud API")

# Enable CORS for external browser and device access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from any employee device or domain
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

@app.get("/")
def root():
    return {"status": "online", "message": "TaskMaster API is live!"}

@app.get("/employees")
def get_employees(db: Session = Depends(get_db)):
    return db.query(models.Employee).order_by(models.Employee.points.desc()).all()

@app.get("/tasks")
def get_tasks(db: Session = Depends(get_db)):
    return db.query(models.Task).all()

@app.post("/tasks/auto-assign")
def auto_assign_task(
    title: str,
    required_skill: str,
    points: int = 10,
    db: Session = Depends(get_db)
):
    all_employees = db.query(models.Employee).all()
    qualified = [e for e in all_employees if required_skill in (e.skills or [])]

    if not qualified:
        raise HTTPException(status_code=404, detail=f"No employee found with skill '{required_skill}'")

    chosen_employee = min(qualified, key=lambda e: len(e.tasks))

    new_task = models.Task(
        title=title,
        required_skill=required_skill,
        points=points,
        status="Assigned",
        assigned_to_id=chosen_employee.id
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "Completed"
    if task.assigned_to:
        task.assigned_to.points += task.points

    db.commit()
    return {"message": "Task completed successfully!", "points_awarded": task.points}