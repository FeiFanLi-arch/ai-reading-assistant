.PHONY: install run test docker
install:
	python -m pip install -r requirements-dev.txt
run:
	python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
test:
	python -m pytest
docker:
	docker compose up --build -d
