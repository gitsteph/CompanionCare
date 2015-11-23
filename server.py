from flask import Flask, request, render_template, redirect, flash, jsonify, url_for, send_from_directory
from flask import session
from flask_debugtoolbar import DebugToolbarExtension
# from jinja2 import StrictUndefined
from model import connect_to_db, db, User, Companion, PetVet, Veterinarian, PetMedication, Medication, Alert, AlertLog
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug import secure_filename
from sqlalchemy import update, delete, exc
from alerts import *
from queries import *
from collections import OrderedDict
import multiprocessing
from vet_finder import search
# from celery import Celery
import send_messages
import datetime
import time
import os
# from flask.ext.httpauth import HTTPBasicAuth

from uuid import uuid4
import boto
from boto.s3.key import Key
import boto.s3.connection

# NEED TO FIX AUTH STUFF
app = Flask(__name__)

app.secret_key = "###"

app.config['AWS_ACCESS_KEY'] = os.environ["AWSAccessKeyId"]
app.config['AWS_SECRET_KEY'] = os.environ["AWSSecretKey"]
app.config['AWS_BUCKET_NAME'] = os.environ["AWSBuckedName1"]

UPLOAD_FOLDER = 'static/img/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])

# auth = HTTPBasicAuth()

# app.jinja_env.undefined = StrictUndefined


# ### REMOVE AFTER SEEDING
# def add_unknown_vet():
#     vet_dict={}
#     vet_dict["name"] = "Unknown"
#     vet_dict["created_at"] = datetime.datetime.now()
#     new_vet = Veterinarian(**vet_dict)
#     db.session.add(new_vet)
#     db.session.commit()


@app.route('/photo/<filename>', methods=["GET"])  ## THIS NEEDS WORK
def uploaded_file(filename):
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        filepath = "/" + UPLOAD_FOLDER + "/" + filename
        return render_template('photos.html', filepath=filepath, filename=filename, user_obj=user_obj)


@app.route('/photos/upload', methods=["POST"])
def upload_file_online():
    #### TODO: STORE POINTER AND OTHER INFO IN TO DB!
    # Uploads files (photos) to AWS S3.
    if request.method == 'POST':
        data_file = request.files.get('photo')
        if data_file and allowed_file(data_file.filename):
            file_name = data_file.filename
            conn = boto.s3.connect_to_region('us-west-1',
               aws_access_key_id=app.config["AWS_ACCESS_KEY"],
               aws_secret_access_key=app.config["AWS_SECRET_KEY"],
               is_secure=True,
               calling_format = boto.s3.connection.OrdinaryCallingFormat(),
               )
            bucket = conn.get_bucket(app.config["AWS_BUCKET_NAME"])
            k = Key(bucket)
            k.set_contents_from_string(data_file.read())
            url = k.generate_url(expires_in=0, query_auth=False)  # need to set to private later
            return jsonify(name=file_name)

            # return redirect(url_for('uploaded_file', filename=filename))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

def upload_file_locally():
    file = request.files['photo']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return redirect(url_for('uploaded_file', filename=filename))
    else:
        return redirect('/photos/upload')

# Helper function to check whether user is logged in.
def confirm_loggedin():
    user_id = session.get("user_id")
    if not user_id:
        print "redirected"
        return None
    else:
        user_obj = User.query.filter(User.id == user_id).first()
    return user_obj

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

    return send_messages.reply_to_user(companion_name, new_scheduled_alert_str, user_response, user_name)


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

        # TODO: if response is received, update_alertlog_with_user_response.
        # TODO: after alertlog updated, update_next_alert_based_on_user_response.
        # run every minute
        time.sleep(10)

################

######## LOGIN/LOGOUT ########
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
        print companion_obj_list
        return render_template("index.html", user_obj=user_obj, companion_obj_list=companion_obj_list)
    else:
        return render_template("home.html")


