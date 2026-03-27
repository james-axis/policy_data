from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-southeast-2"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # Axis CRM
    axis_crm_api_url: str = ""
    axis_crm_api_token: str = ""

    # Browserbase
    browserbase_api_key: str = ""
    browserbase_project_id: str = ""

    # Worker
    max_worker_concurrency: int = 5
    claude_max_turns: int = 30
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
