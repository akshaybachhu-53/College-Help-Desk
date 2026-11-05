"""
Downloads the publicly posted IIT Jodhpur PDFs listed in data/manifest.csv
(rows whose how_obtained column mentions this script) into data/raw/.

The iitj.ac.in server does not send its intermediate certificate, so plain
`requests` fails with CERTIFICATE_VERIFY_FAILED on most Linux machines even though
browsers open the links fine. We download the missing intermediate certificate from
the CA and verify the full chain with it (see INTERMEDIATES). If that does not work on
your network, the script prints the links: open them in a browser and save each PDF
into data/raw/ under the filename shown.

Run:  python scripts/fetch_public_docs.py
"""
from __future__ import annotations

import csv
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


# iitj.ac.in sends only its leaf certificate. The missing intermediate is published by the CA
# at this (plain-HTTP, by design) URL; we add it to certifi's roots, so the server chain is
# still fully verified against a trusted root.
INTERMEDIATES = {
    "iitj.ac.in": "http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt",
}


@lru_cache(maxsize=None)
def verify_for_host(host: str):
    """Return a CA-bundle path that includes the host's missing intermediate, or True."""
    url = next((u for h, u in INTERMEDIATES.items() if host == h or host.endswith("." + h)), None)
    if not url:
        return True
    try:
        import ssl
        import certifi
        der = requests.get(url, timeout=30).content
        pem = der.decode() if der.startswith(b"-----BEGIN") else ssl.DER_cert_to_PEM_cert(der)
        bundle = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        bundle.write(Path(certifi.where()).read_text() + "\n" + pem)
        bundle.close()
        return bundle.name
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not fetch intermediate certificate for {host}: {e}")
        return True


def main() -> int:
    rows = [r for r in csv.DictReader((ROOT / "data" / "manifest.csv").open(encoding="utf-8"))
            if "fetch_public_docs" in r["how_obtained"]]
    failed = []
    for r in rows:
        dest = RAW / r["filename"]
        if dest.exists() and dest.stat().st_size > 1000:
            print(f"[skip] {r['filename']} already present")
            continue
        try:
            resp = requests.get(r["url"], timeout=60, verify=verify_for_host(urlparse(r["url"]).hostname))
            resp.raise_for_status()
            if not resp.content.startswith(b"%PDF"):
                raise ValueError("response is not a PDF")
            dest.write_bytes(resp.content)
            print(f"[ok]   {r['filename']}  ({len(resp.content) // 1024} KB)")
        except Exception as e:  # noqa: BLE001
            failed.append(r)
            print(f"[fail] {r['filename']}: {type(e).__name__}: {str(e)[:120]}")
    if failed:
        print("\nDownload these in a browser and save them into data/raw/ with exactly these names:")
        for r in failed:
            print(f"  {r['filename']:48s} <- {r['url']}")
        return 1
    print("\nAll public documents present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
