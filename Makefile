.PHONY: install dev lint format clean build-local run

install:
	python3 -m pip install -r requirements.txt

dev:
	python3 -m pip install -r requirements.txt
	python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint:
	ruff check app/

format:
	ruff format app/

build-local:
	podman build -f Containerfile -t embedding-api:latest .

run:
	podman run --rm -p 8000:8000 \
		-v hf-cache:/app/.cache/huggingface \
		harbor.prod.skatzi.com/library/embedding-api:latest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
