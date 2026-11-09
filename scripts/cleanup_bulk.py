"""Remove bulk test jobs from production DB."""
import sys
sys.path.insert(0, ".")
from app.database import SessionLocal, init_db
from app.models import Job
from sqlalchemy import select, func, delete

init_db()
db = SessionLocal()
deleted = db.execute(delete(Job).where(Job.raw["bulk"].as_boolean() == True)).rowcount
db.commit()
remaining = db.scalar(select(func.count(Job.id)))
print(f"Deleted {deleted} bulk jobs. Remaining: {remaining}")
db.close()
