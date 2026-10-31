from app.database import SessionLocal, engine
from app.models import Base, User, UserRole

# Create all tables automatically
Base.metadata.create_all(bind=engine)

db = SessionLocal()

sample_users = [
    User(
        id="EMP-101",
        full_name="John Doe",
        email="john@taskmaster.com",
        role=UserRole.WORKER,
        department="Procurement",
        skill_keywords=["purchase", "buy", "steel", "procure"],
        base_salary=5000.00,
    ),
    User(
        id="EMP-102",
        full_name="Alice Smith",
        email="alice@taskmaster.com",
        role=UserRole.WORKER,
        department="Logistics",
        skill_keywords=["ship", "transport", "delivery", "freight"],
        base_salary=4800.00,
    ),
    User(
        id="EMP-999",
        full_name="Executive Boss",
        email="boss@taskmaster.com",
        role=UserRole.BOSS,
        department="Executive",
        skill_keywords=[],
        base_salary=10000.00,
    ),
]

for user in sample_users:
  if not db.query(User).filter(User.id == user.id).first():
    db.add(user)

db.commit()
db.close()
print("✅ PostgreSQL tables created and seeded successfully!")
