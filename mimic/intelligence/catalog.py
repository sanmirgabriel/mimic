"""Small offline catalog shared by CLI/Web; no authentication or generation."""

import csv
import io

from mimic.intelligence.builtins import (
    SERVICE_PROFILES, KNOWLEDGE_VERSION, EXPANDED_KNOWLEDGE_VERSION, get_service_profile,
)
from mimic.intelligence.models import (
    CommonCredentialVocabulary, DefaultCredential, ServiceKnowledge, _identifier, _text, _vocabulary,
)

LEGACY_CATALOG_VERSION = "service-catalog-v1"
CATALOG_VERSION = "service-catalog-v2"
CATALOG_VERSIONS = (LEGACY_CATALOG_VERSION, CATALOG_VERSION)
COMMON_PASSWORDS_VERSION = "common-v1"

SERVICES_V1 = (
    ServiceKnowledge("wordpress", "WordPress", "Content management system.", ("wp",),
        (("WordPress installation", "https://developer.wordpress.org/advanced-administration/before-install/howto-install/"),),
        "The installer asks you to choose an administrator username and password. No universal administrator pair is documented here.", LEGACY_CATALOG_VERSION),
    ServiceKnowledge("mysql", "MySQL", "Relational database server.", ("mysql-server",),
        (("MySQL initial account", "https://dev.mysql.com/doc/refman/8.4/en/default-privileges.html"),),
        "The initial administrative account is root. Password setup depends on initialization and packaging; no universal pair is cataloged.", LEGACY_CATALOG_VERSION),
    ServiceKnowledge("postgresql", "PostgreSQL", "Relational database server.", ("postgres", "pgsql"),
        (("PostgreSQL authentication methods", "https://www.postgresql.org/docs/current/auth-methods.html"),
         ("PostgreSQL initdb", "https://www.postgresql.org/docs/current/app-initdb.html")),
        "postgres is an administrative installation convention, not a universal postgres/postgres pair. The bootstrap superuser defaults to the OS user running initdb; passwords and authentication methods depend on installation and pg_hba.conf.", LEGACY_CATALOG_VERSION),
    ServiceKnowledge("mssql", "Microsoft SQL Server", "Relational database platform.", ("sql-server", "sql server"),
        (("SQL Server authentication modes", "https://learn.microsoft.com/en-us/sql/relational-databases/security/choose-an-authentication-mode"),),
        "Windows and mixed authentication modes differ. The sa account is a convention; its password is set during setup, and it is disabled with Windows authentication. No universal pair is cataloged.", LEGACY_CATALOG_VERSION),
    ServiceKnowledge("windows-ad", "Windows / Active Directory", "Windows directory and identity services.", ("active directory", "ad", "windows"),
        (("Active Directory accounts", "https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-default-user-accounts"),),
        "Administrator and service-account names are contextual conventions, not documented password pairs. Authentication depends on domain configuration.", LEGACY_CATALOG_VERSION),
    ServiceKnowledge("grafana", "Grafana", "Observability and dashboard platform.", ("grafana-server",),
        (("Grafana first sign-in", "https://grafana.com/docs/grafana/latest/setup-grafana/sign-in-to-grafana/"),
         ("Grafana roles and permissions", "https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/")),
        "Default initial sign-in uses admin/admin unless configured differently. The first successful sign-in prompts a password change.", LEGACY_CATALOG_VERSION),
    ServiceKnowledge("rabbitmq", "RabbitMQ", "Message broker using AMQP.", ("rabbit mq", "amqp"),
        (("RabbitMQ access control", "https://www.rabbitmq.com/docs/access-control"),),
        "A blank broker normally creates guest/guest. guest is restricted to localhost by default; imported definitions on initial boot prevent this default user from being created.", LEGACY_CATALOG_VERSION),
)

DEFAULT_CREDENTIALS_V1 = (
    DefaultCredential("grafana-initial-admin", "grafana", "admin", "admin",
        "Grafana first sign-in", SERVICES_V1[5].references[0][1],
        "Initial sign-in with default configuration.",
        ("Custom configuration can change the initial credentials.",
         "The first successful sign-in prompts a password change; this pair does not describe subsequent logins."), LEGACY_CATALOG_VERSION),
    DefaultCredential("rabbitmq-initial-guest", "rabbitmq", "guest", "guest",
        "RabbitMQ access control", SERVICES_V1[6].references[0][1],
        "Initial database creation on a blank broker, with default user configuration and without boot-time definition import.",
        ("guest can connect only from localhost by default, regardless of protocol.",
         "Importing definitions at initial boot prevents creation of this default user.",
         "Configuration and administrator changes can alter or remove the account."), LEGACY_CATALOG_VERSION),
)

