from flask import Flask, request, render_template, redirect, flash, jsonify, url_for, send_from_directory
from flask import session
from flask_debugtoolbar import DebugToolbarExtension
# from jinja2 import StrictUndefined
from model import connect_to_db, db, User, Companion, Image, PetVet, Veterinarian, PetMedication, Medication, Alert, AlertLog
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug import secure_filename
from sqlalchemy import update, delete, exc
from alerts import *
from queries import *
from collections import OrderedDict, defaultdict
import multiprocessing
from vet_finder import search
import send_messages
import datetime
import time
from uuid import uuid4
import boto
from boto.s3.key import Key
import boto.s3.connection
import os


app = Flask(__name__)

app.secret_key = "###"

app.config['AWS_ACCESS_KEY'] = os.environ["AWSAccessKeyId"]
app.config['AWS_SECRET_KEY'] = os.environ["AWSSecretKey"]
app.config['AWS_BUCKET_NAME'] = os.environ["AWSBuckedName1"]

UPLOAD_FOLDER = 'static/img/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])

# app.jinja_env.undefined = StrictUndefined


######## HELPER FUNCTION DDICT/OBJTREE ########
class objdict(defaultdict):
    def __getattr__(self, key):
        try:
            return self.__dict__[key]
        except KeyError:
            return self.__getitem__(key)

    __setattr__ = lambda self, k, v: self.__setitem__(k,v)

objtree = lambda: objdict(objtree)


def dd2dr(dd):
    """defaultdict to dict recursively"""
    return dict(
        (k, dd2dr(v) if isinstance(v, defaultdict) else v)
        for k, v in dd.items()
    )


################

######## HELPER FUNCTION TO SEED ONLY ONCE ########
def add_unknown_vet():
    if not Veterinarian.query.filter(Veterinarian.name == "Unknown").first():
        vet_dict={}
        vet_dict["name"] = "Unknown"
        vet_dict["created_at"] = datetime.datetime.now()
        new_vet = Veterinarian(**vet_dict)
        db.session.add(new_vet)
        db.session.commit()


################

######## ALERTS MULTIPROCESSING SEND & RESPOND ########
@app.route('/sms', methods=["POST"])
def retrieve_user_response_and_reply():
    user_from = request.values.get('From', None)
    user_response = request.values.get('Body', None)
    user_response = user_response.lower()
    user_from = user_from.strip('+1')
    user_name = db.session.query(User).filter(User.phone == user_from).first().first_name

    # Given the alert_id and action_taken from user_response, queries the database for the alertlog entry
    # and saves the desired action.  This will then trigger setting the next alert.
    user_response = user_response.split()
    alert_id = user_response[0]
    action_taken = user_response[1]

    # Processes user_response and returns the datetime of next scheduled alert.
    new_scheduled_alert, new_alertlog_obj, user_response = process_user_response(alert_id, action_taken)
    new_scheduled_alert_str = new_scheduled_alert.strftime('%I:%M %p on %x')
    companion_name = new_alertlog_obj.alert.petmedication.petvet.companion.name
    medication_name = new_alertlog_obj.alert.petmedication.medication.name
    missed_dose = new_alertlog_obj.alert.petmedication.medication.missed_dose
    return send_messages.reply_to_user(companion_name, new_scheduled_alert_str, user_response, medication_name, missed_dose, user_name)


def time_alerts():
    while True:
        current_datetime = datetime.datetime.now()
        # query for alerts with past datetimes that have not yet been issued.
        alertlogs = AlertLog.query.filter(AlertLog.scheduled_alert_datetime < current_datetime,
                                          AlertLog.alert_issued.is_(None)).all()
        print alertlogs, "<<< ALERTS PENDING"
        if alertlogs:
            for alertlog in alertlogs:
                issue_alert_and_update_alertlog(alertlog.id)

        # run every minute
        time.sleep(10)


################

######## LOGIN/LOGOUT ########
# Helper function to check whether user is logged in.
def confirm_loggedin():
    user_id = session.get("user_id")
    if not user_id:
        print "redirected"
        return None
    else:
        user_obj = User.query.filter(User.id == user_id).first()
    return user_obj