@app.route('/register', methods=['GET', 'POST'])
def register_user():
    if request.method == 'GET':
        """Shows form to register new user."""
        if confirm_loggedin():
            flash('logged into account, already have account')
            return redirect("/")
        else:
            user_attributes_dict = OrderedDict([("logged_in", False),
                                                ("Email", ("email", "email")),
                                                ("Password", ("password", "password")),
                                                ("First Name", ("first_name", "text")),
                                                ("Last Name", ("last_name", "text")),
                                                ("Phone Number", ("phone", "text")),
                                                ("Zipcode", ("zipcode", "text"))])
            return render_template("registration_form.html", user_attributes_dict=user_attributes_dict)

    elif request.method == 'POST':
        """Processes new user registration."""

        # Requests information provided by the user from registration form.
        value_types = ["email", "first_name", "last_name", "phone", "zipcode"]
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
    # Queries all companions cared for by primary user.
                # If user is sole primary user, will delete all pets.
                # companion_list = Companion.query.filter(Companion.user_id == session["user_id"]).all()
                # for companion in companion_list:
                # GO BACK TO THIS LATER

    # To delete a user:
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
    companion_values_dict = {val:request.form.get(val) for val in value_types}
    companion_values_dict["user_id"] = session["user_id"]
    companion_values_dict["created_at"] = datetime.datetime.now()
    companion_values_dict["updated_at"] = None
    new_companion = Companion(**companion_values_dict)

    #### TODO: Fix minor bug--default value in form is empty string if no input provided.
    #### Either make age required or remove default val. Age requires int.

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

######## ALERTS ########


@app.route('/alerts', methods=["GET", "POST"])
def show_all_alerts_and_form():
    """Renders alerts page with existing alerts and other routes to add and edit alerts."""
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        ######## THIS NEEDS WORK!!!!! GO BACK

        # all_alerts_dict_by_companion = {}
        # all_alerts_dict_by_medication = {}

        # # Query for list of all user's companions.
        # user_companions_list = get_all_user_companions()
        # print user_companions_list

        # # Iterate through list of user's companions to generate a list of petmed IDs and related info to show user for alerts.
        # for companion_obj in user_companions_list:
        #     alert_dict = {}
        #     companion_petvets_list = companion_obj.petvets  # returns list of petvets per pet
        #     alert_dict["companion_petvets_list"] = companion_petvets_list
        #     for petvet in companion_petvets_list:
        #         vet_name = petvet.veterinarian.name
        #         alert_dict["vet_name"] = vet_name
        #         petmeds_list = petvet.petmeds  # returns list of petmeds per petvet
        #         alert_dict["petmeds_list"] = petmeds_list
        #         for petmed in petmeds_list:
        #             medication = petmed.medication
        #             alert_dict["medication"] = medication



            # INFO NEEDED: medication, petmed, petvet id >>> vet name

        # Pass through petmed IDs to enable adding alerts onto meds.  JS front-end mechanism: click the med to popup a modal with a form to add the alert.
        # Or add a new alert to a medication not listed (will create a medication object too).
        # Enable user to minimize the add_new_alert div (on front-end).


        # VISUALIZE the relationships below! And enable viewing/editing from visualization area.  (separate div)
        return render_template('alerts.html', user_obj=user_obj)


@app.route('/add_new_alert', methods=["POST"])
def add_new_alert():
    alert_variables = ["primary_alert_phone", "secondary_alert_phone", "alert_datetime_start", "alert_datetime_end", "alert_type"]
    alert_frequency = request.form.get("alert_frequency")
    alert_frequency_unit = request.form.get("alert_frequency_unit")
    if alert_frequency_unit == "days":  # to convert to hours
        alert_frequency = alert_frequency * 24
    alert_values_dict = {}
    alert_values_dict["alert_frequency"] = alert_frequency
    alert_values_dict = {var:request.form.get(var) for var in alert_variables}
    print alert_values_dict
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

    rtrn_msg = "An alert has been set for " + str(companion_obj.name) +"."
    return rtrn_msg

######## MEDICATIONS ########

@app.route('/medications', methods=['GET', 'POST'])
def show_all_medications():
    user_obj = confirm_loggedin()
    if not user_obj:
        redirect('/')
    else:
        medications = Medication.query.order_by(Medication.name).all()

        ### TODO: MAY WANT TO SORT BASED ON name.lower() b/c ascii alpha is weird.

        # Splitting the med_name_list into three mini-lists to enable easy display in columns on the front-end.
        third_med_list = len(medications)/3
        first_third_med_list = medications[:third_med_list]
        second_third_med_list = medications[third_med_list:2*third_med_list]
        last_third_med_list = medications[2*third_med_list:]
        list_med_list = [first_third_med_list, second_third_med_list, last_third_med_list]

        return render_template("medications.html", list_med_list=list_med_list, user_obj=user_obj)


@app.route('/add_companion_medication/<companion_name>', methods=['POST'])  ### NEW PATH TO ADD FOR COMPANION
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
# @auth.login_required
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


######## VETERINARIANS ########

