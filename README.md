# Pyget

A lightweight nuget server written in Python, intended for deployment to Heroku.

Not all routes are currently implemented, so use with caution.

## Usage

### Local

For local testing, start with `foreman start`.

Configure with environment variables, stored in `.env`, for example:

```
# .env
NUGET_API_KEY=somethingsecret
S3_BUCKET=bucket # try also 'bucket/folder', e.g. 'example/packages'
S3_KEY=see https://devcenter.heroku.com/articles/s3#credentials
S3_SECRET=see S3_KEY
DATABASE_URL=postgres://localhost/pyget
```

### Heroku

Pyget is designed to be deployed to Heroku. Start by grabbing the source and creating a new heroku app.

```
$ git clone git@github.com:pearswj/pyget.git
$ cd pyget
$ heroku create
```

Pyget requires a database. How about Postgres?

```
$ heroku addons:add heroku-postgresql:hobby-dev
$ heroku config | grep HEROKU_POSTGRESQL
$ heroku pg:promote HEROKU_POSTGRESQL_<colour>
```

Set the necessary environment variables, e.g.

```
$ heroku config:set NUGET_API_KEY=somethingsecret
```

Finally push the app to Heroku and initialise the database.

```
$ git push heroku master
$ heroku run python
>>> from app import db
>>> db.create_all()
```


## NuGet on OS X

Download and install the MDK from here: http://www.mono-project.com/download/

Type `nuget` into Terminal.