@app.route('/login', methods=['POST'])
def process_login():
    """Processes log in information for existing users."""
    email = request.form.get("email")
    password = request.form.get("password")

    # Queries "users" table in database to determine whether the user already has an account.
    # If the user has an account, the user's account information and password are verified.
    user_object = User.query.filter(User.email == email).first()
    if user_object:
        if check_password_hash(user_object.password, password):
            session['user_id'] = user_object.id

            flash("Logged in")
            return redirect("/")  # dashboard
        else:
            flash('wrong password')
            return redirect("/")  # login page
    else:
        flash('no such user')
        return redirect("/")


@app.route('/logout/<int:deleted>')
def logout(deleted):
    """Log out."""

    del session["user_id"]
    if deleted != 2:
        flash("Logged Out.")
    return redirect("/")

################

######## HOME, DASHBOARD, USER REGISTRATION, UPDATE, DELETE USER ########
@app.route('/', methods=['GET'])
def show_homedash():
    """If not logged in, will show homepage.  Else, will show dashboard."""
    user_obj = confirm_loggedin()
    if user_obj:
        companion_obj_list = Companion.query.filter(Companion.user_id == session['user_id']).all()

        # Retrieve all active alerts for all user's companions.
        active_alerts_list = get_alerts_sorted_by_time()

        companion_dash_list = []
        # Retrieve all medications for each of user's companions.
        for companion_obj in companion_obj_list:
            companion_petvet_list = db.session.query(PetVet).filter(PetVet.pet_id == companion_obj.id).all()

            # Retrieve all vets for each of user's companions.
            companion_vetname_list = []
            for petvet in companion_petvet_list:
                vet_name = petvet.veterinarian.name
                companion_vetname_list.append(vet_name)

            # Retrieve all meds for each of user's companions.
            petmed_list = get_petmed_list_by_companion(companion_obj.id)
            companion_medname_list = []
            for petmed_obj in petmed_list:
                med_name = petmed_obj.medication.name
                companion_medname_list.append(med_name)

            # Retrieve all photos for each of user's companions.
            companion_name = companion_obj.name
            image_obj = Image.query.filter(Image.tags.match("%"+companion_name+"%")).order_by(Image.created_at.desc()).first()
            companion_dash_list.append((companion_obj, companion_vetname_list, companion_medname_list, image_obj))

        return render_template("index.html", user_obj=user_obj, companion_dash_list=companion_dash_list, active_alerts_list=active_alerts_list)

    else:
        user_attributes_dict = OrderedDict([("logged_in", False),
                                                ("Email", ("email", "email")),
                                                ("Password", ("password", "password")),
                                                ("First Name", ("first_name", "text")),
                                                ("Last Name", ("last_name", "text")),
                                                ("Phone Number", ("phone", "text"))])
        return render_template("home.html", user_attributes_dict=user_attributes_dict)


@app.route('/register', methods=['POST'])
def register_user():
    if request.method == 'POST':
        """Processes new user registration."""

        # Requests information provided by the user from registration form.
        value_types = ["email", "first_name", "last_name", "phone"]
        values_dict = {val:request.form.get(val) for val in value_types}
        values_dict["created_at"] = datetime.datetime.now()
        unhashed_pw = request.form.get("password")
        print unhashed_pw, "<<< unhashed"
        password = generate_password_hash(unhashed_pw)  # hashes and salts pw
        print password, "<<< hashed"
        values_dict["password"] = password

        # Queries "users" table in database to determine whether user already has an account.
        # If the user has an account, the user is redirected to login page.
        # Otherwise, a new account is created and the user is logged in via the session.
        user_object = User.query.filter(User.email == values_dict["email"]).first()
        if user_object:
            flash('account exists')
            return redirect("/")
        else:
            new_user = User(**values_dict)
            db.session.add(new_user)
            db.session.commit()
            user_object = User.query.filter(User.email == values_dict["email"]).first()
            session['user_id'] = user_object.id

        return redirect("/")


@app.route('/user_profile/delete', methods=['POST'])
def delete_user_profile():
    """Deletes user profile and returns to home page, logged out."""
    db.session.delete(User.query.filter(User.id == session["user_id"]).first())
    db.session.commit()
    flash('Your account has been deleted.')
    return redirect("/logout/2")


