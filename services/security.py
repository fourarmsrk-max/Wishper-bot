import hmac
import hashlib
import time
from urllib.parse import parse_qs

def validate_telegram_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Validates Telegram Web App initData securely.
    Prevents replay attacks by checking auth_date.
    Returns parsed data dict if valid, None otherwise.
    """
    try:
        parsed_data = parse_qs(init_data)
        hash_val = parsed_data.pop("hash", [None])[0]
        if not hash_val:
            return None

        # Check replay attack (allow 60 seconds tolerance)
        auth_date = int(parsed_data.get("auth_date", [0])[0])
        if time.time() - auth_date > 60:
            return None

        # Recreate data-check-string
        data_check_string = "\n".join(
            f"{k}={v[0]}" for k, v in sorted(parsed_data.items())
        )

        # Calculate secret key
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()

        # Calculate hash
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if calculated_hash == hash_val:
            # Convert lists to single values
            return {k: v[0] for k, v in parsed_data.items()}
            
        return None
    except Exception:
        return None