@app.route('/veterinarians', methods=['GET', 'POST'])
def show_veterinarians():
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        #### TODO: VISUALIZE relationships and enable dynamic edits.
        return render_template("veterinary_specialists.html", user_obj=user_obj)


@app.route('/edit_veterinarian_profile', methods=["POST"])
def edit_vet_ajax():
    """AJAX route to edit existing veterinarian profile.  Can only be accessed on front-end via visualized vets."""
    return  #### TODO: Complete this route.


def edit_vet_profile(vet_id, vet_dict):
    """Updates vet profile."""
    vet_dict["updated_at"] = datetime.datetime.now()
    vet_dict = {k:v for k,v in vet_dict.iteritems() if v}
    update_dict = update(Veterinarian.__table__).where(Veterinarian.id == vet_id).values(**vet_dict)
    db.session.execute(update_dict)
    db.session.commit()


@app.route('/add_new_veterinarian', methods=["POST"])
def add_new_veterinarian():
    """AJAX route to add new veterinarian from veterinarians route."""
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
        rtrn_msg = vet_name + " has been added to our database."

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

#### CHECK AND REFACTOR BELOW

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


######## PHOTOS ########

@app.route('/photos', methods=['GET'])
def show_photos():
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:



        return render_template("photos.html", user_obj=user_obj)


################

######## NEED TO COMPLETE ROUTES BELOW ########

@app.route('/alerts/<companion_name>', methods=["GET", "POST"])
def show_alerts_and_form(companion_name):
    # Will return a list of petmed_ids (unicode) that the user selects to add alert.
    user_obj = confirm_loggedin()
    companion_obj = get_companion_obj(companion_name)
    if not (user_obj and companion_obj):
        return redirect("/")
    else:
        if request.method == "POST":
            petmed_id_for_alerts = request.form.getlist("alerts")
            companion_obj = get_companion_obj(companion_name)
            petmed_med_dict = get_petmed_medication_by_petmed_id_list(petmed_id_for_alerts)

            # Renders new form with existing alerts, petmeds that have been selected, and
            # fields to add alerts to selected petmeds.
            return render_template('alerts.html',
                                    companion_obj=companion_obj,
                                    petmed_med_dict=petmed_med_dict,
                                    user_obj=user_obj)


@app.route('/alerts/<int:companion_id>/add', methods=["POST"])
def add_alerts(companion_name):
    # TO ADD AN ALERT ONLY-- need to update too. (TODO)  ALSO validate logged in.
    value_types = ["primary_alert_phone", "secondary_alert_phone", "petmed_id"]
    values_dict = {val:request.form.get(val) for val in value_types}
    values_dict["alert_options"] = request.form.getlist("alert_options")
    values_dict["created_at"] = datetime.datetime.now()
    values_dict["updated_at"] = datetime.datetime.now()  # Only true for creation.

    new_alert = Alert(**values_dict)
    db.session.add(new_alert)
    db.session.commit()

    # Schedule alert in alertlog (set to not-issued).
    alert_id = db.session.query(Alert).filter(Alert.petmed_id == values_dict["petmed_id"]).order_by(Alert.updated_at.desc()).first().id
    scheduled_alert_datetime = request.form.get("scheduled_alert_datetime")
    schedule_alert(alert_id, scheduled_alert_datetime)

    return redirect('/')

# def show_medications():
#     if request.method == 'GET':
#         medication_attributes_dict = OrderedDict([("name", "Medication Name"),
#                                       ("current", "Current"),
#                                       ("frequency", "Frequency"),
#                                       ("prescribing_vet", "Prescribing Veterinarian")])
#         companion_name = request.args.get("companion_name")
#         companion_id = request.args.get("companion_id")
#         # Other attributes will be provided from scraped medication data.
#         return render_template("medications.html",
#                                medication_attributes_dict=medication_attributes_dict,
#                                companion_name=companion_name,
#                                companion_id=companion_id)

#     elif request.method == 'POST':

#             value_types = ["name", "current", "frequency", "prescribing_vet"]
#             values_dict = {val:request.form.get(val) for val in value_types}
#             values_dict["user_id"] = session["user_id"]
#             # values_dict["created_at"] = datetime.datetime.now()
#             # values_dict["updated_at"] = None

#             # new_companion = Companion(**values_dict)
#             # db.session.add(new_companion)
#             # db.session.commit()




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
            if request.form.get("delete"):
                # TODO: Notify all users of companion deletion.
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
                return redirect("/")  # maybe redirect back to pet detail.

##############################################################################
# Helper functions

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