@app.route('/user_profile/update', methods=['POST'])
def update_user_profile():
    """AJAX route to update user profile from modal."""
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        value_types = ["email", "password", "first_name", "last_name", "zipcode", "phone"]
        values_dict = {val:request.form.get(val) for val in value_types}
        print values_dict
        values_dict["updated_at"] = datetime.datetime.now()
        values_dict = {k:v for k,v in values_dict.iteritems() if v}

        ind_update = update(User.__table__).where(User.id == session['user_id']).values(**values_dict)
        db.session.execute(ind_update)
        db.session.commit()
    return "Your user profile has been updated."


################

######## ADD COMPANION ########
def process_add_new_companion(value_types):
    # Requests information about each companion.
    add_unknown_vet()
    companion_values_dict = {val:request.form.get(val) for val in value_types}
    companion_values_dict["user_id"] = session["user_id"]
    companion_values_dict["created_at"] = datetime.datetime.now()
    companion_values_dict["updated_at"] = None
    new_companion = Companion(**companion_values_dict)

    db.session.add(new_companion)
    db.session.commit()

    # Upon creation of new companion in db, also create new petvet relationship between Companion & Unknown Vet.
    companion_name = request.form.get("name")

    petvet_values_dict = {}

    # Queries for id of newly-created companion in db.
    petvet_values_dict["pet_id"] = Companion.query.filter(Companion.name == companion_name).first().id
    petvet_values_dict["vet_id"] = Veterinarian.query.filter(Veterinarian.name == "Unknown").first().id  # Unknown Vet
    print petvet_values_dict

    new_petvet = PetVet(**petvet_values_dict)
    db.session.add(new_petvet)
    db.session.commit()

################

######## PHOTOS ########
@app.route('/photos', methods=['GET'])
def show_photos():
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        image_list = Image.query.filter(Image.user_id == session.get("user_id")).all()
        return render_template("photos.html", user_obj=user_obj, image_list=image_list)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_file_online():
    """Uploads to AWS S3 by taking in form data (file, name, tag) if user is logged in."""
    data_file = request.files.get("photo")
    if data_file and allowed_file(data_file.filename):
        file_name = data_file.filename
        conn = boto.s3.connect_to_region('us-west-1',
                                         aws_access_key_id=app.config["AWS_ACCESS_KEY"],
                                         aws_secret_access_key=app.config["AWS_SECRET_KEY"],
                                         is_secure=True,
                                         calling_format=boto.s3.connection.OrdinaryCallingFormat(),
                                         )
        bucket = conn.get_bucket(app.config["AWS_BUCKET_NAME"])
        k = Key(bucket)
        k.set_contents_from_string(data_file.read())
        k.set_acl('public-read')
        location_url = k.generate_url(expires_in=0, query_auth=False)  # public
        image_dict = {}
        image_dict["location_url"] = location_url
        image_dict["user_id"] = session.get("user_id")
        image_dict["name"] = request.form.get("name")
        image_dict["tags"] = request.form.get("tags")

        # Check to see if image already has a pointer stored in db.
        image_query = Image.query.filter(Image.location_url == location_url).first()
        if image_query:
            # If pointer already stored, update instead of adding.
            image_query_id = image_query.id
            image_dict["updated_at"] = datetime.datetime.now()
            image_dict = {k:v for k,v in image_dict.iteritems() if v}

            img_update = update(Image.__table__).where(Image.id == image_query_id).values(**image_dict)
            db.session.execute(img_update)
            flash("Your photo has been updated.")
        else:
            # If no pointer stored, add new image entry to db.
            image_dict["created_at"] = datetime.datetime.now()
            new_image = Image(**image_dict)
            db.session.add(new_image)
            flash("Your photo has been uploaded.")

        db.session.commit()

        image_obj = Image.query.filter(Image.location_url == location_url).first()
        return image_obj.id
    else:
        flash("Upload unsuccessful")
    return None


@app.route('/photos/upload', methods=["POST"])
def photo_upload_to_S3():
    # Uploads files (photos) to AWS S3.
    user_obj = confirm_loggedin
    if not user_obj:
        return redirect('/')
    else:
        if request.method == 'POST':
            image_id = upload_file_online()
            if image_id:
                return redirect('/photos/' + str(image_id))
            else:
                return redirect('/photos')


