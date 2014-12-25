from flask.ext.sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

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
    dependencies = db.Column(db.String()) # TODO: dependencies as relationships
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
        if not self.dependencies:
            self.dependencies = ''

    def __repr__(self):
        return '<Version %r %r>' % (self.package.name, self.version)

    def to_json(self):
        return {
            'author': 'test',
            'version': self.version,
            'normalised_version': self.normalized_version,
            'copyright': '',
            'created': self.created.isoformat(),
            'dependencies': self.dependencies,
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
            'link_edit': 'Packages(Id=\'{0}\',Version=\'{1}\')'.format(self.package.name, self.version)
        }

class Author(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(), unique=True)

    def __repr__(self):
        return '<Author %r>' % (self.name)
