A lightweight nuget server written in Python, intended for deployment to Heroku.

Start with `foreman run python app.py`.

Configure with environment variables, stored in `.env` for local use.

```
DEBUG=True
NUGET_API_KEY=somethingsecret # required
FLASK_PORT=80
```
