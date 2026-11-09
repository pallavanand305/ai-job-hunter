"""Seed the master resume from a local file.

Usage:
    python scripts/seed_resume.py "C:\\Users\\palla\\Downloads\\Resume (31).pdf"
    python scripts/seed_resume.py resume.docx --variant backend --no-master
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db  # noqa: E402
from app.services.profiles import get_or_create_user, profile_dict, save_resume  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--variant", default="master")
    parser.add_argument("--no-master", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    init_db()
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        resume = save_resume(
            db,
            user,
            os.path.basename(str(path)),
            path.read_bytes(),
            variant=args.variant,
            make_master=not args.no_master,
        )
        profile = profile_dict(db, user)
        print(f"Imported resume #{resume.id} ({resume.variant}), master={resume.is_master}")
        print(f"Name: {profile['name']}")
        print(f"Location: {profile['location']}")
        print(f"Experience: {profile['years_experience']} years")
        print(f"Skills ({len(profile['skills'])}): {', '.join(profile['skills'])}")
        print(f"Experience entries: {len(profile['experience'])}")
        print(f"Projects: {len(profile['projects'])}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
