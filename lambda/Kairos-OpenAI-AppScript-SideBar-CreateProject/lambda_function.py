import os
import json
import boto3
from datetime import datetime
import logging
from openai import OpenAI

from open_ai_prompt import generate_openai_result

from appconfig_manager import AppConfigClient, AppConfigError

lambda_client = boto3.client('lambda')  # client to invoke other Lambda functions

# ─── Logging Setup ─────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Environment selection (dev / prod) ───────────────────────────────────────
ENV = os.environ.get("ENVIRONMENT", "prod").strip().lower()   # "dev" or "prod"

def _get_appconfig_env_id() -> str:
    """
    Return the correct AppConfig environment ID based on ENV.
    Uses only APPCONFIG_ENV_ID_DEV / APPCONFIG_ENV_ID_PROD.
    """
    if ENV == "dev" or ENV == "staging":
        env_id = os.environ.get("APPCONFIG_ENV_ID_DEV")
        if not env_id:
            raise RuntimeError("APPCONFIG_ENV_ID_DEV must be set when ENVIRONMENT=dev")
        logger.info(f"[AppConfig] Using DEV environment id: {env_id}")
        return env_id

    if ENV == "prod":
        env_id = os.environ.get("APPCONFIG_ENV_ID_PROD")
        if not env_id:
            raise RuntimeError("APPCONFIG_ENV_ID_PROD must be set when ENVIRONMENT=prod")
        logger.info(f"[AppConfig] Using PROD environment id: {env_id}")
        return env_id

    # If someone sets ENVIRONMENT to something unexpected
    raise RuntimeError("ENVIRONMENT must be either 'dev' or 'prod'")

# ─── Get App Configurations ────────────────────────────────────────────────────────
config_client = AppConfigClient(
            app_id=os.environ.get("APPCONFIG_APP_ID"),
            env_id=_get_appconfig_env_id(),
            profile_id=os.environ.get("APPCONFIG_PROFILE_ID"),
            region=os.environ.get("AWS_REGION", "us-west-1"),
            ttl_seconds= int(os.environ.get("APPCONFIG_POLL_INTERVAL_SEC", "60")),
        )

config_metadata = config_client.get_config()
logger.info(f"App Config Service : {config_metadata.get('config_metadata')}")

# ─── Error Codes ──────────────────────────────────────────────────────────────
ERROR_CODES = {
    "MISSING_FIELDS": "ERR_MISSING_FIELDS",
    "USER_LOOKUP_FAILED": "ERR_USER_LOOKUP_FAILED",
    "OPENAI_FAILED": "ERR_OPENAI_FAILED",
    "INTERACTION_BUILD_FAILED": "ERR_INTERACTION_BUILD_FAILED",
    "INTERNAL": "ERR_INTERNAL"
}

# ─── Module-scope cache - START────────────────────────────────────────────────
_OPENAI_KEY = None
_OPENAI_CLIENT = None

# Create the Secrets Manager client once
_SECRETS_CLIENT = boto3.client(
    "secretsmanager",
    region_name=os.environ.get("AWS_REGION", "us-west-1")
)


def get_secret() -> str:
    """
    Lazily fetch and cache the OpenAI API key from AWS Secrets Manager.
    """
    global _OPENAI_KEY
    if _OPENAI_KEY is not None:
        return _OPENAI_KEY

    secret_name = os.environ.get("OPENAI_SECRET_NAME", "SchoolFuel-OPENAI-API-KEY")
    resp = _SECRETS_CLIENT.get_secret_value(SecretId=secret_name)
    secret = json.loads(resp["SecretString"])
    _OPENAI_KEY = secret["OPENAI_API_KEY"]

    return _OPENAI_KEY


def get_openai_client() -> OpenAI:
    """
    Lazily construct and cache a single OpenAI client instance.
    """
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is not None:
        return _OPENAI_CLIENT

    key = get_secret()
    _OPENAI_CLIENT = OpenAI(api_key=key)
    return _OPENAI_CLIENT

# ─── Handler Function Begins ──────────────────────────────────────────────────
def lambda_handler(event, context):
    
    try:
        # 1) Input validation
        prompt = event.get("message")
        email_id = event.get("email_id")
        if not prompt or not email_id:
            logger.warning("Missing required fields: message or email_id")
            return {
                "status": "failed",
                "error_code": ERROR_CODES["MISSING_FIELDS"],
                "error": "Missing required field: 'message' or 'email_id'"
            }

        # 3) Load OpenAI client
        client = get_openai_client()

        # 4) Generate project JSON from OpenAI
        try:
            project_json, openai_response = generate_openai_result(
                user_prompt=prompt,
                client=client,
                config_client=config_client,
                max_retries=2
            )

        except Exception:
            logger.exception("OpenAI request failed")
            return {
                "status": "failed",
                "error_code": ERROR_CODES["OPENAI_FAILED"],
                "error": "OpenAI request failed. Please try again."
            }
        

        # 5) Build interaction payload
        try:
            interaction_Payload = {
                "email_id": email_id,
                "response": openai_response.to_dict() if hasattr(openai_response, "to_dict") else str(openai_response),
                "interaction_type": "Karios_OpenAI_AppScript_SideBar_CreateProject"
            }
        except Exception:
            logger.exception("Failed to build interaction payload")
            return {
                "status": "failed",
                "error_code": ERROR_CODES["INTERACTION_BUILD_FAILED"],
                "error": "Failed to build interaction data"
            }

        # 6) Final response
        return {
            "user_response": {
                "response": project_json,
                "generatedAt": datetime.utcnow().isoformat() + "Z"
            },
        }

    except Exception:
        # Catch-all safeguard
        logger.error("Unhandled exception in action lambda", exc_info=True)
        return {
            "status": "failed",
            "error_code": ERROR_CODES["INTERNAL"],
            "error": "Something went wrong. Please try again later."
        }