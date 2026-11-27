"""Claim and complete leased import jobs through VLearn's HTTP API."""

import json
import logging
import re
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from pathlib import PurePath
from urllib.parse import urlsplit

from vlearn_importer.config import Settings
from vlearn_importer.structured import CONTRACT, MAX_FILE_BYTES, ParseError, json_bytes, parse_bytes

logger = logging.getLogger(__name__)
JOBS_ENDPOINT = "/api/v1/importer/jobs"
HTTP_TIMEOUT_SECONDS = 20
MAX_API_RESPONSE_BYTES = 64 * 1024
RESULT_ATTEMPTS = 4


class ApiFailure(Exception):
    """Transport or protocol failure without remote response text."""

    def __init__(self, *, retryable=False):
        super().__init__("VLearn importer API request failed")
        self.retryable = retryable


class ResponseTooLarge(ApiFailure):
    pass


@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    filename: str
    lease_token: str
    source_url: str


def response_data(raw):
    try:
        return json.loads(raw)["data"]
    except (ValueError, KeyError, TypeError, RecursionError):
        raise ApiFailure(retryable=True) from None


class ApiClient:
    def __init__(self, settings: Settings):
        self.origin = urlsplit(settings.api_url)
        self.service_token = settings.service_token

    def request(self, method, path, *, body=None, lease_token=None, limit=MAX_API_RESPONSE_BYTES):
        connection_type = HTTPSConnection if self.origin.scheme == "https" else HTTPConnection
        connection = connection_type(self.origin.hostname, self.origin.port, timeout=HTTP_TIMEOUT_SECONDS)
        headers = {
            "Authorization": f"Bearer {self.service_token}",
            "Accept-Encoding": "identity",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if lease_token is not None:
            headers["X-Import-Lease"] = lease_token
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            if not 200 <= response.status < 300:
                raise ApiFailure(retryable=response.status >= 500 or response.status in (408, 429))
            declared_size = response.getheader("Content-Length")
            if declared_size is not None and int(declared_size) > limit:
                raise ResponseTooLarge(retryable=True)
            payload = response.read(limit + 1)
            if len(payload) > limit:
                raise ResponseTooLarge(retryable=True)
            if declared_size is not None and len(payload) != int(declared_size):
                raise ApiFailure(retryable=True)
            return payload
        except (OSError, HTTPException, ValueError):
            raise ApiFailure(retryable=True) from None
        finally:
            connection.close()

    def claim(self):
        claimed = response_data(self.request("POST", f"{JOBS_ENDPOINT}/claim", body=b"{}"))
        if claimed is None:
            return None
        if not isinstance(claimed, dict):
            raise ApiFailure()
        job_id = claimed.get("id")
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id):
            raise ApiFailure()
        kind = claimed.get("kind")
        filename = claimed.get("filename")
        lease = claimed.get("leaseToken")
        expected_source = f"{JOBS_ENDPOINT}/{job_id}/source"
        if (
            not isinstance(kind, str)
            or kind not in CONTRACT["kinds"]
            or not isinstance(filename, str)
            or not 0 < len(filename) <= 512
            or not isinstance(lease, str)
            or not re.fullmatch(r"[!-~]{1,256}", lease)
            or claimed.get("sourceUrl") != expected_source
        ):
            raise ApiFailure()
        return Job(job_id, kind, filename, lease, expected_source)

    def fetch_source(self, job):
        try:
            return self.request(
                "GET", job.source_url, lease_token=job.lease_token, limit=MAX_FILE_BYTES
            )
        except ResponseTooLarge:
            raise ParseError("Tệp không được lớn hơn 5 MiB.") from None

    def submit_result(self, job, body):
        response_data(self.request("POST", f"{JOBS_ENDPOINT}/{job.id}/result", body=body))


def process_job(client: ApiClient, stop) -> bool:
    """Handle one claim. Return whether a result was acknowledged."""
    try:
        job = client.claim()
    except ApiFailure:
        logger.warning("Import claim failed")
        return False
    if job is None or stop.is_set():
        return False

    result = {"leaseToken": job.lease_token, "rows": []}
    try:
        source = client.fetch_source(job)
        result["rows"] = parse_bytes(source, PurePath(job.filename).suffix, job.kind)
    except ParseError as error:
        result["error"] = str(error)
    except ApiFailure:
        logger.warning("Import source download failed")
        return False

    body = json_bytes(result)
    for attempt in range(RESULT_ATTEMPTS):
        try:
            client.submit_result(job, body)
            return True
        except ApiFailure as error:
            if not error.retryable or attempt + 1 == RESULT_ATTEMPTS or stop.wait(2 ** attempt):
                logger.warning("Import result was not acknowledged")
                return False
    return False
