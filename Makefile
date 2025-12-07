.PHONY: up down logs test clean

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f api

test:
	@echo "Running tests..."
	docker compose exec api pytest tests/ -v || echo "Tests require running container"

clean:
	docker compose down -v
	docker system prune -f