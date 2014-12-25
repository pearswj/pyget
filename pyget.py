from flask import Flask, Response, request, make_response, redirect
from models import db, Package, Version
import zipfile, xmltodict, traceback
from werkzeug import secure_filename
import os
from datetime import datetime
import semantic_version as sem_ver
import pystache
import hashlib, base64

app = Flask(__name__)

# required settings
settings = [
    'DATABASE_URL',
    'PYGET_API_KEY',
    'PYGET_S3_KEY',
    'PYGET_S3_SECRET',
    'PYGET_S3_BUCKET'
    ]
for setting in settings:
    app.config[setting] = os.environ.get(setting)
    if not app.config[setting]:
        raise Exception(setting + ' setting is required')

# optional settings
app.config['DEBUG'] = os.environ.get('DEBUG', False)

# db
app.config['SQLALCHEMY_DATABASE_URI'] = app.config['DATABASE_URL']
db.init_app(app)

from sqlalchemy_utils import database_exists
from sqlalchemy.exc import OperationalError
try:
    if not database_exists(app.config['DATABASE_URL']):
        raise Exception('No database found at ' + app.config['DATABASE_URL'])
except OperationalError:
    raise Exception('Are you sure the db exists and/or is running?')

def init_db():
    """Call this to initialise the database."""
    with app.app_context():
        db.create_all()

# s3 bucket
import boto

def init_s3(key, secret, bucket_name):
    bucket_tmp = bucket_name.strip('/').split('/')
    bucket_string = bucket_tmp[0]
    print 'Connecting to S3...'
    s3 = boto.connect_s3(key, secret)
    try:
        bucket = s3.get_bucket(bucket_string)
        print 'Connected to S3!'
    except boto.exception.S3ResponseError as e:
        print 'Bucket not found so I\'m creating one for you'
        bucket = s3.create_bucket(bucket_string)
    # s3 dir
    if len(bucket_tmp) > 1:
        path_string = '/'.join(bucket_tmp[1:]) + '/'
    else:
        path_string = ''
    return bucket, (bucket_string, path_string)

bucket, path = init_s3(
    app.config['PYGET_S3_KEY'],
    app.config['PYGET_S3_SECRET'],
    app.config['PYGET_S3_BUCKET']
    )
app.config['PYGET_S3_BUCKET'], app.config['PYGET_S3_PATH'] = path



@app.route('/$metadata')
def show_metadata():
    with open('metadata.xml', 'r') as f:
        xml = f.read()
        return Response(xml, mimetype='text/xml')

def coerce_version(ver_str):
    """Attempts to return a Sem Ver compliant version string."""
    # see https://github.com/NuGet/NuGetGallery/pull/1573
    if '-' in ver_str:
        tmp = ver_str.split('-', 1)
        tmp = [tmp[0], '-', tmp[1]]
    elif '+' in ver_str:
        tmp = ver_str.split('+', 1)
        tmp = [tmp[0], '+', tmp[1]]
    else:
        tmp = [ver_str]

    tmp2 = tmp[0].split('.')
    tmp2 = [x.lstrip('0') for x in tmp2]
    tmp2 = [x if x else '0' for x in tmp2]

    if len(tmp) > 1:
        tmp = ['.'.join(tmp2)] + tmp[1:]

    tmp = ''.join(tmp)

    try:
        v = sem_ver.Version.coerce(tmp)
        return str(v), bool(v.prerelease)
    except:
        raise Exception('Could not coerce semantic version from ' + ver_str)

@app.route('/', methods=['GET'])
def index():
    xml = """<?xml version='1.0' encoding='utf-8' standalone='yes'?>
<service xml:base="{base_url}"
    xmlns:atom="http://www.w3.org/2005/Atom"
    xmlns:app="http://www.w3.org/2007/app"
    xmlns="http://www.w3.org/2007/app">
  <workspace>
    <atom:title>Default</atom:title>
    <collection href="Packages">
      <atom:title>Packages</atom:title>
    </collection>
  </workspace>
</service>""".format(base_url=request.base_url)
    return Response(xml, mimetype='text/xml')

@app.route('/Search()/$count')
@app.route('/Packages()')
def search():
    print request.args
    # TODO: implement routes
    return "Nothing to see here, yet!", 501

@app.route('/package/<id>/<version>')
def download(id, version):
    pkg = Package.query.filter_by(name=id).first()
    if pkg:
        ver = pkg.versions.filter_by(version=version).first()
        if ver:
            name = ver.package.name + '.' + ver.version + '.nupkg'
            filename = app.config['PYGET_S3_PATH'] + secure_filename(name)
            s3_url = 'https://s3-eu-west-1.amazonaws.com/' + \
                app.config['PYGET_S3_BUCKET'] + '/' + filename
            return redirect(s3_url)

