"""Small opt-in HTTP load smoke test for a running non-production environment."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_once(url: str, timeout: float) -> tuple[bool, float, str]:
    started = time.perf_counter()
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            response.read()
            return response.status == 200, time.perf_counter() - started, str(response.status)
    except (HTTPError, URLError, TimeoutError) as exc:
        return False, time.perf_counter() - started, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--path", default="/health/ready")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("--requests and --concurrency must be positive")

    url = args.base_url.rstrip("/") + "/" + args.path.lstrip("/")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda _: request_once(url, args.timeout), range(args.requests)))
    elapsed = time.perf_counter() - started
    successes = sum(1 for success, _, _ in results if success)
    latencies = sorted(duration for _, duration, _ in results)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    print(f"requests={args.requests} concurrency={args.concurrency} success={successes} elapsed={elapsed:.2f}s p95={p95:.3f}s")
    return 0 if successes == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