@app.route('/photos/<int:image_id>', methods=["GET"])
def retrieve_photo(image_id):  # ### TODO: ENABLE EDIT IMAGE TAGS FROM THIS ROUTE.
    user_obj = confirm_loggedin
    if not user_obj:
        return redirect('/')
    else:
        photo_obj = get_photo_obj(image_id)
        if not photo_obj:
            flash("You do not have an image stored with that ID.")
            return redirect('/photos')
        else:
            return render_template('photos.html', user_obj=user_obj, photo_obj=photo_obj)


def upload_file_locally():
    file = request.files['photo']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return redirect(url_for('uploaded_file', filename=filename))
    else:
        return redirect('/photos/upload')


################

######## VISUALIZATION ########
@app.route('/visualization', methods=["GET", "POST"])
def show_data_tree():
    """Renders D3 node tree displaying users, companions, vets, medications, and alerts."""
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        ####### THIS NEEDS WORK!!!!! GO BACK

        # Query for list of all user's companions.
        user_companions_list = get_all_user_companions()
        print user_companions_list

        # Iterate through list of user's companions to generate a list of petmed IDs and related info to show user for alerts.
        alert_dict = objtree()

        for companion_obj in user_companions_list:
            companion_name = companion_obj.name
            companion_petvets_list = companion_obj.petvets  # returns list of petvets per pet
            alert_dict[companion_obj] = objdict(objtree)
            for petvet in companion_petvets_list:
                vet_obj = petvet.veterinarian
                petmeds_list = petvet.petmeds  # returns list of petmeds per petvet
                alert_dict[companion_obj][vet_obj] = objdict(objtree)
                for petmed in petmeds_list:
                    medication = petmed.medication
                    alerts = petmed.alerts
                    alert_dict[companion_obj][vet_obj][medication] = objdict(objtree)
                    for alert in alerts:
                        alert_id = alert.id
                        alert_dict[companion_obj][vet_obj][medication] = alert
        ddict = dd2dr(alert_dict)
        print ddict, "<<<<DDICT"

        def convertToD3Form(d):
            if not isinstance(d, dict):  # if d has no children, stop recursing
                return [{'name':str(d.id)}]

            l = []
            for k,v in d.iteritems():  # iterate through all children of d
                l.append({'name':str(k.name), 'children':convertToD3Form(v)})  # add child and recursively add its children
            return l

        user_obj.name = user_obj.first_name + ' ' + user_obj.last_name
        ddict_tree = convertToD3Form({user_obj:ddict})
        print 'D3 Form:', ddict_tree

        return render_template('visualization.html', user_obj=user_obj, ddict_tree=str(ddict_tree))


################

######## ALERTS ########
@app.route('/alerts', methods=["GET", "POST"])
def show_all_alerts_and_form():
    """Renders alerts page with existing alerts and other routes to add and edit alerts."""
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        # Calls function, get_all_alerts(), from queries.py and unpacks returned values.
        alert_dict, inactive_alert_dict = get_all_alerts()
        print inactive_alert_dict, "<<<<"
        return render_template('alerts.html', user_obj=user_obj, alert_dict=alert_dict, inactive_alert_dict=inactive_alert_dict)


