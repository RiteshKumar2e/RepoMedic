"""SQLModel table definitions.

Importing this package registers every table on ``SQLModel.metadata`` which is
what Alembic autogenerate and ``init_db`` rely on.
"""

from app.models.entities import (
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
from app.models.enums import (
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
    "AnalysisStatus",
    "AuditLog",
    "Finding",
    "FindingCategory",
    "FindingSource",
    "FindingStatus",
    "GitHubInstallation",
    "Patch",
    "PatchStatus",
    "PullRequest",
    "PullRequestStatus",
    "Repository",
    "RepositorySettings",
    "ReviewComment",
    "ReviewerAgent",
    "RiskLevel",
    "Severity",
    "User",
    "ValidationRun",
    "ValidationStatus",
]
