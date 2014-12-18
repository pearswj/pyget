# Pyget

A lightweight nuget server written in Python, intended for deployment to Heroku.

Not all routes are currently implemented, so use with caution.

## Usage

For local testing, start with `foreman run python app.py`.

Configure with environment variables, stored in `.env`, for example:

```
# required
NUGET_API_KEY=somethingsecret
S3_BUCKET=bucket # try also 'bucket/folder', e.g. 'example/packages'
S3_KEY=see https://devcenter.heroku.com/articles/s3#credentials
S3_SECRET=see S3_KEY
DATABASE_URL=postgres://localhost/pyget

# optional
DEBUG=True
FLASK_PORT=80
```

## NuGet on OS X

Download and install the MDK from here: http://www.mono-project.com/download/

Type `nuget` into terminal.
