from sqlalchemy import Column, Integer, String, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    skills = Column(JSON, default=[])  # e.g. ["Python", "PostgreSQL"]
    points = Column(Integer, default=0)

    tasks = relationship("Task", back_populates="assigned_to")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    required_skill = Column(String, nullable=False)
    points = Column(Integer, default=10)
    status = Column(String, default="Assigned")
    assigned_to_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    assigned_to = relationship("Employee", back_populates="tasks")