@app.route('/add_new_alert', methods=["POST"])
def add_new_alert():
    alert_variables = ["primary_alert_phone", "secondary_alert_phone", "alert_datetime_start", "alert_datetime_end", "alert_type"]
    alert_frequency = request.form.get("alert_frequency")
    alert_frequency_unit = request.form.get("alert_frequency_unit")
    if alert_frequency_unit == "days":  # to convert to hours
        alert_frequency = alert_frequency * 24
    alert_values_dict = {var:request.form.get(var) for var in alert_variables}
    alert_values_dict["alert_frequency"] = alert_frequency
    alert_values_dict["created_at"] = datetime.datetime.now()

    companion_name = request.form.get("companion_name")  # Companion must exist already or user will need to add via different route.
    medication_name = request.form.get("medication_name")  # Medication must exist already or user will need to add via different route.

    # Assign petvet id matching companion and unknown vet.  User can update with more info at a later point in time if needed.
    companion_obj = get_companion_obj(companion_name)
    companion_id = companion_obj.id
    print "pet_id", companion_id

    # Gets medication obj from db.
    medication_obj = Medication.query.filter(Medication.name == medication_name).first()
    medication_id = medication_obj.id
    print medication_id, "medID"

    companion_petvets_list = companion_obj.petvets  # returns list of petvets
    companion_petvet_ids_set = set()
    for companion_petvet in companion_petvets_list:
        companion_petvet_ids_set.add(companion_petvet.id)

    print companion_petvet_ids_set

    # Iterate through list of petvets to see if there is a match for a medication issued connected to petvet.
    # If no medication issued, prompt user to add medication for pet via different route.
    # Else, assign petvet id for alert dict.

    petmed_obj = PetMedication.query.filter(PetMedication.medication_id == medication_id, PetMedication.petvet_id.in_(companion_petvet_ids_set)).first()
    petmed_id = petmed_obj.id

    print petmed_obj, "<<< ", petmed_id
    alert_values_dict["petmed_id"] = petmed_id
    print alert_values_dict

    new_alert = Alert(**alert_values_dict)
    db.session.add(new_alert)
    db.session.commit()

    # Schedule first alert (via alertlog entry), set to not-issued yet.
    alert_id = db.session.query(Alert).filter(Alert.petmed_id == alert_values_dict["petmed_id"]).order_by(Alert.updated_at.desc()).first().id
    first_alert_datetime = alert_values_dict["alert_datetime_start"]
    schedule_alert(alert_id, first_alert_datetime)

    ### TODO: When an exception is thrown, e.g. if companion or medication does not exist, or if companion is not assigned specific medication already,
    ### prompt the user to add either companion, medication, or petmed via different route.

    rtrn_msg = "An alert has been set for " + str(companion_obj.name) + "."
    return rtrn_msg


################

######## MEDICATIONS ########
@app.route('/medications', methods=['GET', 'POST'])
def show_all_medications():
    user_obj = confirm_loggedin()
    if not user_obj:
        redirect('/')
    else:
        medications = Medication.query.order_by(Medication.name).all()
        # TODO: MAY WANT TO SORT BASED ON name.lower() b/c ascii alpha is weird.

        # Splitting the med_name_list into three mini-lists to enable easy display in columns on the front-end.
        third_med_list = len(medications)/3
        first_third_med_list = medications[:third_med_list]
        second_third_med_list = medications[third_med_list:2*third_med_list]
        last_third_med_list = medications[2*third_med_list:]
        list_med_list = [first_third_med_list, second_third_med_list, last_third_med_list]

        return render_template("medications.html", list_med_list=list_med_list, user_obj=user_obj)


@app.route('/add_companion_medication/<companion_name>', methods=['POST'])
def add_medications_for_companion(companion_name):
    """AJAX path from medications to add a specific medication for an individual companion."""
    user_obj = confirm_loggedin()
    companion_obj = get_companion_obj(companion_name)
    if not user_obj:
        return redirect("/")
    else:
        if not companion_obj:
            process_add_new_companion(["name", "species"])
            companion_obj = get_companion_obj(companion_name)

    companion_id = companion_obj.id
    vet_name = request.form.get("prescribing_vet")
    if not vet_name:
        vet_name = "Unknown"
    vet_obj = Veterinarian.query.filter(Veterinarian.name == vet_name).first()

    # If Veteranarian name is not yet in the database, add it.
    if vet_obj:
        print "Vet already in db."
        print vet_obj
    else:
        vet_dict = {}
        vet_dict = {"name":vet_name}
        vet_dict["created_at"] = datetime.datetime.now()
        vet_dict["updated_at"] = None
        vet_entry = Veterinarian(**vet_dict)
        db.session.add(vet_entry)
        db.session.commit()

    # If PetVet relationship is not yet in the database, add it.
    vet_id = Veterinarian.query.filter(Veterinarian.name == vet_name).first().id
    print "vet_id = ", vet_id
    petvet_obj = PetVet.query.filter(PetVet.vet_id == vet_id, PetVet.pet_id == companion_id).first()
    if petvet_obj:
        print "PetVet already in db."
        print petvet_obj.id
    else:
        petvet_dict = {}
        petvet_dict = {"pet_id": int(companion_id),
                       "vet_id": int(vet_id)}
        petvet_entry = PetVet(**petvet_dict)
        db.session.add(petvet_entry)
        db.session.commit()

    # List of other medication-related values to pull from form.
    petmed_values = ["current", "dosage", "notes"]
    med_name = request.form.get("medname")
    print med_name

    # Retrieves values input by user from form and create a dictionary
    # that is then passed through via **kwargs to create an instance of
    # class_name db.Model class.  Add instance to db and commit transaction.
    values_dict = {val:request.form.get(val) for val in petmed_values}
    med_id = Medication.query.filter(Medication.name == med_name).first().id
    # Will only create new petmed entry if none exists.
    petvet_id = PetVet.query.filter(PetVet.vet_id == vet_id, PetVet.pet_id == companion_id).first().id
    if not PetMedication.query.filter(PetMedication.petvet_id == petvet_id, PetMedication.medication_id == med_id).first():
        # Converts frequency into hours from whatever user unit was input.
        frequency = int(request.form.get("frequency"))
        frequency_unit = request.form.get("frequency_units")
        if frequency_unit == "days":
            print frequency_unit
            frequency = frequency * 24
            print frequency
        values_dict["medication_id"] = int(med_id)
        values_dict["petvet_id"] = int(petvet_id)
        values_dict["frequency"] = frequency
        values_dict["created_at"] = datetime.datetime.now()
        values_dict["updated_at"] = None
        new_entry = PetMedication(**values_dict)
        db.session.add(new_entry)
        db.session.commit()

        return "This medication has been added for your companion."


