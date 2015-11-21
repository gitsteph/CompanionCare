from flask import Flask, request, render_template, redirect, flash, jsonify
from flask import session
from flask_debugtoolbar import DebugToolbarExtension
# from jinja2 import StrictUndefined
from model import connect_to_db, db, User, Companion, PetVet, Veterinarian, PetMedication, Medication, Alert, AlertLog
from sqlalchemy import update, delete, exc
from alerts import *
from queries import *
from collections import OrderedDict
import multiprocessing
# from celery import Celery
import send_messages
import datetime
import time
import os
# from flask.ext.httpauth import HTTPBasicAuth

# NEED TO FIX AUTH STUFF

# auth = HTTPBasicAuth()
app = Flask(__name__)

app.secret_key = "###"

# app.jinja_env.undefined = StrictUndefined


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


# Helper function to check whether user is logged in.
def confirm_loggedin():
    user_id = session.get("user_id")
    if not user_id:
        print "redirected"
        return None
    else:
        user_obj = User.query.filter(User.id == user_id).first()
    return user_obj


@app.route('/', methods=['GET'])
def show_homedash():
    """If not logged in, will show homepage.  Else, will show dashboard."""

    if confirm_loggedin():
        companion_obj_list = Companion.query.filter(Companion.user_id == session['user_id']).all()
        print companion_obj_list

        return render_template("index.html", companion_obj_list=companion_obj_list)
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
        value_types = ["email", "password", "first_name", "last_name", "phone", "zipcode"]
        values_dict = {val:request.form.get(val) for val in value_types}
        values_dict["created_at"] = datetime.datetime.now()

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


@app.route('/login', methods=['POST'])
def process_login():
    """Processes log in information for existing users."""
    email = request.form.get("email")
    password = request.form.get("password")

    # Queries "users" table in database to determine whether the user already has an account.
    # If the user has an account, the user's account information and password are verified.
    user_object = User.query.filter(User.email == email).first()
    if user_object:
        if user_object.password == password:
            session['user_id'] = user_object.id

            flash("Logged in")
            return redirect("/")  # dashboard
        else:
            flash('wrong password')
            return redirect("/")  # login page
    else:
        flash('no such user')
        return redirect("/")


@app.route('/logout')
def logout():
    """Log out."""

    del session["user_id"]
    flash("Logged Out.")
    return redirect("/")


@app.route('/user_profile', methods=['GET'])  # get v post
def user_profile():
    """View and edit user information."""
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        return render_template("user_profile.html", user_obj=user_obj)


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
    flash('account deleted')
    return redirect("/logout")


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


@app.route('/user_profile/edit', methods=['GET', 'POST']) ## MAYBE DELETE OR REFACTOR THIS ROUTE
def edit_user_profile():
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        if request.method == 'GET':
            """Enables user to update their profile information."""
            user_attributes_dict = OrderedDict([("logged_in", True),
                                                ("Email", ("email", "email", user_obj.email)),
                                                ("Password", ("password", "password", user_obj.password)),
                                                ("First Name", ("first_name", "text", user_obj.first_name)),
                                                ("Last Name", ("last_name", "text", user_obj.last_name)),
                                                ("Zipcode", ("zipcode", "text", user_obj.zipcode)),
                                                ("Phone", ("phone", "text", user_obj.phone))])

            print user_attributes_dict
            return render_template("registration_form.html", user_attributes_dict=user_attributes_dict)

        elif request.method == 'POST':
            """Processes updated information."""
            value_types = ["email", "password", "first_name", "last_name", "zipcode", "phone"]
            values_dict = {val:request.form.get(val) for val in value_types}
            values_dict["updated_at"] = datetime.datetime.now()
            values_dict = {k:v for k,v in values_dict.iteritems() if v}

            ind_update = update(User.__table__).where(User.id == session['user_id']).values(**values_dict)
            db.session.execute(ind_update)
            db.session.commit()

            return redirect("/user_profile")


