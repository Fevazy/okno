curl -X POST http://127.0.0.1:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "start": "2026-09-19T00:00:00+00:00",
    "end": "2026-09-19T04:00:00+00:00",
    "step_minutes": 10,
    "mode": "current"
  }'
