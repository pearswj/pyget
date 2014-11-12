from flask import Flask, Response, request, make_response
from flask.ext.sqlalchemy import SQLAlchemy
import zipfile, xmltodict, traceback
from werkzeug import secure_filename
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgres://localhost/pyget'
db = SQLAlchemy(app)

app.config['DEBUG'] = os.environ.get('DEBUG', False)
app.config['NUGET_API_KEY'] = os.environ.get('NUGET_API_KEY')
if not app.config['NUGET_API_KEY']:
    raise Exception('NUGET_API_KEY setting is required')

class Package(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True)
    version = db.Column(db.String(80), unique=True)

    def __init__(self, name, version):
        self.name = name
        self.version = version

    def __repr__(self):
        return '<Package %r %r>' % (self.name, self.version)

    # TODO: one-to-many relationship between package and version?
    # TODO: store more metadata in db

@app.route('/$metadata')
def show_metadata():
    with open('metadata.xml', 'r') as f:
        xml = f.read()
        return Response(xml, mimetype='text/xml')

@app.route('/api/v2/package/', methods=['PUT'])
def upload():
    try:
        key = request.headers.get('X_NUGET_APIKEY')
        if not key or key != app.config['NUGET_API_KEY']:
            return 'Invalid or missing API key', 403
        file = request.files['package']
        if not file:
            return 'No package file', 400
        package = zipfile.ZipFile(file, 'r')
        nuspec = next((x for x in package.namelist() if x.endswith('.nuspec')), None)
        if not nuspec:
            return 'NuSpec file not found in package', 400
        with package.open(nuspec, 'r') as f:
            xml = xmltodict.parse(f)
        metadata = xml['package']['metadata']
        name = metadata['id'] + '.' + metadata['version'] + '.nupkg'
        filename = secure_filename(name)
        # TODO: push this file to s3 and remember its location
        pkg = Package.query.filter_by(name=metadata['id'], version=metadata['version']).first()
        if pkg:
            return 'This package version already exists', 409
        pkg = Package(metadata['id'], metadata['version'])
        db.session.add(pkg)
        db.session.commit()
        # TODO: add more metadata to db
    except:
        traceback.print_exc()
        return 'Error pushing package', 500
    return "Created", 201

@app.route('/api/v2/package/<name>/<version>', methods=['DELETE'])
def delete(name, version):
    try:
        pkg = Package.query.filter_by(name=name, version=version).first()
        if pkg:
            db.session.delete(pkg)
            db.session.commit()
            # TODO: remove .nupkg from s3
            return 'Deleted', 204
        else:
            return 'No package by this name and with this version', 400
    except:
        traceback.print_exc()
        return 'Error deleting package', 500

@app.route('/ping')
def ping():
    return "pong"

if __name__ == "__main__":
    app.run(port=int(os.environ.get('FLASK_PORT', 5000)))
