"""Small offline catalog shared by CLI/Web; no authentication or generation."""

import csv
import io

from mimic.intelligence.builtins import get_service_profile
from mimic.intelligence.models import (
    CommonCredentialVocabulary, DefaultCredential, ServiceKnowledge,
)

CATALOG_VERSION = "service-catalog-v1"
COMMON_PASSWORDS_VERSION = "common-v1"

SERVICES = (
    ServiceKnowledge("wordpress", "WordPress", "Content management system.", ("wp",),
        (("WordPress installation", "https://developer.wordpress.org/advanced-administration/before-install/howto-install/"),),
        "The installer asks you to choose an administrator username and password. No universal administrator pair is documented here.", CATALOG_VERSION),
    ServiceKnowledge("mysql", "MySQL", "Relational database server.", ("mysql-server",),
        (("MySQL initial account", "https://dev.mysql.com/doc/refman/8.4/en/default-privileges.html"),),
        "The initial administrative account is root. Password setup depends on initialization and packaging; no universal pair is cataloged.", CATALOG_VERSION),
    ServiceKnowledge("postgresql", "PostgreSQL", "Relational database server.", ("postgres", "pgsql"),
        (("PostgreSQL authentication methods", "https://www.postgresql.org/docs/current/auth-methods.html"),
         ("PostgreSQL initdb", "https://www.postgresql.org/docs/current/app-initdb.html")),
        "postgres is an administrative installation convention, not a universal postgres/postgres pair. The bootstrap superuser defaults to the OS user running initdb; passwords and authentication methods depend on installation and pg_hba.conf.", CATALOG_VERSION),
    ServiceKnowledge("mssql", "Microsoft SQL Server", "Relational database platform.", ("sql-server", "sql server"),
        (("SQL Server authentication modes", "https://learn.microsoft.com/en-us/sql/relational-databases/security/choose-an-authentication-mode"),),
        "Windows and mixed authentication modes differ. The sa account is a convention; its password is set during setup, and it is disabled with Windows authentication. No universal pair is cataloged.", CATALOG_VERSION),
    ServiceKnowledge("windows-ad", "Windows / Active Directory", "Windows directory and identity services.", ("active directory", "ad", "windows"),
        (("Active Directory accounts", "https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-default-user-accounts"),),
        "Administrator and service-account names are contextual conventions, not documented password pairs. Authentication depends on domain configuration.", CATALOG_VERSION),
    ServiceKnowledge("grafana", "Grafana", "Observability and dashboard platform.", ("grafana-server",),
        (("Grafana first sign-in", "https://grafana.com/docs/grafana/latest/setup-grafana/sign-in-to-grafana/"),
         ("Grafana roles and permissions", "https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/")),
        "Default initial sign-in uses admin/admin unless configured differently. The first successful sign-in prompts a password change.", CATALOG_VERSION),
    ServiceKnowledge("rabbitmq", "RabbitMQ", "Message broker using AMQP.", ("rabbit mq", "amqp"),
        (("RabbitMQ access control", "https://www.rabbitmq.com/docs/access-control"),),
        "A blank broker normally creates guest/guest. guest is restricted to localhost by default; imported definitions on initial boot prevent this default user from being created.", CATALOG_VERSION),
)

DEFAULT_CREDENTIALS = (
    DefaultCredential("grafana-initial-admin", "grafana", "admin", "admin",
        "Grafana first sign-in", SERVICES[5].references[0][1],
        "Initial sign-in with default configuration.",
        ("Custom configuration can change the initial credentials.",
         "The first successful sign-in prompts a password change; this pair does not describe subsequent logins."), CATALOG_VERSION),
    DefaultCredential("rabbitmq-initial-guest", "rabbitmq", "guest", "guest",
        "RabbitMQ access control", SERVICES[6].references[0][1],
        "Initial database creation on a blank broker, with default user configuration and without boot-time definition import.",
        ("guest can connect only from localhost by default, regardless of protocol.",
         "Importing definitions at initial boot prevents creation of this default user.",
         "Configuration and administrator changes can alter or remove the account."), CATALOG_VERSION),
)

COMMON_VOCABULARY = CommonCredentialVocabulary(
    "common-credentials", COMMON_PASSWORDS_VERSION,
    "Conventional weak values, not prevalence statistics or associated credential pairs. Usernames and passwords are independent lists.",
    ("admin", "root", "administrator", "guest", "support", "test"),
    ("admin", "password", "changeme", "welcome", "123456", "mudar"),
)


def validate_catalog(services=SERVICES, credentials=DEFAULT_CREDENTIALS) -> None:
    """Reject duplicate identities/pairs and dangling or unversioned evidence."""
    service_ids = [service.id for service in services]
    if len(set(service_ids)) != len(service_ids):
        raise ValueError("duplicate service IDs")
    ids = [credential.id for credential in credentials]
    pairs = [(c.service_id, c.username, c.password, c.applicability) for c in credentials]
    if len(set(ids)) != len(ids) or len(set(pairs)) != len(pairs):
        raise ValueError("duplicate documented credentials")
    for service in services:
        get_service_profile(service.id)
        if service.catalog_version != CATALOG_VERSION:
            raise ValueError("unsupported service catalog version")
    for credential in credentials:
        if credential.service_id not in service_ids:
            raise ValueError("credential references an unknown service")
        if credential.catalog_version != CATALOG_VERSION:
            raise ValueError("unsupported credential catalog version")
        service = next(s for s in services if s.id == credential.service_id)
        if (credential.source_title, credential.source_url) not in service.references:
            raise ValueError("credential evidence must reference its service documentation")


validate_catalog()


def list_services(query: str = "") -> tuple[ServiceKnowledge, ...]:
    query = query.strip().casefold()
    return tuple(service for service in SERVICES if not query or query in " ".join(
        (service.id, service.display_name, *service.aliases,
         *get_service_profile(service.id).tokens)).casefold())


def get_service(service_id: str) -> ServiceKnowledge:
    for service in SERVICES:
        if service.id == service_id:
            return service
    raise ValueError(f"unknown service: {service_id}")


def list_credentials(service_id: str | None = None) -> tuple[DefaultCredential, ...]:
    if service_id is not None:
        get_service(service_id)
    return tuple(c for c in DEFAULT_CREDENTIALS if service_id is None or c.service_id == service_id)


def common_vocabulary(version: str = COMMON_PASSWORDS_VERSION) -> CommonCredentialVocabulary:
    if version != COMMON_VOCABULARY.version:
        raise ValueError(f"unsupported common password collection version: {version}")
    return COMMON_VOCABULARY


def _csv_value(value: str) -> str:
    # Quoting alone does not prevent spreadsheet formula execution.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def credentials_csv(service_id: str | None = None) -> str:
    return _credential_rows_csv(list_credentials(service_id))


def _credential_rows_csv(credentials) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("service", "username", "password", "type", "source_url", "applicability"))
    for c in credentials:
        # Restrictions and source version context travel with each exported pair.
        applicability = c.applicability + " " + " ".join(c.restrictions)
        if c.version_scope:
            applicability += " Version scope: " + c.version_scope
        writer.writerow(tuple(_csv_value(value) for value in
            (c.service_id, c.username, c.password, c.type, c.source_url, applicability)))
    return output.getvalue()


def common_csv() -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("category", "value", "type", "collection", "version"))
    collection = common_vocabulary()
    for category, values in (("username", collection.usernames), ("password", collection.passwords)):
        for value in values:
            writer.writerow((category, _csv_value(value), collection.type, collection.id, collection.version))
    return output.getvalue()
