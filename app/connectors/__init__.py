from app.connectors.base import BaseConnector, NormalizedJob
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.jobicy import JobicyConnector
from app.connectors.lever import LeverConnector
from app.connectors.remoteok import RemoteOKConnector
from app.connectors.remotive import RemotiveConnector
from app.connectors.arbeitnow import ArbeitnowConnector
from app.connectors.rss import RSSConnector
from app.connectors.alert_feed import (
    IndeedConnector,
    InstahyreConnector,
    LinkedInConnector,
    NaukriConnector,
    WellfoundConnector,
)
from app.connectors.adzuna import AdzunaConnector
from app.connectors.himalayas import HimalayasConnector
from app.connectors.jooble import JoobleConnector
from app.connectors.pythonjobs import PythonJobsConnector
from app.connectors.weworkremotely import WeWorkRemotelyConnector
from app.connectors.workingnomads import WorkingNomadsConnector
from app.connectors.themuse import TheMuseConnector
from app.connectors.landingjobs import LandingJobsConnector

CONNECTORS: dict[str, type[BaseConnector]] = {
    "greenhouse": GreenhouseConnector,
    "lever": LeverConnector,
    "remotive": RemotiveConnector,
    "remoteok": RemoteOKConnector,
    "arbeitnow": ArbeitnowConnector,
    "jobicy": JobicyConnector,
    "rss": RSSConnector,
    "himalayas": HimalayasConnector,
    "weworkremotely": WeWorkRemotelyConnector,
    "pythonjobs": PythonJobsConnector,
    "workingnomads": WorkingNomadsConnector,
    "themuse": TheMuseConnector,
    "landingjobs": LandingJobsConnector,
    "adzuna": AdzunaConnector,
    "jooble": JoobleConnector,
    "linkedin": LinkedInConnector,
    "naukri": NaukriConnector,
    "indeed": IndeedConnector,
    "instahyre": InstahyreConnector,
    "wellfound": WellfoundConnector,
}

__all__ = ["BaseConnector", "NormalizedJob", "CONNECTORS"]