@app.route('/Packages(Id=\'<id>\',Version=\'<version>\')')
def packages(id, version):
    pkg = Package.query.filter_by(name=id).first()
    if pkg:
        ver = pkg.versions.filter_by(version=version).first()
        if ver:
            env = ver.to_json()
            env['base_url'] = '/'.join(request.base_url.split('/')[:-1])
            renderer = pystache.Renderer()
            xml = renderer.render_path('packages.mustache', env)
            return Response(xml, mimetype='application/atom+xml')
    return 'No package by this name and with this version', 404

@app.route('/api/v2/package/', methods=['PUT'])
def upload():
    try:
        key = request.headers.get('X_NUGET_APIKEY')
        if not key or key != app.config['PYGET_API_KEY']:
            return 'Invalid or missing API key', 403
        file = request.files['package']
        if not file:
            return 'No package file', 400
        # open nupkg as zip archive and get xml from nuspec
        with zipfile.ZipFile(file, 'r') as package:
            nuspec = next((x for x in package.namelist() if x.endswith('.nuspec')), None)
            if not nuspec:
                return 'NuSpec file not found in package', 400
            with package.open(nuspec, 'r') as f:
                xml = xmltodict.parse(f)
        # get package id and version from nuspec
        metadata = xml['package']['metadata']
        name = metadata['id'] + '.' + metadata['version'] + '.nupkg'
        # check for existance of package
        pkg = Package.query.filter_by(name=metadata['id']).first()
        if not pkg:
            # create package
            pkg = Package(name=metadata['id'])
            db.session.add(pkg)
            #db.session.commit()
        else:
            # check for existance of version
            ver = pkg.versions.filter_by(version=metadata['version']).first()
            if ver:
                return 'This package version already exists', 409
        # push package to s3
        file.seek(0) # important
        filename = secure_filename(name)
        key = bucket.new_key(app.config['PYGET_S3_PATH'] + filename)
        key.set_contents_from_file(file)
        # add the package version to the db
        sem_ver_str, prerelease = coerce_version(metadata['version'])
        ver = Version(
            package=pkg,
            version=metadata['version'],
            normalized_version=sem_ver_str,
            package_size=os.fstat(file.fileno()).st_size,
            package_hash=base64.b64encode(hashlib.sha512(filename).digest()),
            is_prerelease=prerelease
            #tags='',
            )
        # get and save dependencies
        if 'dependencies' in metadata and \
            'dependency' in metadata['dependencies']:
            deps = metadata['dependencies']['dependency']
            if type(deps) is not list:
                deps = [deps]
            deps_string = '|'.join(['{0}:{1}'.format(dep['@id'], dep['@version']) if '@version' in dep else dep['@id'] for dep in deps])
            ver.dependencies = deps_string
        db.session.add(ver)
        db.session.commit()
        # TODO: add more metadata to db
    except:
        traceback.print_exc()
        return 'Error pushing package', 500
    return "Created", 201

@app.route('/api/v2/package/<name>/<version>', methods=['DELETE'])
def delete(name, version):
    try:
        key = request.headers.get('X_NUGET_APIKEY')
        if not key or key != app.config['PYGET_API_KEY']:
            return 'Invalid or missing API key', 403
        pkg = Package.query.filter_by(name=name).first()
        if pkg:
            ver = pkg.versions.filter_by(version=version).first()
            if ver:
                # remove nupkg from s3
                name = ver.package.name + '.' + ver.version + '.nupkg'
                key = app.config['PYGET_S3_PATH'] + secure_filename(name)
                bucket.delete_key(key)
                # remove package version from db
                db.session.delete(ver)
                #db.session.commit()
                if len(pkg.versions.all()) < 1:
                    db.session.delete(pkg)
                db.session.commit()
                return 'Deleted', 204
        return 'No package by this name and with this version', 400
    except:
        traceback.print_exc()
        return 'Error deleting package', 500

@app.route('/Search()')
@app.route('/FindPackagesById()')
def find():
    env = {
        'base_url': '/'.join(request.base_url.split('/')[:-1]),
        'id_url': request.base_url.strip('()'),
        'title': request.base_url.strip('()').split('/')[-1],
        'updated': datetime.utcnow().isoformat(),
        'entries': []
    }
    if 'id' in request.args:
        name = request.args['id'].strip('\'')
        pkgs = Package.query.filter_by(name=name).all() # TODO: use .one()
    elif 'searchTerm' in request.args:
        name = request.args['searchTerm'].strip('\'')
        if name:
            pkgs = Package.query.filter(
                Package.name.like('%' + name + '%')
                ).all()
        else:
            pkgs = Package.query.all()
    if pkgs and len(pkgs) > 0:
        env['entries'] = []
        for pkg in pkgs:
            vers = pkg.versions
            if request.args.get('includePrerelease', 'false') == 'false':
                vers = vers.filter(Version.is_prerelease is not True)
            env['entries'].extend([ver.to_json() for ver in vers.all()])
    renderer = pystache.Renderer()
    xml = renderer.render_path('feed.mustache', env)
    return Response(xml, mimetype='application/atom+xml')

@app.route('/ping')
def ping():
    return "pong"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('FLASK_PORT', 5000)))
