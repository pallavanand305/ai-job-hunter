from __future__ import annotations

import argparse
import os

from app.database import SessionLocal, init_db
from app.services.discovery import run_discovery, seed_sources
from app.services.matching import run_matching
from app.services.profiles import get_or_create_user, profile_dict, rebuild_profile, save_resume


def cmd_init(_args) -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_sources(db)
        user = get_or_create_user(db)
        print(f"Initialized. User: {user.name} <{user.email}>")
    finally:
        db.close()


def cmd_import_resume(args) -> None:
    init_db()
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        with open(args.path, "rb") as handle:
            content = handle.read()
        resume = save_resume(
            db, user, os.path.basename(args.path), content,
            variant=args.variant, make_master=args.master,
        )
        profile = profile_dict(db, user)
        print(f"Imported resume #{resume.id} ({resume.variant}). Master={resume.is_master}")
        print(f"Skills: {', '.join(profile['skills'])}")
        print(f"Experience: {profile['years_experience']} years")
    finally:
        db.close()


def cmd_discover(args) -> None:
    init_db()
    db = SessionLocal()
    try:
        result = run_discovery(db, only=args.only)
        print(result)
    finally:
        db.close()


def cmd_match(_args) -> None:
    init_db()
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        print(run_matching(db, user, profile_dict(db, user)))
    finally:
        db.close()


def cmd_rebuild(_args) -> None:
    init_db()
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        rebuild_profile(db, user)
        profile = profile_dict(db, user)
        print(f"Skills: {', '.join(profile['skills'])}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="AI Job Hunter CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create database and default records").set_defaults(func=cmd_init)

    p = sub.add_parser("import-resume", help="Parse and import a resume file")
    p.add_argument("path")
    p.add_argument("--variant", default="master")
    p.add_argument("--master", action="store_true", default=True)
    p.set_defaults(func=cmd_import_resume)

    p = sub.add_parser("discover", help="Run job discovery")
    p.add_argument("--only", default=None, help="Only run one source name")
    p.set_defaults(func=cmd_discover)

    sub.add_parser("match", help="Score all jobs against the profile").set_defaults(func=cmd_match)
    sub.add_parser("rebuild", help="Rebuild profile from master resume").set_defaults(func=cmd_rebuild)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
