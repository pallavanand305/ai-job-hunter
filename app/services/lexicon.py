from __future__ import annotations

import re
from functools import lru_cache

# canonical skill -> (category, aliases)
SKILLS: dict[str, tuple[str, list[str]]] = {
    # AI / GenAI
    "LLMs": ("AI/GenAI", ["llm", "llms", "large language model", "large language models"]),
    "RAG": ("AI/GenAI", ["rag", "retrieval augmented generation", "retrieval-augmented generation"]),
    "LangChain": ("AI/GenAI", ["langchain", "lang chain"]),
    "LlamaIndex": ("AI/GenAI", ["llamaindex", "llama index"]),
    "Prompt Engineering": ("AI/GenAI", ["prompt engineering", "prompt design"]),
    "Vector Databases": ("AI/GenAI", ["vector database", "vector databases", "vector db", "vector store"]),
    "Qdrant": ("AI/GenAI", ["qdrant"]),
    "Pinecone": ("AI/GenAI", ["pinecone"]),
    "Weaviate": ("AI/GenAI", ["weaviate"]),
    "FAISS": ("AI/GenAI", ["faiss"]),
    "Neo4j": ("AI/GenAI", ["neo4j", "graph database", "graph databases"]),
    "OpenAI API": ("AI/GenAI", ["openai", "openai api", "gpt-4", "gpt4", "gpt-4o", "chatgpt api"]),
    "Hugging Face": ("AI/GenAI", ["hugging face", "huggingface", "transformers library"]),
    "Fine-tuning": ("AI/GenAI", ["fine-tuning", "finetuning", "fine tuning", "lora", "peft"]),
    "Agentic AI": ("AI/GenAI", ["agentic", "ai agents", "multi-agent", "langgraph", "crewai"]),

    # ML
    "Machine Learning": ("ML", ["machine learning", "ml"]),
    "Deep Learning": ("ML", ["deep learning", "neural networks"]),
    "NLP": ("ML", ["nlp", "natural language processing"]),
    "Computer Vision": ("ML", ["computer vision", "opencv"]),
    "PyTorch": ("ML", ["pytorch", "torch"]),
    "TensorFlow": ("ML", ["tensorflow", "tf.keras"]),
    "Scikit-learn": ("ML", ["scikit-learn", "sklearn", "scikit learn"]),
    "Pandas": ("ML", ["pandas"]),
    "NumPy": ("ML", ["numpy"]),
    "BERT": ("ML", ["bert"]),
    "LSTM": ("ML", ["lstm", "lstms"]),
    "CNN": ("ML", ["cnn", "cnns", "convolutional"]),
    "Feature Engineering": ("ML", ["feature engineering"]),
    "Model Evaluation": ("ML", ["model evaluation", "model metrics"]),
    "Recommendation Systems": ("ML", ["recommendation system", "recommender"]),

    # MLOps
    "MLOps": ("MLOps", ["mlops", "ml ops"]),
    "SageMaker": ("MLOps", ["sagemaker", "sage maker"]),
    "MLflow": ("MLOps", ["mlflow"]),
    "Kubeflow": ("MLOps", ["kubeflow"]),
    "Model Deployment": ("MLOps", ["model deployment", "model serving"]),
    "Model Monitoring": ("MLOps", ["model monitoring", "drift detection"]),
    "Automated Retraining": ("MLOps", ["automated retraining", "auto retraining", "retraining"]),
    "Feature Store": ("MLOps", ["feature store", "feast"]),
    "Airflow": ("MLOps", ["airflow", "apache airflow"]),

    # Backend
    "Python": ("Backend", ["python"]),
    "FastAPI": ("Backend", ["fastapi", "fast api"]),
    "Django": ("Backend", ["django"]),
    "Django REST Framework": ("Backend", ["django rest framework", "drf"]),
    "Flask": ("Backend", ["flask"]),
    "Node.js": ("Backend", ["node.js", "nodejs", "node js"]),
    "Java": ("Backend", ["java"]),
    "Go": ("Backend", ["golang", "go language"]),
    "SQLAlchemy": ("Backend", ["sqlalchemy"]),
    "Pydantic": ("Backend", ["pydantic"]),
    "Celery": ("Backend", ["celery"]),
    "Asyncio": ("Backend", ["asyncio", "async io"]),
    "REST APIs": ("Backend", ["rest api", "rest apis", "restful", "restful apis", "rest"]),
    "GraphQL": ("Backend", ["graphql"]),
    "gRPC": ("Backend", ["grpc"]),
    "Microservices": ("Backend", ["microservice", "microservices", "micro services"]),
    "JWT": ("Backend", ["jwt", "json web token"]),
    "OAuth2": ("Backend", ["oauth", "oauth2", "oauth 2.0"]),
    "API Design": ("Backend", ["api design", "api development"]),

    # Cloud
    "AWS": ("Cloud", ["aws", "amazon web services"]),
    "GCP": ("Cloud", ["gcp", "google cloud"]),
    "Azure": ("Cloud", ["azure", "microsoft azure"]),
    "EC2": ("Cloud", ["ec2"]),
    "S3": ("Cloud", ["s3"]),
    "Lambda": ("Cloud", ["lambda", "aws lambda"]),
    "API Gateway": ("Cloud", ["api gateway"]),
    "RDS": ("Cloud", ["rds"]),
    "ECS": ("Cloud", ["ecs"]),
    "EKS": ("Cloud", ["eks"]),
    "SQS": ("Cloud", ["sqs"]),
    "SNS": ("Cloud", ["sns"]),
    "CloudWatch": ("Cloud", ["cloudwatch"]),
    "Step Functions": ("Cloud", ["step functions"]),
    "Glue": ("Cloud", ["aws glue"]),
    "Serverless": ("Cloud", ["serverless"]),

    # DevOps / IaC
    "Docker": ("DevOps", ["docker", "containerization"]),
    "Kubernetes": ("DevOps", ["kubernetes", "k8s"]),
    "Jenkins": ("DevOps", ["jenkins"]),
    "GitHub Actions": ("DevOps", ["github actions"]),
    "GitLab CI": ("DevOps", ["gitlab ci", "gitlab-ci"]),
    "ArgoCD": ("DevOps", ["argocd", "argo cd"]),
    "GitOps": ("DevOps", ["gitops"]),
    "Helm": ("DevOps", ["helm"]),
    "Terraform": ("DevOps", ["terraform"]),
    "CloudFormation": ("DevOps", ["cloudformation", "cloud formation"]),
    "CI/CD": ("DevOps", ["ci/cd", "cicd", "continuous integration", "continuous delivery", "continuous deployment"]),
    "Linux": ("DevOps", ["linux", "ubuntu", "unix"]),
    "Nginx": ("DevOps", ["nginx"]),
    "VPC": ("DevOps", ["vpc"]),
    "IAM": ("DevOps", ["iam", "least privilege", "least-privilege"]),

    # Data
    "Kafka": ("Data", ["kafka", "apache kafka"]),
    "Spark": ("Data", ["spark", "apache spark", "pyspark"]),
    "Flink": ("Data", ["flink", "apache flink"]),
    "ETL": ("Data", ["etl", "elt", "data pipeline", "data pipelines"]),
    "Airbyte": ("Data", ["airbyte"]),
    "dbt": ("Data", ["dbt"]),
    "Data Warehousing": ("Data", ["data warehouse", "data warehousing", "snowflake", "redshift", "bigquery"]),
    "Great Expectations": ("Data", ["great expectations"]),

    # DB
    "PostgreSQL": ("Databases", ["postgresql", "postgres", "psql"]),
    "MySQL": ("Databases", ["mysql"]),
    "MongoDB": ("Databases", ["mongodb", "mongo"]),
    "Redis": ("Databases", ["redis", "elasticache"]),
    "Alembic": ("Databases", ["alembic", "migrations"]),
    "SQL": ("Databases", ["sql", "query optimization", "sql queries"]),
    "Elasticsearch": ("Databases", ["elasticsearch", "elastic search", "opensearch"]),
    "DynamoDB": ("Databases", ["dynamodb"]),
    "pgvector": ("Databases", ["pgvector"]),

    # Monitoring
    "Prometheus": ("Monitoring", ["prometheus"]),
    "Grafana": ("Monitoring", ["grafana"]),
    "ELK Stack": ("Monitoring", ["elk", "elk stack", "kibana", "logstash"]),
    "Datadog": ("Monitoring", ["datadog"]),
    "OpenTelemetry": ("Monitoring", ["opentelemetry", "otel"]),
    "SLO/SLA": ("Monitoring", ["slo", "sla", "sli"]),

    # Testing
    "PyTest": ("Testing", ["pytest", "py test"]),
    "Unit Testing": ("Testing", ["unit test", "unit testing", "unit tests"]),
    "Integration Testing": ("Testing", ["integration test", "integration testing"]),
    "TDD": ("Testing", ["tdd", "test driven development", "test-driven development"]),
    "Playwright": ("Testing", ["playwright"]),
    "Selenium": ("Testing", ["selenium"]),

    # Frontend / misc
    "React": ("Frontend", ["react", "react.js", "reactjs"]),
    "Next.js": ("Frontend", ["next.js", "nextjs", "next js"]),
    "TypeScript": ("Frontend", ["typescript", "ts"]),
    "JavaScript": ("Frontend", ["javascript", "js"]),
    "HTML/CSS": ("Frontend", ["html", "css", "html/css"]),
    "Git": ("Tools", ["git", "github", "gitlab", "version control"]),
    "Agile": ("Tools", ["agile", "scrum", "kanban"]),
    "System Design": ("Architecture", ["system design", "distributed systems", "high availability", "scalability"]),
    "Event-Driven Architecture": ("Architecture", ["event-driven", "event driven", "pub/sub"]),
    "Caching": ("Architecture", ["caching", "cache"]),
    "Rate Limiting": ("Architecture", ["rate limiting", "rate limiter"]),
}

