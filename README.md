# Travel Web App 

Production-style FastAPI travel website

## Highlights

- Layered structure: API, schemas, services, config, templates, static assets
- Async weather intelligence with current + date-based expected weather
- Built-in budget optimizer (LOW, MEDIUM, LUXURY)
- Aesthetic front-end with responsive layout and polished styling
- Clean API contract with input validation

## Project Structure

app/
- api/routes.py
- core/config.py
- schemas/travel.py
- services/planner.py
- templates/base.html
- templates/index.html
- static/css/styles.css
- static/js/app.js
- main.py

run.py

## Quick Start

1. Create/activate your virtual environment.
2. Install dependencies:

	pip install -r requirements.txt

3. Run the app:

	python run.py

4. Open:

	http://127.0.0.1:8000

## API

- Health: GET /api/v1/health
- Plan: POST /api/v1/plan

Example request body:

{
  "city": "Paris",
  "check_in": "2026-03-23",
  "check_out": "2026-03-27",
  "adults": 2,
  "budget_amount": 50000,
  "budget_currency": "INR",
  "style": "luxury"
}

## Environment

Optional .env keys:

- APP_NAME
- ENVIRONMENT
- DEBUG
- HOST
- PORT