def view_individual_medication(med_name):
    medication_obj = Medication.query.filter(Medication.name == med_name).first()
    print medication_obj
    return medication_obj


@app.route('/medications/api/name/<med_name>', methods=['GET'])
def view_single_med(med_name):
    medication_obj = view_individual_medication(med_name)
    med_cols = [("Name", medication_obj.name), ("General Description", medication_obj.general_description), ("How It Works", medication_obj.how_it_works),
                ("Missed Dose?", medication_obj.missed_dose), ("Storage Information", medication_obj.storage_information), ("Side Effects & Contraindications", medication_obj.side_effects_and_drug_interactions)]
    medication_dict = {}
    for col in med_cols:
        medication_dict[col[0]] = str(col[1]).replace('\n', " ")
    medication_dict["uri"] = "/medications/api/name/" + med_name

    return jsonify(medication_dict)


@app.route('/medications/<med_name>', methods=['GET', 'POST'])
def edit_medication(med_name):
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect('/')
    else:
        medication_obj = view_individual_medication(med_name)
        return render_template('medication_detail.html', medication_obj=medication_obj, user_obj=user_obj)


@app.route('/medications/<med_name>/update', methods=['POST'])
def update_medication_indb(med_name):
    """Route specifically for AJAX call to update medication."""
    medication_attributes_list = ['name', 'general_description', 'how_it_works', 'missed_dose', 'storage_information', 'side_effects_and_drug_interactions']
    updated_med_dict = {val:request.form.get(val) for val in medication_attributes_list}
    updated_med_dict["updated_at"] = datetime.datetime.now()
    updated_med_dict = {k:v for k,v in updated_med_dict.iteritems() if v}

    update_dict = update(Medication.__table__).where(Medication.name == med_name).values(**updated_med_dict)
    db.session.execute(update_dict)
    db.session.commit()

    return "Your update has been submitted."


@app.route('/medications/directory_add', methods=['POST'])
def add_medication_todb():
    """Route specifically for AJAX call to add new medication."""

    medication_attributes_list = ['name', 'general_description', 'how_it_works', 'missed_dose', 'storage_information', 'side_effects_and_drug_interactions']
    new_med_dict = {val:request.form.get(val) for val in medication_attributes_list}
    new_med_dict["created_at"] = datetime.datetime.now()

    new_med = Medication(**new_med_dict)
    db.session.add(new_med)
    db.session.commit()

    return "The medication has been added to our directory."


@app.route('/medications/directory_delete/<med_name>', methods=['POST'])
def delete_medication_fromdb(med_name):
    try:
        db.session.delete(Medication.query.filter(Medication.name == med_name).first())
    except:  # TODO: fix this in a better way.  Error because of model db cascade alls.
        return "Cannot delete medication as it is already assigned to companions."

    db.session.commit()
    return "The medication entry has been deleted."

################

