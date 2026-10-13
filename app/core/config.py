from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = ElevenData
    APP_TAGLINE: str = "Airtime · Data · Bills — one tap away"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1"

    SECRET_KEY: str = "dev-secret-do-not-use-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    RESET_TOKEN_EXPIRE_MINUTES: int = 30

    DATABASE_URL: str = "sqlite:///./zaply.db"

    VTU_PROVIDER: str = "mock"
    PROVIDER_MODE: str = "sandbox"

    # bsokdata.com adapter (VTU_PROVIDER=bsokdata activates it for airtime & data)
    BSOKDATA_BASE_URL: str = "https://bsokdata.com"
    BSOKDATA_API_KEY: str = ""
    PAYMENT_GATEWAY: str = "mock"
    PAYMENT_SECRET_KEY: str = "sk_test_server_only_replace_me"
    PAYMENT_PUBLIC_KEY: str = "pk_test_client_safe"
    PAYMENT_WEBHOOK_SECRET: str = "whsec_server_only"

    # Dedicated virtual account shown on the dashboard for wallet funding by transfer
    VA_BANK_NAME: str = "Palmpay"

    # Announcement shown once per day after a successful sign-in (null CTA hides the button)
    ANNOUNCEMENT_ENABLED: bool = True
    ANNOUNCEMENT_TITLE: str = "Zero fees, every single day"
    ANNOUNCEMENT_BODY: str = (
        "All airtime and data top-ups on Zaply are completely fee-free. Fund your wallet "
        "once and pay bills, subscribe to cable TV and more — all at no extra charge."
    )
    ANNOUNCEMENT_CTA_LABEL: str | None = "Fund your wallet"
    ANNOUNCEMENT_CTA_PATH: str | None = "/wallet"

    # Comma-separated emails granted access to the admin console (/admin.html)
    ADMIN_EMAILS: str = "demo@zaply.ng"

    SEED_DEMO_DATA: bool = True

    RATE_LIMIT_AUTH_REQUESTS: int = 10
    RATE_LIMIT_AUTH_WINDOW: int = 60

    PIN_MAX_ATTEMPTS: int = 5
    PIN_LOCKOUT_SECONDS: int = 300

    # SMTP email settings
    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = None
    SMTP_USER: str | None = None
    SMTP_PASS: str | None = None
    SMTP_FROM: str | None = None
    ADMIN_EMAIL: str | None = None

    # VAPID key for push notifications (alternative to file)
    VAPID_PRIVATE_KEY: str | None = None

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
