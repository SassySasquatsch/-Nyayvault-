import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    # --- General ---
    APP_NAME: str = "NyayVault API"
    APP_VERSION: str = "1.0.0"
    ENV: str = os.getenv("ENV", "development")
    
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'nyayvault.db'}"
    )

    # --- Auth / JWT ---
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "dev-secret-key-change-this-in-production-please"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")  # 8 hour shift
    )

    # --- File storage ---
    STORAGE_DIR: Path = Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage")))
    EVIDENCE_DIR: Path = STORAGE_DIR / "evidence"
    REPORTS_DIR: Path = STORAGE_DIR / "reports"
    FORENSIC_REPORTS_DIR: Path = STORAGE_DIR / "forensic_reports"   # uploaded examination reports
    COURT_ORDERS_DIR: Path = STORAGE_DIR / "court_orders"   # uploaded court orders / judgments
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "250"))

    # --- Blockchain anchoring (app/utils/blockchain_anchor.py) ---
    # That module reads these but config.py never defined them, so every upload's
    # background anchoring task crashed with AttributeError. Defaults keep the
    # layer OFF, which is what the module documents as the default.
    #
    # WEB3_PROVIDER_URI / WALLET_PRIVATE_KEY are the names used for a live
    # public testnet (e.g. Polygon Amoy). BLOCKCHAIN_RPC_URL /
    # BLOCKCHAIN_PRIVATE_KEY are kept as older aliases so an existing local
    # setup with those names still works -- whichever pair is set wins, with
    # the WEB3_/WALLET_ names taking priority when both are present.
    BLOCKCHAIN_ANCHORING_ENABLED: bool = os.getenv("BLOCKCHAIN_ANCHORING_ENABLED", "false").lower() in ("1", "true", "yes")
    BLOCKCHAIN_RPC_URL: str = os.getenv(
        "WEB3_PROVIDER_URI", os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    )
    BLOCKCHAIN_PRIVATE_KEY: str = os.getenv(
        "WALLET_PRIVATE_KEY", os.getenv("BLOCKCHAIN_PRIVATE_KEY", "")
    )
    # Default stays 1337 (a local dev chain) so nothing changes for existing
    # local setups; set BLOCKCHAIN_CHAIN_ID=80002 for Polygon Amoy.
    BLOCKCHAIN_CHAIN_ID: int = int(os.getenv("BLOCKCHAIN_CHAIN_ID", "1337"))
    BLOCKCHAIN_CONTRACT_ADDRESS: str = os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS", "")
    BLOCKCHAIN_GAS_LIMIT: int = int(os.getenv("BLOCKCHAIN_GAS_LIMIT", "200000"))
    BLOCKCHAIN_TX_TIMEOUT_SECONDS: int = int(os.getenv("BLOCKCHAIN_TX_TIMEOUT_SECONDS", "60"))
    # How long to wait for the RPC endpoint itself to respond before treating
    # it as unreachable (separate from BLOCKCHAIN_TX_TIMEOUT_SECONDS, which is
    # how long to wait for a transaction to be *mined*).
    BLOCKCHAIN_RPC_TIMEOUT_SECONDS: int = int(os.getenv("BLOCKCHAIN_RPC_TIMEOUT_SECONDS", "15"))
    # Optional explicit block-explorer base URL, e.g.
    # "https://amoy.polygonscan.com/tx/". When unset, blockchain_anchor.py
    # falls back to a small built-in table keyed by BLOCKCHAIN_CHAIN_ID
    # (Polygon Amoy, Polygon mainnet, Sepolia, Ethereum mainnet).
    BLOCKCHAIN_EXPLORER_BASE_URL: str = os.getenv("BLOCKCHAIN_EXPLORER_BASE_URL", "")

    # --- ABAC (organisational segregation) ---------------------------------
    # Everything below is configuration, not code: nothing here names a state,
    # district or unit. See app/abac.py for how these are used.
    #
    # Which user/case attributes must match for organisational scope. Each
    # name must be a column present on BOTH `users` and `cases`. Drop one
    # (e.g. "state,unit") to segregate on fewer levels.
    ABAC_SCOPE_ATTRIBUTES: tuple = tuple(
        a.strip() for a in os.getenv("ABAC_SCOPE_ATTRIBUTES", "state,district,unit").split(",") if a.strip()
    )
    # Roles that are exempt from organisational scoping (system oversight).
    ABAC_ORG_WIDE_ROLES: tuple = tuple(
        r.strip() for r in os.getenv("ABAC_ORG_WIDE_ROLES", "admin").split(",") if r.strip()
    )
    # Roles that must ALSO be the assigned/owning officer of a case, on top of
    # matching its organisational scope.
    ABAC_ASSIGNMENT_ROLES: tuple = tuple(
        r.strip() for r in os.getenv("ABAC_ASSIGNMENT_ROLES", "io").split(",") if r.strip()
    )
    # Optional document-type limits per role, e.g. '{"judge": ["PDF", "VIDEO"]}'.
    # A role that is not listed may act on every document type.
    ABAC_ROLE_DOC_TYPES: dict = json.loads(os.getenv("ABAC_ROLE_DOC_TYPES", "{}") or "{}")

    # --- CORS ---
    # Comma-separated list of allowed origins. "*" for local/demo use.
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")


settings = Settings()

settings.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
settings.FORENSIC_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
settings.COURT_ORDERS_DIR.mkdir(parents=True, exist_ok=True)
