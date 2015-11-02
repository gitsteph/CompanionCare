from flask.ext.sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class User(db.Model):
    """User of site."""

    __tablename__ = "users"

    id = db.Column(db.Integer, autoincrement=True, nullable=False, primary_key=True)
    email = db.Column(db.String(40), nullable=False, unique=True)
    first_name = db.Column(db.String(20), nullable=False)
    last_name = db.Column(db.String(20), nullable=False)
    password = db.Column(db.String(20), nullable=False)
    # network_id = db.Column(db.Integer, nullable=False)
    zipcode = db.Column(db.String(15), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)

    companion = db.relationship('Companion')

    def __repr__(self):
        """Provide helpful representation when printed."""

        return "<User id=%s Name=%s %s>" % (self.id, self.first_name, self.last_name)


class Companion(db.Model):
    """Furry and non-furry companions."""

    __tablename__ = "companions"

    id = db.Column(db.Integer, autoincrement=True, nullable=False, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    primary_nickname = db.Column(db.String(20), nullable=True)
    species = db.Column(db.String(20), nullable=False)
    gender = db.Column(db.String(20))
    breed = db.Column(db.String(20))
    age = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    # network_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User')


##############################################################################
# Helper functions
def connect_to_db(app):
    """Connect the database to our Flask app."""

    # Configure to use PostgreSQL database.
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://localhost/companions'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.app = app
    db.init_app(app)

if __name__ == "__main__":
    # If module is run interactively, user will be able to work with db directly.

    from server import app
    connect_to_db(app)
    print "Connected to DB."
