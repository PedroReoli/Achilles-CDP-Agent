"""Benchmark reproduzível da sessão CDP com fixture local e Chromium descartável."""

import argparse
import asyncio
import importlib.metadata
import json
import math
import platform
import socket
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from achilles.services.application import ApplicationServices


def available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fixture_html(element_count: int) -> str:
    buttons = "".join(
        f'<button aria-label="Ação {index}">Ação {index}</button>'
        for index in range(element_count)
    )
    article = " ".join("Conteúdo de exemplo para medir o Reader Mode." for _ in range(30))
    return (
        '<!doctype html><html><head><title>Achilles benchmark</title></head><body>'
        '<main><article><h1>Achilles benchmark</h1><p>' + article + '</p></article>'
        '<button aria-label="Incrementar" onclick="document.body.dataset.clicks = '
        'String(Number(document.body.dataset.clicks || 0) + 1)">Incrementar</button>'
        + buttons + '</main></body></html>'
    )


def latency_summary(measurements: List[float]) -> Dict[str, float]:
    ordered = sorted(measurements)
    return {
        "p50_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2),
        "min_ms": round(ordered[0], 2),
        "max_ms": round(ordered[-1], 2),
    }


def size_comparison(raw_chars: int, compact_chars: int) -> Dict[str, Any]:
    return {
        "raw_html_chars": raw_chars,
        "output_chars": compact_chars,
        "raw_tokens_estimated": math.ceil(raw_chars / 4),
        "output_tokens_estimated": math.ceil(compact_chars / 4),
        "savings_percent_estimated": round(
            max(0, 1 - compact_chars / max(1, raw_chars)) * 100, 1
        ),
    }


async def benchmark(samples: int, element_count: int) -> Dict[str, Any]:
    from playwright.async_api import async_playwright

    cdp_port = available_port()
    owner = await async_playwright().start()
    browser = None
    app: Optional[ApplicationServices] = None
    try:
        started = time.perf_counter()
        browser = await owner.chromium.launch(
            headless=True, args=[f"--remote-debugging-port={cdp_port}"]
        )
        launch_ms = (time.perf_counter() - started) * 1000
        page = await browser.new_page()
        await page.set_content(fixture_html(element_count))
        app = ApplicationServices(cdp_port)

        started = time.perf_counter()
        pages = await app.session.list_pages()
        attach_ms = (time.perf_counter() - started) * 1000
        page_id = next(
            row["page_id"] for row in pages["pages"] if row["title"] == "Achilles benchmark"
        )
        snapshot_args = {"page_id": page_id, "limit": element_count + 1}

        cold_times: Dict[str, float] = {}
        started = time.perf_counter()
        await app.call("browser_snapshot", snapshot_args)
        cold_times["snapshot_ms"] = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        await app.call("browser_read_content", {"page_id": page_id})
        cold_times["read_ms"] = (time.perf_counter() - started) * 1000

        for _ in range(2):
            await app.call("browser_snapshot", snapshot_args)
            await app.call("browser_read_content", {"page_id": page_id})

        timings: Dict[str, List[float]] = {"snapshot": [], "read": [], "act_click": []}
        last_snapshot: Dict[str, Any] = {}
        last_read: Dict[str, Any] = {}
        for _ in range(samples):
            started = time.perf_counter()
            last_snapshot = await app.call("browser_snapshot", snapshot_args)
            timings["snapshot"].append((time.perf_counter() - started) * 1000)

            started = time.perf_counter()
            last_read = await app.call("browser_read_content", {"page_id": page_id})
            timings["read"].append((time.perf_counter() - started) * 1000)

            target = next(
                row for row in last_snapshot["elements"] if row["name"] == "Incrementar"
            )
            started = time.perf_counter()
            result = await app.call(
                "browser_action",
                {
                    "action": "click",
                    "page_id": page_id,
                    "snapshot_id": last_snapshot["snapshot_id"],
                    "element_ref": target["element_ref"],
                },
            )
            timings["act_click"].append((time.perf_counter() - started) * 1000)
            if result["status"] != "executed":
                raise RuntimeError("A ação do benchmark não foi executada")

        if await page.get_attribute("body", "data-clicks") != str(samples):
            raise RuntimeError("A contagem de cliques da fixture não confere")
        raw_chars = len(await page.content())
        return {
            "schema_version": 1,
            "measured_at_utc": datetime.now(timezone.utc).isoformat(),
            "fixture": "set_content local, sem rede externa",
            "elements": element_count,
            "samples": samples,
            "environment": {
                "os": platform.platform(),
                "python": platform.python_version(),
                "playwright": importlib.metadata.version("playwright"),
                "chromium": browser.version,
            },
            "cold": {
                "browser_launch_ms": round(launch_ms, 2),
                "cdp_attach_ms": round(attach_ms, 2),
                **{key: round(value, 2) for key, value in cold_times.items()},
            },
            "warm": {name: latency_summary(values) for name, values in timings.items()},
            "size_comparison": {
                "snapshot": size_comparison(raw_chars, len(last_snapshot.get("compact", ""))),
                "read": size_comparison(raw_chars, len(last_read.get("markdown", ""))),
                "method": "aproximação de 4 caracteres por token; não usa tokenizer de LLM",
            },
        }
    finally:
        try:
            if app is not None:
                await app.close()
        finally:
            try:
                if browser is not None:
                    await browser.close()
            finally:
                await owner.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--elements", type=int, default=50)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 3 <= args.samples <= 200 or not 1 <= args.elements <= 500:
        parser.error("--samples deve estar entre 3 e 200; --elements entre 1 e 500")
    result = asyncio.run(benchmark(args.samples, args.elements))
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