@app.route('/new_companion', methods=['GET', 'POST'])
def add_companion():
    """Add companions individually."""
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        if request.method == 'GET':
            """Shows form to add a companion."""
            companion_attributes_dict = OrderedDict([("logged_in", True),
                                                    ("new_companion", True),
                                                    ("Name", ("name", "text")),
                                                    ("Primary Nickname", ("primary_nickname", "text")),
                                                    ("Species", ("species", "text")),
                                                    ("Breed", ("breed", "text")),
                                                    ("Gender", ("gender", "text")),
                                                    ("Age", ("age", "text"))])

            return render_template("pet_detail.html", companion_attributes_dict=companion_attributes_dict)

        elif request.method == 'POST':
            """Processes new companion information."""

            # Requests information about each companion.
            value_types = ["name", "primary_nickname", "species", "breed", "gender", "age"]
            values_dict = {val:request.form.get(val) for val in value_types}
            values_dict["user_id"] = session["user_id"]
            values_dict["created_at"] = datetime.datetime.now()
            values_dict["updated_at"] = None

            new_companion = Companion(**values_dict)
            db.session.add(new_companion)
            db.session.commit()

            return redirect("/")


@app.route('/vet_finder', methods=['GET'])
def find_vet():
    pass
    return redirect('/')


@app.route('/veterinary_specialists', methods=['GET', 'POST'])
def show_veterinarians():
    if request.method == 'GET':
        return render_template("veterinary_specialists.html")
#     else:


@app.route('/medications/<int:companion_id>', methods=['GET', 'POST'])
def show_medications(companion_id):
    """"Path to add/view medications for a specific companion.  GET will render
    form template, POST will request and process input."""
    user_obj = confirm_loggedin()
    companion_obj = get_companion_obj(companion_id)
    if not (user_obj and companion_obj):
        return redirect("/")
    else:
        if request.method == 'GET':
            medication_attributes_dict = OrderedDict([("name", "Medication Name"),
                                          ("current", "Current"),
                                          ("prescribing_vet", "Prescribing Veterinarian")])
            companion_name = companion_obj.name

            # Queries for all medications for specific pet (companion_id), returning a list of petmed objects.
            petmed_list = get_petmed_list_by_companion(companion_id)

            # Creates a dictionary with PetMedication tied to Medication.
            petmed_dict = {}
            for petmed_obj in petmed_list:
                medication_obj = Medication.query.filter(Medication.id == petmed_obj.medication_id).first()
                petmed_dict[petmed_obj] = medication_obj

            # Other attributes will be provided from scraped medication data.
            # TODO: enable user to click on medication ID link and see a modal window/display of medication data queried from Medication table.
            return render_template("medications.html",
                                   medication_attributes_dict=medication_attributes_dict,
                                   companion_name=companion_name,
                                   companion_id=companion_id,
                                   petmed_dict=petmed_dict)

        elif request.method == 'POST':
            vet_name = request.form.get("prescribing_vet")
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

            # List of values to pull from form.
            petmed_values = ["current"]
            med_values = ["name"]
            med_name = request.form.get("name")
            # Dictionary of Model.py classes and their corresponding input attributes.
            class_list_dict = OrderedDict([(Medication, med_values),
                                           (PetMedication, petmed_values)])

            # For each db.Model class and its corresponding values list above,
            # retrieve values input by user from form and create a dictionary
            # that is then passed through via **kwargs to create an instance of
            # class_name db.Model class.  Add instance to db and commit transaction.
            print "companion_id = ", companion_id
            for class_name, val_list in class_list_dict.iteritems():
                values_dict = {val:request.form.get(val) for val in val_list}
                if class_name == Medication:
                    med_obj = Medication.query.filter(Medication.name == med_name).first()
                    if med_obj:
                        # won't put in a new medication if medication exists.
                        continue
                elif class_name == PetMedication:
                    med_id = Medication.query.filter(Medication.name == med_name).first().id
                    # Will only create new petmed entry if none exists.
                    petvet_id = PetVet.query.filter(PetVet.vet_id == vet_id, PetVet.pet_id == companion_id).first().id
                    if PetMedication.query.filter(PetMedication.petvet_id == petvet_id, PetMedication.medication_id == med_id).first():
                        continue
                    else:
                        values_dict["medication_id"] = int(med_id)
                        values_dict["petvet_id"] = int(petvet_id)
                        values_dict["frequency"] = int(request.form.get("frequency", 0))
                values_dict["created_at"] = datetime.datetime.now()
                values_dict["updated_at"] = None
                new_entry = class_name(**values_dict)
                db.session.add(new_entry)
                db.session.commit()

        return redirect('/')


