# Reproducible builds

Use Python 3.12. Compile `requirements.txt` with uv 0.11.32 and compare it with `requirements.lock`; install only with `--require-hashes`. Build the digest-pinned image with a full `GIT_REVISION`. CI records a source archive, CycloneDX SBOM, lock digest, provenance, and image ID. Do not publish or promote.
