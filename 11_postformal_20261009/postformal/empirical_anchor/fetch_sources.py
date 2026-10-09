"""Fetch explicitly enumerated public evidence, recording successes and failures.

Run from any working directory. No credentials, retries or access-control bypass.
Existing acquisitions are never overwritten. Output is local feasibility evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SOURCES = {
    "ipsos_history": "https://www.ipsos.com/en-uk/issues-index-2018-onwards",
    "ipsos_archive": "https://www.ipsos.com/en-uk/issues-index-archive",
    "ipsos_jan2018": "https://www.ipsos.com/en-uk/issues-index-january-2018-public-concern-about-nhs-rises",
    "ipsos_aug2026": "https://www.ipsos.com/en-uk/immigration-remains-britains-biggest-issue-concern-about-climate-change-and-environment-rises",
    "google_data_help": "https://support.google.com/trends/answer/4365533?hl=en",
    "google_compare_help": "https://support.google.com/trends/answer/4359550?hl=en-GB",
}
METHOD_SOURCES = {
    "ipsos_feb2018": "https://www.ipsos.com/en-uk/issues-index-february-2018-nhs-and-brexit-continue-dominate-public-concern",
    "ipsos_mar2018": "https://www.ipsos.com/en-uk/brexit-and-nhs-top-britons-concerns-worry-about-housing-rising",
    "ipsos_apr2018": "https://www.ipsos.com/en-uk/issues-index-concern-about-crime-reaches-seven-year-high",
    "ipsos_may2018": "https://www.ipsos.com/en-uk/ipsos-mori-issues-index-may-2018-nhs-and-brexit-are-still-seen-publics-top-issues",
    "ipsos_jun2018": "https://www.ipsos.com/en-uk/ipsos-mori-issues-index-june-2018-publics-two-main-concerns-remain-brexit-and-nhs",
    "ipsos_apr2020": "https://www.ipsos.com/en-uk/ipsos-issues-index-april-2020",
    "google_api_alpha": "https://developers.google.com/search/apis/trends",
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def acquire(key, url, out):
    started = utc()
    record = {"id": key, "requested_url": url, "started_at_utc": started,
              "request_headers": {"User-Agent": "ABM-JASSS-empirical-feasibility/0.1 (public-source-research)"}}
    try:
        request = Request(url, headers=record["request_headers"])
        with urlopen(request, timeout=45) as response:
            body = response.read()
            record.update(status="downloaded", http_status=response.status,
                          final_url=response.url, headers=dict(response.headers))
    except HTTPError as error:
        body = error.read()
        record.update(status="http_error", http_status=error.code, final_url=error.url,
                      headers=dict(error.headers), error=str(error))
    except (URLError, TimeoutError, OSError) as error:
        body = b""
        record.update(status="network_error", http_status=None, error=repr(error))
    path = out / (key + ".body")
    path.write_bytes(body)
    record.update(finished_at_utc=utc(), body_path=path.relative_to(ROOT).as_posix(),
                  bytes=len(body), sha256=sha256(body).hexdigest())
    (out / (key + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record, body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=["sources", "methods", "trends", "url"], required=True)
    parser.add_argument("--id")
    parser.add_argument("--url")
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = ROOT / "raw" / run_id
    out.mkdir(parents=True, exist_ok=False)
    records = []
    if args.group in ("sources", "methods"):
        for key, url in (SOURCES if args.group == "sources" else METHOD_SOURCES).items():
            record, _ = acquire(key, url, out)
            records.append(record)
            print(json.dumps({k: record.get(k) for k in ["id", "status", "http_status", "bytes"]}), flush=True)
    elif args.group == "url":
        if not args.id or not args.url or not args.id.replace("_", "").isalnum():
            parser.error("--url and a letters/digits/underscore --id are required")
        record, _ = acquire(args.id, args.url, out)
        records.append(record)
    else:
        config_path = ROOT / "protocol" / "development_queries.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))["google"]
        for batch in config["batches"]:
            req = {"comparisonItem": [{"keyword": key, "geo": config["geo"], "time": config["date"]}
                                      for key in batch["keywords"]], "category": config["category"], "property": config["property"]}
            url = "https://trends.google.com/trends/api/explore?" + urlencode({"hl": config["hl"], "tz": config["tz"], "req": json.dumps(req, separators=(",", ":"))})
            record, body = acquire("trends_" + batch["id"], url, out)
            record["query"] = req
            records.append(record)
            if record["status"] != "downloaded":
                break
            try:
                payload = json.loads(body.decode("utf-8").removeprefix(")]}'"))
                widgets = [w for w in payload.get("widgets", []) if w.get("id") == "TIMESERIES"]
                if not widgets:
                    record["parse_status"] = "no_timeseries_widget"
                    break
                widget = widgets[0]
                data_url = "https://trends.google.com/trends/api/widgetdata/multiline?" + urlencode({"hl": config["hl"], "tz": config["tz"], "req": json.dumps(widget["request"], separators=(",", ":")), "token": widget["token"]})
                data_record, _ = acquire("trends_" + batch["id"] + "_timeseries", data_url, out)
                records.append(data_record)
                if data_record["status"] != "downloaded":
                    break
            except (ValueError, KeyError, UnicodeDecodeError) as error:
                record["parse_status"] = repr(error)
                break
    manifest = {"schema": "public-acquisition-v1", "run_id": run_id, "group": args.group,
                "python": sys.version, "platform": platform.platform(), "records": records,
                "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                "development_queries_sha256": sha256((ROOT / "protocol/development_queries.json").read_bytes()).hexdigest()}
    (out / "acquisition_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(out / "acquisition_manifest.json"), "records": [{k: r.get(k) for k in ("id", "status", "http_status", "bytes")} for r in records]}))


if __name__ == "__main__":
    main()
