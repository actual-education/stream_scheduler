import time
from typing import Callable, TypeVar

T = TypeVar("T")


def run_with_retries(
    func: Callable[[], T],
    *,
    max_retries: int,
    base_delay_seconds: float,
) -> T:
    attempt = 0
    while True:
        try:
            return func()
        except Exception:
            attempt += 1
            if attempt >= max_retries:
                raise
            time.sleep(base_delay_seconds * (2 ** (attempt - 1)))
