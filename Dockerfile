# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Copy the whole build context, then locate the app inside it. This keeps the build working if the repo is
# nested one folder deeper than expected or the context is only backend/, and prints a clear error otherwise.
COPY . /build
RUN <<EOS
set -e
SRV=${SRV:-/srv}; BUILD=${BUILD:-/build}
main=$(find "$BUILD" -path '*/app/main.py' -not -path '*/node_modules/*' | head -1)
if [ -z "$main" ]; then echo "ERROR: backend app/main.py not found in the build context. Build context contains:"; find "$BUILD" -maxdepth 3 | head -40; echo "Check Render: Root Directory blank, Docker Build Context Directory = ., and that backend/ is committed to the repo."; exit 1; fi
appdir=$(dirname "$main"); root=$(dirname "$appdir")
req=$(find "$root" "$BUILD" -maxdepth 2 -name requirements.txt | head -1)
[ -n "$req" ] || { echo "ERROR: requirements.txt not found"; exit 1; }
mkdir -p "$SRV"; cp -r "$appdir" "$SRV/app"
fe=$(find "$BUILD" -maxdepth 3 -name index.html -path '*frontend*' | head -1)
[ -n "$fe" ] && cp -r "$(dirname "$fe")" "$SRV/frontend" || echo "note: frontend/ not found, API only"
echo "$req" > "$SRV/.req"; echo "staged app from: $appdir, requirements: $req"
EOS
RUN pip install --no-cache-dir -r "$(cat /srv/.req)" && rm -f /srv/.req && rm -rf /build && useradd -m app && chown -R app /srv
WORKDIR /srv
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
