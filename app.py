from flask import Flask, Response, request, make_response, send_file
from flask.ext.sqlalchemy import SQLAlchemy
import zipfile, xmltodict, traceback
from werkzeug import secure_filename
import os
from datetime import datetime
import semantic_version as sem_ver
import pystache
import hashlib, base64
import io

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
db = SQLAlchemy(app)

app.config['DEBUG'] = os.environ.get('DEBUG', False)
app.config['NUGET_API_KEY'] = os.environ.get('NUGET_API_KEY')
if not app.config['NUGET_API_KEY']:
    raise Exception('NUGET_API_KEY setting is required')
app.config['S3_BUCKET'] = os.environ.get('S3_BUCKET')
if app.config['S3_BUCKET']:
    import boto
    print 'Connecting to S3...'
    s3 = boto.connect_s3(os.environ.get('S3_KEY'), os.environ.get('S3_SECRET'))
    try:
        bucket = s3.get_bucket(app.config['S3_BUCKET'])
        print 'Connected to S3!'
    except boto.exception.S3ResponseError as e:
        print 'Bucket not found so I\'m creating one for you'
        bucket = s3.create_bucket(app.config['S3_BUCKET'])
else:
    raise Exception('S3_BUCKET setting is required')

# see http://docs.nuget.org/docs/reference/nuspec-reference

class Package(db.Model):
    __tablename__ = 'packages'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(), unique=True)
    updated = db.Column(db.DateTime())
    authors = db.Column(db.String()) # TODO: multiple authors
    #latest_version = db.relationship('Version')

    # one-to-many relationship with versions
    versions = db.relationship('Version', backref='package', lazy='dynamic')

    def get_sorted_versions(self):
        return sorted(
            self.versions.all(),
            key=lambda x: sem_ver.Version(x.normalized_version),
            reverse=True)

    #def update_latest_version(self):
    #    vers = self.get_sorted_versions()
    #    if len(vers):
    #        self.latest_version = vers[0]

    def __repr__(self):
        return '<Package %r>' % (self.name)

class Version(db.Model):
    __tablename__ = 'versions'
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(), nullable=False) # unique (see below)
    # normalized_version, see https://github.com/NuGet/NuGetGallery/pull/1573
    normalized_version = db.Column(db.String())
    copyright = db.Column(db.String())
    created = db.Column(db.DateTime())
    # TODO: dependencies
    # store version spec separately, to be queried at install-time
    #dependencies = db.relationship('Package')
    description = db.Column(db.String())
    # download_count
    # gallery_details_url
    icon_url = db.Column(db.String())
    # is_latest_version
    # is_absolute_latest_version
    is_prerelease = db.Column(db.Boolean())
    # langauge
    # published
    package_hash = db.Column(db.String())
    package_hash_algorithm = db.Column(db.String())
    package_size = db.Column(db.Integer())
    project_url = db.Column(db.String())
    # report_abuse_url
    release_notes = db.Column(db.String())
    require_license_acceptance = db.Column(db.Boolean())
    summary = db.Column(db.String())
    tags = db.Column(db.String()) # TODO: split tags
    title = db.Column(db.String())
    # version_download_count
    # min_client_version
    # last_edited
    license_url = db.Column(db.String())
    license_names = db.Column(db.String())
    # license_report_url

    # foreign key for parent package
    _package_id = db.Column(db.Integer, db.ForeignKey('packages.id'), nullable=False)

    # composite unique constraint: version AND package
    __table_args__ = (
        db.UniqueConstraint('version', '_package_id', name='_package_version_uc'),
    )

    def __init__(self, *args, **kwargs):
        super(Version, self).__init__(*args, **kwargs)
        self.created = datetime.utcnow()

    def __repr__(self):
        return '<Version %r %r>' % (self.package.name, self.version)

    def to_json(self):
        return {
            'author': 'test',
            'version': self.version,
            'normalised_version': self.normalized_version,
            'copyright': '',
            'created': self.created.isoformat(),
            'dependencies': '',
            'description': '',
            'download_count': 0,
            #'gallery_details_url': None,
            #'icon_url': None,
            'is_latest_version': 'true',
            'is_absolute_latest_version': 'true',
            'is_prerelease': 'false',
            'langauge' : None,
            'published': self.created.isoformat(),
            'package_hash': self.package_hash,
            'package_hash_algorithm': 'SHA512',
            'package_size': self.package_size,
            'project_url': '', #self.project_url,
            'report_abuse_url': '',
            'release_notes': '', #self.release_notes,
            'require_license_acceptance': 'false',
            'summary': '',
            'tags': '',
            'title': self.package.name,
            'version_download_count': 0,
            # min_client_version
            # last_edited
            'license_url': '',
            'license_names': '',
            'license_report_url': '',
            'content': "https://s3-eu-west-1.amazonaws.com/{0}/".format(app.config['S3_BUCKET']) + self.package.name + '.' + self.version + '.nupkg',
            'link_edit': 'Packages(Id=\'{0}\',Version=\'{1}\')'.format(self.package.name, self.version)
        }

class Author(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(), unique=True)

    def __repr__(self):
        return '<Author %r>' % (self.name)

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
        return str(sem_ver.Version.coerce(tmp))
    except:
        return None

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
            filename = ver.package.name + '.' + ver.version + '.nupkg'
            key = bucket.get_key(filename)
            if key:
                in_buffer = io.BytesIO()
                key.get_contents_to_file(in_buffer)
                in_buffer.seek(0)
                return send_file(in_buffer, mimetype='application/zip')
    return 'No package by this name and with this version', 404

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
        key = bucket.new_key(filename)
        key.set_contents_from_file(file)
        # add the package version to the db
        ver = Version(
            package=pkg,
            version=metadata['version'],
            normalized_version=coerce_version(metadata['version']),
            package_size=os.fstat(file.fileno()).st_size,
            package_hash=base64.b64encode(hashlib.sha512(filename).digest()),
            #tags='',
            )
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
        if not key or key != app.config['NUGET_API_KEY']:
            return 'Invalid or missing API key', 403
        pkg = Package.query.filter_by(name=name).first()
        if pkg:
            ver = pkg.versions.filter_by(version=version).first()
            if ver:
                # remove nupkg from s3
                key = ver.package.name + '.' + ver.version + '.nupkg'
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
        pkgs = Package.query.filter_by(name=name).all()
    elif 'searchTerm' in request.args:
        name = request.args['searchTerm'].strip('\'')
        if name:
            pkgs = Package.query.filter_by(name=name).all() # TODO: partials
        else:
            pkgs = Package.query.all()
    #print pkgs
    if pkgs and len(pkgs) > 0:
        env['entries'] = []
        for pkg in pkgs:
            env['entries'].extend([ver.to_json() for ver in pkg.versions.all()])
    renderer = pystache.Renderer()
    xml = renderer.render_path('feed.mustache', env)
    return Response(xml, mimetype='application/atom+xml')

@app.route('/ping')
def ping():
    return "pong"

if __name__ == "__main__":
    app.run(port=int(os.environ.get('FLASK_PORT', 5000)))
