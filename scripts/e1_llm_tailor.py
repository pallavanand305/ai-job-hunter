"""E-1: Tailor 4 JDs using the real LLM path and extract PDF text."""
from __future__ import annotations
import sys, os
sys.path.insert(0, ".")

from pathlib import Path
from app.database import SessionLocal, init_db
from app.models import Job, User
from app.services.profiles import get_or_create_user, profile_dict, save_resume
from app.services.tailoring import build_tailored, export_tailored
from app.llm.client import get_llm

init_db()
db = SessionLocal()
user = get_or_create_user(db)

# Check LLM status
llm = get_llm()
info = llm.info()
print(f"LLM: provider={info['provider']} model={info['model']} usable={info['usable']} fallback={info['fallback']}")

profile = profile_dict(db, user)
print(f"Resume: {len(profile.get('resume_text',''))} chars, {len(profile.get('skills',[]))} skills")
print(f"Experience roles: {len(profile.get('experience',[]))}")

JDS = [
    {
        "label": "AI Engineer",
        "title": "AI Engineer",
        "company": "TechCorp India",
        "location": "Remote, India",
        "remote": True,
        "description": (
            "Job Title: AI Engineer\nCompany: TechCorp India\n\n"
            "We are hiring an AI Engineer with Python, FastAPI, LLMs, RAG, LangChain, "
            "Qdrant, AWS, Docker, Kubernetes experience. Build LLM-powered backend services, "
            "RAG pipelines and agentic AI systems. 3-5 years experience required."
        ),
    },
    {
        "label": "Gurugram GenAI",
        "title": "GenAI Engineer",
        "company": "GenAI Labs",
        "location": "Gurugram, Haryana, India",
        "remote": False,
        "description": (
            "Job Title: GenAI Engineer\nCompany: GenAI Labs\nLocation: Gurugram\n\n"
            "Seeking a GenAI Engineer with LLMs, RAG, LangChain, vector databases, "
            "Python, FastAPI, AWS, Docker, Kubernetes. Build agentic AI systems with "
            "knowledge graphs and multi-agent pipelines. 2-5 years experience."
        ),
    },
    {
        "label": "DevOps Cloud",
        "title": "DevOps Engineer",
        "company": "CloudOps Inc",
        "location": "Pune, India",
        "remote": False,
        "description": (
            "Job Title: DevOps Engineer\nCompany: CloudOps Inc\nLocation: Pune, India\n\n"
            "DevOps Engineer with Docker, Kubernetes, Terraform, Jenkins, GitHub Actions, "
            "AWS EC2/S3/EKS, CI/CD pipelines, Linux, monitoring with Prometheus and Grafana. "
            "Manage cloud infrastructure and deployment pipelines. 3-6 years experience."
        ),
    },
    {
        "label": "No title no company",
        "title": "",
        "company": "",
        "location": "Remote, India",
        "remote": True,
        "description": (
            "Senior LLM Engineer\n\n"
            "We need a Python engineer with LLMs, RAG, LangChain, Qdrant vector database, "
            "FastAPI, AWS, Docker, Kubernetes, MLOps experience. Build and deploy AI "
            "inference services. Work fully remote from India. 4+ years experience."
        ),
    },
]

import hashlib
import pymupdf

for jd in JDS:
    label = jd["label"]
    print(f"\n{'='*65}")
    print(f"JD: {label}")
    print(f"{'='*65}")

    title = jd["title"]
    if not title:
        from app.services.jd_metadata import infer_role_title, infer_company
        title = infer_role_title(jd["description"]) or ""
        company = infer_company(jd["description"]) or ""
    else:
        company = jd["company"]

    key = hashlib.sha256(f"e1-{label}".encode()).hexdigest()
    existing = db.query(Job).filter(Job.dedupe_hash == key).first()
    if existing:
        db.delete(existing)
        db.commit()

    job = Job(
        title=title[:300], company=company[:200],
        location=jd["location"][:200], remote=jd["remote"],
        description=jd["description"], dedupe_hash=key, raw={},
    )
    db.add(job); db.commit(); db.refresh(job)

    profile = profile_dict(db, user)
    tailored = build_tailored(db, user, job, profile)
    report = tailored.match_report or {}
    llm_meta = report.get("llm", {})

    print(f"LLM path: provider={llm_meta.get('provider')} fallback={llm_meta.get('fallback')}")
    print(f"before={report.get('before_score')}%  after={report.get('after_score')}%  target={report.get('target_score')}%  met={report.get('target_met')}")
    print(f"Inferred title: {job.title!r}  company: {job.company!r}")

    # Extract PDF
    pdf_path = tailored.pdf_path
    if pdf_path and Path(pdf_path).exists():
        doc = pymupdf.open(pdf_path)
        pages = len(doc)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        print(f"Pages: {pages}")
        print(f"Filename: {Path(pdf_path).name}")
        print(f"\n--- PDF TEXT ---")
        print(text)
        print(f"--- END ---")

        # Checks
        issues = []
        for bad in ["Confidential", "Unknown company", "Pasted JD role", "Role not specified"]:
            if bad.lower() in text.lower(): issues.append(f"PLACEHOLDER: {bad}")
            if bad.replace(" ", "_") in Path(pdf_path).name: issues.append(f"PLACEHOLDER in filename: {bad}")
        if "leveraged" in text.lower(): issues.append("'; leveraged' suffix pattern")
        headline = profile.get("headline","")
        import re
        sm = re.search(r'Professional Summary\s*(.*?)(?:Core Technical|Work Experience)', text, re.DOTALL)
        if sm and headline and headline in sm.group(1): issues.append("Headline repeated in summary")
        exp = tailored.experience or []
        if len(exp) < 2: issues.append(f"Only {len(exp)} roles (expected 2+)")
        master_titles = [e.get("title","") for e in (profile.get("experience") or [])]
        for e in exp:
            if e.get("title") not in master_titles:
                issues.append(f"Changed title: {e.get('title')!r} not in master")
        if label in ("AI Engineer","Gurugram GenAI","No title no company"):
            projs = tailored.projects or []
            if projs:
                fp = projs[0]
                fp_text = (fp.get("name","") + fp.get("tech","") + " ".join(fp.get("bullets",[]))).lower()
                if not any(k in fp_text for k in ("rag","graph","langchain","qdrant","vector","knowledge","llm")):
                    issues.append(f"GraphRAG not first project: {fp.get('name')}")
        print(f"\nCHECKS: {'PASS' if not issues else 'ISSUES: ' + '; '.join(issues)}")
    else:
        print("NO PDF GENERATED")

    db.delete(job); db.commit()

db.close()