######## VETERINARIANS ########
@app.route('/veterinarians', methods=['GET', 'POST'])
def show_veterinarians():
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:  # TODO: render all vets editable.

        # generate list of vets for user's companions.
        user_companions = get_all_user_companions()
        user_petvets_list = []

        for companion_obj in user_companions:
            petvets = PetVet.query.filter(PetVet.pet_id == companion_obj.id).all()
            user_petvets_list += petvets

        user_vets_set = set()
        vet_id_set = set()

        for petvet in user_petvets_list:
            vet_obj = petvet.veterinarian
            vet_id_set.add(vet_obj.id)
            user_vets_set.add(vet_obj)

        vet_companion_dict = {}
        for vet_obj in user_vets_set:
            vet_companion_dict[vet_obj] = []
            petvets_list_by_vet = vet_obj.petvets
            for petvet in petvets_list_by_vet:
                companion_obj = petvet.companion
                if session["user_id"] == companion_obj.user_id:
                    vet_companion_dict[vet_obj].append(companion_obj)

        # generate list of all avail. vets, excluding vets already in user network.
        all_vets = Veterinarian.query.filter(~Veterinarian.id.in_(vet_id_set)).all()

        return render_template("veterinary_specialists.html", user_obj=user_obj, vet_companion_dict=vet_companion_dict, all_vets=all_vets, user_companions=user_companions)


@app.route('/edit_veterinarian_profile', methods=["POST"])
def edit_vet_ajax():
    """AJAX route to edit existing veterinarian profile.  Can only be accessed on front-end via visualized vets."""
    return  # ### TODO: Complete this route.


def edit_vet_profile(vet_id, vet_dict):
    """Updates vet profile."""
    vet_dict["updated_at"] = datetime.datetime.now()
    vet_dict = {k:v for k,v in vet_dict.iteritems() if v}
    update_dict = update(Veterinarian.__table__).where(Veterinarian.id == vet_id).values(**vet_dict)
    db.session.execute(update_dict)
    db.session.commit()


def add_petvet(companions_list, vet_id):
    linked_pets = []
    for companion_name in companions_list:
        companion_obj = get_companion_obj_by_id(companion_name)
        # If PetVet relationship is not yet in the database, add it.
        petvet_obj = PetVet.query.filter(PetVet.vet_id == vet_id, PetVet.pet_id == companion_obj.id).first()
        if petvet_obj:
            print "PetVet already in db."
            print petvet_obj.id
        else:
            petvet_dict = {}
            petvet_dict = {"pet_id": int(companion_obj.id),
                           "vet_id": int(vet_id)}
            petvet_entry = PetVet(**petvet_dict)
            db.session.add(petvet_entry)
            db.session.commit()
            linked_pets.append(companion_obj.name)
    if linked_pets:
        def stringlist(tolist):
            if len(tolist) <= 2:
                return " and ".join(tolist)
            else:
                return ", ".join(tolist[:-1]) + " and " + tolist[-1]
        flash("This veterinarian is now connected to " + stringlist(linked_pets) + ".")
    return redirect('/veterinarians')


@app.route('/add_new_veterinarian', methods=["POST"])
def add_new_veterinarian():
    """AJAX route to add new veterinarian from veterinarians route."""
    print 'Full Form',request.form

    veterinarian_attributes = ["name", "office_name", "phone_number", "email", "address", "specialties"]
    new_vet_dict = {val:request.form.get(val) for val in veterinarian_attributes}
    vet_obj = Veterinarian.query.filter(Veterinarian.name == new_vet_dict["name"], Veterinarian.office_name == new_vet_dict["office_name"]).first()
    vet_name = new_vet_dict["name"]
    if vet_obj:
        # Update for non-null values in dict in case user enters a vet already listed.
        edit_vet_profile(vet_obj.id, new_vet_dict)
        rtrn_msg = vet_name + "'s veterinarian entry has been updated in our database."

    else:
        # Create new vet entry in db.
        new_vet_dict["created_at"] = datetime.datetime.now()
        new_vet = Veterinarian(**new_vet_dict)
        db.session.add(new_vet)
        db.session.commit()
        vet_obj = Veterinarian.query.filter(Veterinarian.name == new_vet_dict["name"], Veterinarian.office_name == new_vet_dict["office_name"]).first()
        rtrn_msg = vet_name + " has been added to our database."
    companions = request.form.getlist("companions[]")
    if not companions:
        companions = [request.form.get("companions")]
    print companions, "<<<<"
    if companions:
        add_petvet(companions, vet_obj.id)
    return rtrn_msg


