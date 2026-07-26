"""SQLModel table definitions.

Importing this package registers every table on ``SQLModel.metadata`` which is
what Alembic autogenerate and ``init_db`` rely on.
"""

from app.models.entities import (  # noqa: F401
    Analysis,
    AuditLog,
    Finding,
    GitHubInstallation,
    Patch,
    PullRequest,
    Repository,
    RepositorySettings,
    ReviewComment,
    User,
    ValidationRun,
)
from app.models.enums import (  # noqa: F401
    AnalysisStatus,
    FindingCategory,
    FindingSource,
    FindingStatus,
    PatchStatus,
    PullRequestStatus,
    ReviewerAgent,
    RiskLevel,
    Severity,
    ValidationStatus,
)

__all__ = [
    "Analysis",
    "AuditLog",
    "Finding",
    "GitHubInstallation",
    "Patch",
    "PullRequest",
    "Repository",
    "RepositorySettings",
    "ReviewComment",
    "User",
    "ValidationRun",
    "AnalysisStatus",
    "FindingCategory",
    "FindingSource",
    "FindingStatus",
    "PatchStatus",
    "PullRequestStatus",
    "ReviewerAgent",
    "RiskLevel",
    "Severity",
    "ValidationStatus",
]