@app.route('/alerts/<int:companion_id>', methods=["GET", "POST"])
def show_alerts_and_form(companion_id):
    # Will return a list of petmed_ids (unicode) that the user selects to add alert.
    user_obj = confirm_loggedin()
    companion_obj = get_companion_obj(companion_id)
    if not (user_obj and companion_obj):
        return redirect("/")
    else:
        if request.method == "POST":
            petmed_id_for_alerts = request.form.getlist("alerts")
            companion_obj = get_companion_obj(companion_id)
            petmed_med_dict = get_petmed_medication_by_petmed_id_list(petmed_id_for_alerts)

            # Renders new form with existing alerts, petmeds that have been selected, and
            # fields to add alerts to selected petmeds.
            return render_template('alerts.html',
                                    companion_obj=companion_obj,
                                    petmed_med_dict=petmed_med_dict,
                                    user_obj=user_obj)


@app.route('/alerts/<int:companion_id>/add', methods=["POST"])
def add_alerts(companion_id):
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


@app.route('/medications', methods=['GET', 'POST'])
def show_all_medications():
    medications = Medication.query.order_by(Medication.name).all()

    ### TODO: MAY WANT TO SORT BASED ON name.lower() b/c ascii alpha is weird.

    # Splitting the med_name_list into three mini-lists to enable easy display in columns on the front-end.
    third_med_list = len(medications)/3
    first_third_med_list = medications[:third_med_list]
    second_third_med_list = medications[third_med_list:2*third_med_list]
    last_third_med_list = medications[2*third_med_list:]
    list_med_list = [first_third_med_list, second_third_med_list, last_third_med_list]

    return render_template("medications.html", list_med_list=list_med_list)


def view_individual_medication(med_name):
    medication_obj = Medication.query.filter(Medication.name == med_name).first()
    return medication_obj


@app.route('/medications/api/<med_name>', methods=['GET'])
# @auth.login_required
def view_single_med(med_name):
    medication_obj = view_individual_medication(med_name)
    med_cols = [("Name", medication_obj.name), ("General Description", medication_obj.general_description), ("How It Works", medication_obj.how_it_works),
                ("Missed Dose?", medication_obj.missed_dose), ("Storage Information", medication_obj.storage_information), ("Side Effects & Contraindications", medication_obj.side_effects_and_drug_interactions)]
    medication_dict = {}
    for col in med_cols:
        medication_dict[col[0]] = str(col[1]).replace('\n', " ")
    medication_dict["uri"] = "/medications/api/" + med_name

    return jsonify(medication_dict)


@app.route('/medications/<med_name>', methods=['GET', 'POST'])
def edit_medication(med_name):
    medication_obj = view_individual_medication(med_name)
    return render_template('medication_detail.html', medication_obj=medication_obj)


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
    print "made it!"
    db.session.delete(Medication.query.filter(Medication.name == med_name).first())
    db.session.commit()

    return "The medication entry has been deleted."



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

# @app.route('/photos', methods=['GET'])
# def show_photos():
#     if request.method == 'GET':
#         return render_template("photos.html")

#     else:


# # @app.route('/alerts', methods=['GET','POST'])
# # def show_veterinarians():
# #     if request.method == 'GET':

# #     else:


@app.route('/companion/<int:companion_id>', methods=['GET', 'POST'])  # get v post
def edit_companion(companion_id):
    """Edit companions individually."""
    user_obj = confirm_loggedin()
    companion_obj = Companion.query.filter(Companion.id == companion_id).first()
    if not (user_obj and companion_obj):
        return redirect("/")
    else:
        # To confirm if the logged-in user has access to view specific pet:
        if session['user_id'] != companion_obj.user_id:
            flash("this is not your pet")
            return redirect('/')
        # If user is allowed to view pet:
        else:
            if request.method == 'GET':
                companion_attributes_dict = OrderedDict([("logged_in", True),
                                        ("new_companion", False),
                                        ("Name", ("name", "text", companion_obj.name)),
                                        ("Primary Nickname", ("primary_nickname", "text", companion_obj.primary_nickname)),
                                        ("Species", ("species", "text", companion_obj.species)),
                                        ("Breed", ("breed", "text", companion_obj.breed)),
                                        ("Gender", ("gender", "text", companion_obj.gender)),
                                        ("Age", ("age", "text", companion_obj.age))])
                print "companion_id: ", companion_id
                companion_name = companion_obj.name
                return render_template("pet_detail.html", companion_attributes_dict=companion_attributes_dict, companion_name=companion_name, companion_id=companion_id)
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
