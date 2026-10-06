"""Curated contextual vocabulary, not corpora or default credential pairs."""

from mimic.intelligence.models import ServiceProfile

KNOWLEDGE_VERSION = "knowledge-v1"
COMMON_NUMBERS = ("123", "321", "1234", "4321", "12345", "123456",
                  "000", "0000", "111", "1111")
CORPORATE_ROLES = ("admin", "administrator", "support", "helpdesk", "IT", "suporte")
SERVICE_PROFILES = (
    ServiceProfile("wordpress", "WordPress", ("WordPress", "wp"), ("admin", "editor"), KNOWLEDGE_VERSION),
    ServiceProfile("mysql", "MySQL", ("mysql", "sql", "db"), ("root", "dba"), KNOWLEDGE_VERSION),
    ServiceProfile("postgresql", "PostgreSQL", ("postgresql", "postgres", "db"), ("postgres", "dba"), KNOWLEDGE_VERSION),
    ServiceProfile("mssql", "Microsoft SQL Server", ("mssql", "sql", "db"), ("sa", "dba"), KNOWLEDGE_VERSION),
    ServiceProfile("windows-ad", "Windows / Active Directory", ("windows", "AD"), ("administrator", "svc"), KNOWLEDGE_VERSION),
)


def get_service_profile(service_id: str) -> ServiceProfile:
    for profile in SERVICE_PROFILES:
        if profile.id == service_id:
            return profile
    raise ValueError(f"unknown service profile: {service_id}")