# Official sources reviewed 2026-10-16. URLs are data, never runtime requests.
SERVICES = SERVICES_V1 + (
    ServiceKnowledge("zabbix", "Zabbix", "Observability and monitoring platform.", ("zabbix-server",),
        (("Zabbix 7.4 first login", "https://www.zabbix.com/documentation/7.4/en/manual/quickstart/login"),),
        "The Zabbix 7.4 frontend quickstart documents initial Admin/zabbix (case-sensitive). Change the password immediately after first login. This describes initial frontend setup, not agent authentication, modified accounts, custom images or every release.", CATALOG_VERSION),
    ServiceKnowledge("sonarqube", "SonarQube Server", "DevSecOps and code quality platform.", ("sonar", "sonarqube-server", "sonarqube server"),
        (("SonarQube Server 2025.1 user management", "https://docs.sonarsource.com/sonarqube-server/2025.1/instance-administration/user-management/introduction"),
         ("SonarQube Server 2025.1 first setup", "https://docs.sonarsource.com/sonarqube-server/2025.1/try-out-sonarqube"),
         ("SonarQube Server 2025.1 installation scope", "https://docs.sonarsource.com/sonarqube-server/2025.1/setup-and-upgrade/install-the-server/introduction")),
        "SonarQube Server 2025.1 creates an initial admin/admin account with Administer System permission. The documented Docker/ZIP first setup asks for a password change. Scope here is Developer/Enterprise Edition initial setup; changed accounts, SonarQube Cloud, Community Build and other releases are not covered.", CATALOG_VERSION),
    ServiceKnowledge("jenkins", "Jenkins", "CI/CD automation server.", ("jenkins-controller",),
        (("Jenkins offline setup wizard", "https://www.jenkins.io/doc/book/installing/offline/"),),
        "The documented new-controller setup wizard uses an automatically generated, installation-specific unlock password, then asks for the first administrator user. This bootstrap secret is not a universal username/password pair. Preconfigured controllers and images may use another setup process. The unversioned handbook establishes no release range.", CATALOG_VERSION),
    ServiceKnowledge("tomcat", "Apache Tomcat", "Java application server and administration.", ("apache-tomcat", "apache tomcat"),
        (("Apache Tomcat 11.0.27 distributed users file", "https://github.com/apache/tomcat/blob/11.0.27/conf/tomcat-users.xml"),
         ("Apache Tomcat 11 Manager access", "https://tomcat.apache.org/tomcat-11.0-doc/manager-howto.html")),
        "The Apache Tomcat 11.0.27 distributed users file enables no manager-gui user. Its commented users and password placeholders are ignored examples. Manager access requires an explicitly configured account and role. This factory configuration does not describe every installed Realm, distribution or container image.", CATALOG_VERSION),
    ServiceKnowledge("redis", "Redis", "Database and cache server.", ("redis-server", "redis oss"),
        (("Redis Open Source security", "https://redis.io/docs/latest/operate/oss_and_stack/management/security/"),
         ("Redis Open Source ACL", "https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/"),
         ("Redis Cloud database security", "https://redis.io/docs/latest/operate/rc/security/database-security/")),
        "Redis Open Source authentication depends on configuration: Redis 6+ ACLs support named users; the documented default user with nopass permits connections without AUTH. That is not a fixed or empty password pair. requirepass configures a password. Protected mode limits access in the documented default/no-password case. Redis Cloud databases require a password and support RBAC; Cloud credentials are separate. Latest documentation establishes no universal release/deployment scope or password.", CATALOG_VERSION),
    ServiceKnowledge("opensearch", "OpenSearch", "Search and observability platform.", ("open-search", "opensearch-security"),
        (("OpenSearch 2.12 demo configuration", "https://docs.opensearch.org/2.12/security/configuration/demo-configuration/"),),
        "Starting with OpenSearch 2.12, a new cluster using the Security plugin demo installer requires a custom admin password; setup fails without it. The documented Docker/TAR/Windows/Helm/RPM/DEB paths use OPENSEARCH_INITIAL_ADMIN_PASSWORD. Existing configured clusters are unaffected by this installation change. Historical demo credentials are not universal current defaults; no historical pair is cataloged. Production/custom security configurations and managed services require their own evidence.", CATALOG_VERSION),
)

DEFAULT_CREDENTIALS = DEFAULT_CREDENTIALS_V1 + (
    DefaultCredential("zabbix-initial-admin", "zabbix", "Admin", "zabbix",
        SERVICES[7].references[0][0], SERVICES[7].references[0][1],
        "Initial Zabbix frontend login using the documented 7.4 quickstart configuration.",
        ("Username capitalization is significant: Admin.",
         "Change the default password immediately after the first login.",
         "Not an agent credential or evidence for changed accounts, custom images or other releases."),
        CATALOG_VERSION, version_scope="Zabbix 7.4 frontend quickstart"),
    DefaultCredential("sonarqube-initial-admin", "sonarqube", "admin", "admin",
        SERVICES[8].references[0][0], SERVICES[8].references[0][1],
        "Initial SonarQube Server 2025.1 installation with the automatically created administrative account.",
        ("Scope is Developer/Enterprise Edition first setup as documented for Docker/ZIP.",
         "First setup asks for a password change; this pair does not describe the changed account.",
         "No assertion for SonarQube Cloud, Community Build, custom provisioning or other releases."),
        CATALOG_VERSION, version_scope="SonarQube Server 2025.1; Developer/Enterprise Edition initial setup"),
)

