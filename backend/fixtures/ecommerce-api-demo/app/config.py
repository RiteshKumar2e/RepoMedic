"""Application configuration."""

from fastapi.middleware.cors import CORSMiddleware

DATABASE_URL = "postgresql://shop:shop@localhost:5432/shop"

# FINDING: hardcoded payment credential committed to source control.
STRIPE_SECRET_KEY = ""

# FINDING: hardcoded signing secret — anyone with repo access can forge tokens.
JWT_SIGNING_SECRET = "s3cr3t-signing-key-do-not-share-9f2b"

TOKEN_TTL_SECONDS = 3600
DEFAULT_PAGE_SIZE = 50
INVOICE_DIRECTORY = "/var/app/invoices"


def install_cors(app):
    """Allow the storefront to call the API."""
    # FINDING: wildcard origin combined with credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
