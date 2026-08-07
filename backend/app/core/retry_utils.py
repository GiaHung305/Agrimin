from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from google.genai.errors import ServerError

# Chỉ retry lỗi 503 (quá tải tạm thời của Google), KHÔNG retry 429 (quota) —
# vì retry lỗi quota chỉ tốn thêm quota vô ích, không giải quyết được gì.
gemini_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, max=10),
    retry=retry_if_exception_type(ServerError),
    reraise=True,
)