COMMON_VOCABULARY = CommonCredentialVocabulary(
    "common-credentials", COMMON_PASSWORDS_VERSION,
    "Conventional weak values, not prevalence statistics or associated credential pairs. Usernames and passwords are independent lists.",
    ("admin", "root", "administrator", "guest", "support", "test"),
    ("admin", "password", "changeme", "welcome", "123456", "mudar"),
)


def validate_catalog(services=SERVICES, credentials=DEFAULT_CREDENTIALS, *, profiles=SERVICE_PROFILES) -> None:
    """Validate one coherent view; legacy record revisions remain immutable."""
    service_ids = [service.id for service in services]
    if len(set(service_ids)) != len(service_ids):
        raise ValueError("duplicate service IDs")
    profile_ids = [profile.id for profile in profiles]
    if len(set(profile_ids)) != len(profile_ids):
        raise ValueError("duplicate service profile IDs")
    expected_versions = {s.id: s.catalog_version for s in SERVICES}
    aliases = {}
    for service in services:
        if service.catalog_version not in CATALOG_VERSIONS or service.catalog_version != expected_versions.get(service.id):
            raise ValueError("unsupported service catalog version for service ID")
        names = (service.id, service.display_name, *service.aliases)
        normalized_aliases = [a.strip().casefold() for a in service.aliases]
        if len(set(normalized_aliases)) != len(normalized_aliases):
            raise ValueError("duplicate service aliases")
        for name in names:
            key = name.strip().casefold()
            if key in aliases and aliases[key] != service.id:
                raise ValueError("ambiguous service alias")
            aliases[key] = service.id
    for profile in profiles:
        _identifier(profile.id)
        _text(profile.display_name, "profile display_name")
        for field in ("tokens", "roles"):
            _vocabulary(getattr(profile, field), "profile " + field)
        if not profile.tokens:
            raise ValueError("service profiles require contextual tokens")
        expected = KNOWLEDGE_VERSION if profile.id in {s.id for s in SERVICES_V1} else EXPANDED_KNOWLEDGE_VERSION
        if profile.version != expected:
            raise ValueError("unsupported service profile version")
    if set(profile_ids) != set(service_ids):
        raise ValueError("service profiles and knowledge must have matching IDs")
    ids = [credential.id for credential in credentials]
    # Different prose does not justify recording the same pair twice. Distinct
    # explicit version scopes can represent separately documented history.
    pairs = [(c.service_id, c.username, c.password, (c.version_scope or "").strip().casefold()) for c in credentials]
    if len(set(ids)) != len(ids) or len(set(pairs)) != len(pairs):
        raise ValueError("duplicate documented credentials")
    for credential in credentials:
        if credential.service_id not in service_ids:
            raise ValueError("credential references an unknown service")
        service = next(s for s in services if s.id == credential.service_id)
        if credential.catalog_version != service.catalog_version or credential.record_version != "1":
            raise ValueError("unsupported credential catalog or record version")
        if credential.catalog_version == CATALOG_VERSION and not credential.version_scope:
            raise ValueError("expanded credential requires an explicit version scope")
        if (credential.source_title, credential.source_url) not in service.references:
            raise ValueError("credential evidence must reference its service documentation")


validate_catalog()


def _service_collection(version: str) -> tuple[ServiceKnowledge, ...]:
    if version == LEGACY_CATALOG_VERSION:
        return SERVICES_V1
    if version == CATALOG_VERSION:
        return SERVICES
    raise ValueError(f"unsupported service catalog version: {version}")


def list_services(query: str = "", *, version: str = CATALOG_VERSION) -> tuple[ServiceKnowledge, ...]:
    query = query.strip().casefold()
    return tuple(service for service in _service_collection(version) if not query or query in " ".join(
        (service.id, service.display_name, service.description, *service.aliases,
         *get_service_profile(service.id).tokens)).casefold())


def get_service(service_id: str, *, version: str = CATALOG_VERSION) -> ServiceKnowledge:
    for service in _service_collection(version):
        if service.id == service_id:
            return service
    raise ValueError(f"unknown service: {service_id}")


def list_credentials(service_id: str | None = None, *, version: str = CATALOG_VERSION) -> tuple[DefaultCredential, ...]:
    _service_collection(version)  # Reject unknown versions, even for empty filters.
    if service_id is not None:
        get_service(service_id, version=version)
    credentials = DEFAULT_CREDENTIALS_V1 if version == LEGACY_CATALOG_VERSION else DEFAULT_CREDENTIALS
    return tuple(c for c in credentials if service_id is None or c.service_id == service_id)


def common_vocabulary(version: str = COMMON_PASSWORDS_VERSION) -> CommonCredentialVocabulary:
    if version != COMMON_VOCABULARY.version:
        raise ValueError(f"unsupported common password collection version: {version}")
    return COMMON_VOCABULARY


def _csv_value(value: str) -> str:
    # Quoting alone does not prevent spreadsheet formula execution.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def credentials_csv(service_id: str | None = None, *, version: str = CATALOG_VERSION) -> str:
    return _credential_rows_csv(list_credentials(service_id, version=version))


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
