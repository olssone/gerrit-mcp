FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy project metadata and source package
COPY pyproject.toml requirements.txt README.md ./
COPY src/ ./src/

# Install package and dependencies
RUN pip install --no-cache-dir .

# Run via installed console script entry point
CMD ["gerrit-review-mcp"]
