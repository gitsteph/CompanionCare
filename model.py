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
    phone = db.Column(db.String, nullable=True)
    zipcode = db.Column(db.String(15), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        """Provide helpful representation when printed."""

        return "<User id=%s Name=%s %s>" % (self.id, self.first_name, self.last_name)

    companions = db.relationship('Companion', cascade="all,delete", backref="user")


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

    petvets = db.relationship('PetVet', cascade="all,delete", backref="companion")

    def __repr__(self):
        """Provide helpful representation when printed."""

        return "<Companion ID=%s Name=%s Species=%s>" % (self.id, self.name, self.species)


class PetVet(db.Model):
    """Facilitating the many-to-many relationship between companions and veterinarians."""

    __tablename__ = "petvets"

    id = db.Column(db.Integer, autoincrement=True, nullable=False, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey('companions.id'), nullable=False)
    vet_id = db.Column(db.Integer, db.ForeignKey('veterinarians.id'), nullable=False)
    first_visit = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        """Provide helpful representation when printed."""

        return "<PetVet ID=%s Pet ID=%s Vet ID=%s>" % (self.id, self.pet_id, self.vet_id)

    petmeds = db.relationship('PetMedication', backref="petvet")



class Veterinarian(db.Model):
    """Veterinary specialists."""

    __tablename__ = "veterinarians"

    id = db.Column(db.Integer, autoincrement=True, nullable=False, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    office_name = db.Column(db.String(20), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(20), nullable=True)
    specialties = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        """Provide helpful representation when printed."""

        return "<Vet ID=%s Name=%s Office=%s>" % (self.id, self.name, self.office_name)

    petvets = db.relationship('PetVet', cascade="all,delete", backref="veterinarian")



class Medication(db.Model):
    """Pet medications."""

    __tablename__ = "medications"

    id = db.Column(db.Integer, autoincrement=True, nullable=False, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String, nullable=True)
    link = db.Column(db.String(20), nullable=True)  # link type?
    species = db.Column(db.String(20), nullable=True)  # may want to separate out to be searchable later.
    # photo = db.Column(db.String(20), nullable=True)  # photo type?
    uses = db.Column(db.String, nullable=True)  # may want to separate out to be searchable later.
    side_effects = db.Column(db.String, nullable=True)
    contraindications = db.Column(db.String, nullable=True)
    instructions = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)

    petmeds = db.relationship('PetMedication', cascade="all,delete", backref="medication")
    # petmedications backref will return a list, like an attribute

    def __repr__(self):
        """Provide helpful representation when printed."""

        return "<ID=%s Name=%s Description=%s>" % (self.id, self.name, self.description)


class PetMedication(db.Model):
    """Facilitating the many-to-many relationship between pets and medications."""

    __tablename__ = "petmedications"

    id = db.Column(db.Integer, autoincrement=True, nullable=False, primary_key=True)
    medication_id = db.Column(db.Integer, db.ForeignKey('medications.id'), nullable=False)
    current = db.Column(db.String(10), nullable=False)
    notes = db.Column(db.String, nullable=True)
    petvet_id = db.Column(db.Integer, db.ForeignKey('petvets.id'))
    frequency = db.Column(db.Integer)  # every X hours
    frequency_unit = db.Column(db.String)  # delete this later
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)
    # medication attribute exists via relationship

    alerts = db.relationship('Alert', cascade="all,delete", backref="petmedication")

    def __repr__(self):
        """Provide helpful representation when printed."""

        return "<ID=%s Medication ID=%s Current? %s>" % (self.id, self.medication_id, self.current)


class Alert(db.Model):
    """Alerts!"""

    __tablename__ = "alerts"

    id = db.Column(db.Integer, autoincrement=True, nullable=False, primary_key=True)
    petmed_id = db.Column(db.Integer, db.ForeignKey('petmedications.id'), nullable=True)
    petfood_id = db.Column(db.Integer, nullable=True)
    primary_alert_phone = db.Column(db.String)
    secondary_alert_phone = db.Column(db.String)
    alert_frequency = db.Column(db.String)  # may want to remove this
    alert_frequency_unit = db.Column(db.String)  # may want to remove this
    current = db.Column(db.String(20))
    alert_options = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)

    alertlogs = db.relationship('AlertLog', cascade="all,delete", backref="alert")

    def __repr__(self):
        """Provide helpful representation when printed."""

        return "<ID=%s PetMed ID=%s Alert DateTime=%s>" % (self.id, self.petmed_id, self.next_alert_datetime)


class AlertLog(db.Model):
    """Alert log."""

    __tablename__ = "alertlogs"

    id = db.Column(db.Integer, autoincrement=True, nullable=False, primary_key=True)
    scheduled_alert_datetime = db.Column(db.DateTime, nullable=False)
    alert_id = db.Column(db.Integer, db.ForeignKey('alerts.id'), nullable=False)
    alert_issued = db.Column(db.DateTime)
    recipient = db.Column(db.String, nullable=False)
    action_taken = db.Column(db.String(20))
    response_timestamp = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True)


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