# Build a single combined matcher (one regex pass instead of ~150).
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, (_cat, _aliases) in SKILLS.items():
    for _alias in [_canonical, *_aliases]:
        _ALIAS_TO_CANONICAL.setdefault(_alias.lower(), _canonical)

_ALIASES_LONGEST_FIRST = sorted(_ALIAS_TO_CANONICAL, key=len, reverse=True)
COMBINED_RE = re.compile(
    r"(?<![A-Za-z0-9+#.])(?:" + "|".join(re.escape(a) for a in _ALIASES_LONGEST_FIRST) + r")(?![A-Za-z0-9+#.])",
    re.IGNORECASE,
)

STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "that", "this", "have", "has",
    "from", "not", "but", "all", "any", "can", "who", "what", "when", "where", "how", "why", "job",
    "role", "work", "team", "teams", "years", "experience", "including", "using", "build", "building",
    "strong", "good", "plus", "etc", "across", "into", "about", "their", "they", "them", "its", "it",
    "is", "be", "as", "at", "by", "in", "of", "on", "or", "to", "we", "us", "an", "a", "per", "via",
    "must", "should", "would", "could", "may", "more", "most", "such", "than", "then", "there", "these",
    "those", "was", "were", "been", "being", "also", "other", "some", "new", "well", "make", "made",
    "help", "helps", "like", "need", "needs", "want", "wants", "one", "two", "three", "ability", "able",
}


def canonical_skill(name: str) -> str:
    """Map a free-form skill string to a canonical name if possible."""
    low = name.strip().lower()
    for canonical, (_cat, aliases) in SKILLS.items():
        if low == canonical.lower() or low in (a.lower() for a in aliases):
            return canonical
    return name.strip()


@lru_cache(maxsize=1024)
def _find_skills_cached(text: str) -> tuple[tuple[str, str], ...]:
    found: dict[str, str] = {}
    for match in COMBINED_RE.finditer(text):
        canonical = _ALIAS_TO_CANONICAL.get(match.group(0).lower())
        if canonical:
            found[canonical] = SKILLS[canonical][0]
    return tuple(found.items())


def find_skills(text: str) -> dict[str, str]:
    """Return {canonical: category} for every skill found in text."""
    if not text:
        return {}
    return dict(_find_skills_cached(text))


def skill_category(name: str) -> str:
    canonical = canonical_skill(name)
    return SKILLS.get(canonical, ("Other", []))[0]


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9+#.]", "", name.lower())