@app.route('/find_vet', methods=["GET"])
def find_veterinarian(location="San Francisco"):
    #### TODO: turn this into an AJAX call via vets page.
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        print search("veterinarian", "San Francisco")
        query_results = search("veterinarian", location)
        query_businesses_list = query_results["businesses"]  # becomes a list of dictionaries with each dict being a business profile

        return render_template("veterinary_specialists.html", user_obj=user_obj, query_businesses_list=query_businesses_list)

################

######## NEED TO COMPLETE ROUTES BELOW ########

@app.route('/new_companion', methods=['GET', 'POST'])
def add_new_companion():
    """Add companions individually."""
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        if request.method == 'GET':
            """Shows form to add a companion."""
            def add_new_companion_form():
                companion_attributes_dict = OrderedDict([("logged_in", True),
                                                        ("new_companion", True),
                                                        ("Name", ("name", "text")),
                                                        ("Primary Nickname", ("primary_nickname", "text")),
                                                        ("Species", ("species", "text")),
                                                        ("Breed", ("breed", "text")),
                                                        ("Gender", ("gender", "text")),
                                                        ("Age", ("age", "text"))])
                return companion_attributes_dict

            companion_attributes_dict = add_new_companion_form()
            return render_template("pet_detail.html", companion_attributes_dict=companion_attributes_dict, user_obj=user_obj)

        elif request.method == 'POST':
            """Processes new companion information."""

            value_types = ["name", "primary_nickname", "species", "breed", "gender", "age"]
            process_add_new_companion(value_types)
            return redirect("/")


@app.route('/companion/name/<companion_name>', methods=['GET', 'POST'])
def edit_companion(companion_name):
    """Edit companions individually."""
    user_obj = confirm_loggedin()
    companion_obj = get_companion_obj(companion_name)
    if not user_obj:
        return redirect("/")
    # To confirm if the logged-in user has access to view specific pet:
    if not companion_obj:
        flash("this is not your pet")
        return redirect('/')
    else:
        # If user is allowed to view pet:
        companion_id = companion_obj.id

        if request.method == 'GET':
            companion_attributes_dict = OrderedDict([("logged_in", True),
                                    ("new_companion", False),
                                    ("Name", ("name", "text", companion_obj.name)),
                                    ("Primary Nickname", ("primary_nickname", "text", companion_obj.primary_nickname)),
                                    ("Species", ("species", "text", companion_obj.species)),
                                    ("Breed", ("breed", "text", companion_obj.breed)),
                                    ("Gender", ("gender", "text", companion_obj.gender)),
                                    ("Age", ("age", "text", companion_obj.age))])
            companion_name = companion_obj.name
            return render_template("pet_detail.html", companion_attributes_dict=companion_attributes_dict, companion_name=companion_name, companion_id=companion_id, user_obj=user_obj)
        elif request.method == 'POST':
            companion_id = companion_obj.id
            if request.form.get("delete"):
                # Delete companion!
                db.session.delete(Companion.query.filter(Companion.id == companion_id).first())
                db.session.commit()
                flash('companion profile deleted')
                return redirect("/")

            else:
                value_types = ["name", "primary_nickname", "species", "breed", "gender", "age"]
                values_dict = {val:request.form.get(val) for val in value_types}
                values_dict["updated_at"] = datetime.datetime.now()
                values_dict = {k:v for k,v in values_dict.iteritems() if v}

                ind_update = update(Companion.__table__).where(Companion.id == companion_id).values(**values_dict)
                db.session.execute(ind_update)
                db.session.commit()
                return redirect("/")

##############################################################################

########  Multiprocessing Daemonic Child Process ########

def install_alerts_daemon(*args, **kwargs):
    p = multiprocessing.Process(target=time_alerts)
    # Daemonic processes will only continue running so long as there are non-daemons.
    # Quit when there are no non-daemons left.
    p.daemon = True
    p.start()
    print "installed alerts daemon", p

if __name__ == "__main__":
    app.debug = True

    connect_to_db(app)

    # only run this once (on reload if in debug, or normal load if not debug)
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        install_alerts_daemon()

    app.run()

    # To use the DebugToolbar, uncomment below:
    # DebugToolbarExtension(app)
