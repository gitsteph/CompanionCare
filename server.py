from flask import Flask, request, render_template, redirect, flash, jsonify
from flask import session
from flask_debugtoolbar import DebugToolbarExtension
# from jinja2 import StrictUndefined
from model import connect_to_db, db, User, Companion
from sqlalchemy import update, delete
from collections import OrderedDict


import datetime


app = Flask(__name__)

app.secret_key = "###"

# app.jinja_env.undefined = StrictUndefined


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
                                    ("Zipcode", ("zipcode", "text"))])
            return render_template("registration_form.html", user_attributes_dict=user_attributes_dict)

    elif request.method == 'POST':
        """Processes new user registration."""

        # Requests information provided by the user from registration form.
        value_types = ["email", "password", "first_name", "last_name", "zipcode"]
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


@app.route('/user_profile/edit', methods=['GET', 'POST'])
def edit_user_profile():
    user_obj = confirm_loggedin()
    if not user_obj:
        return redirect("/")
    else:
        if request.method == 'GET':
            """Enables user to update their profile information."""
            # NEED TO FIX: Dictionaries are unordered-- need to create a way to index and sort.
            user_attributes_dict = OrderedDict([("logged_in", True),
                                    ("Email", ("email", "email", user_obj.email)),
                                    ("Password", ("password", "password", user_obj.password)),
                                    ("First Name", ("first_name", "text", user_obj.first_name)),
                                    ("Last Name", ("last_name", "text", user_obj.last_name)),
                                    ("Zipcode", ("zipcode", "text", user_obj.zipcode))])

            print user_attributes_dict
            return render_template("registration_form.html", user_attributes_dict=user_attributes_dict)

        elif request.method == 'POST':
            """Processes updated information."""

            # To delete a user:
            if request.form.get("delete"):
                # Queries all companions cared for by primary user.
                # If user is sole primary user, will delete all pets.
                # companion_list = Companion.query.filter(Companion.user_id == session["user_id"]).all()
                # for companion in companion_list:
                # GO BACK TO THIS LATER

                db.session.delete(User.query.filter(User.id == session["user_id"]).first())
                db.session.commit()
                flash('account deleted')
                return redirect("/logout")

            else:
                value_types = ["email", "password", "first_name", "last_name", "zipcode"]
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
            return render_template("pet_detail.html")

        elif request.method == 'POST':
            """Processes new companion information."""

            # Requests information about each companion.
            email = request.form.get("email")

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


@app.route('/veterinary_specialists', methods=['GET','POST'])
def show_veterinarians():
    if request.method == 'GET':
        return render_template("veterinary_specialists.html")
#     else:


@app.route('/medications', methods=['GET','POST'])
def show_medications():
    if request.method == 'GET':
        medication_attributes_dict = {"name": "Medication Name",
                                      "current": "Current",
                                      "frequency": "Frequency",
                                      "prescribing_vet": "Prescribing Veterinarian"}

        # Other attributes will be provided from scraped medication data.
        return render_template("medications.html", medication_attributes_dict=medication_attributes_dict)
#     else:


@app.route('/photos', methods=['GET','POST'])
def show_photos():
    if request.method == 'GET':
        return render_template("photos.html")

#     else:


# @app.route('/photos', methods=['GET','POST'])
# def show_veterinarians():
#     if request.method == 'GET':

#     else:


@app.route('/companion/<int:companion_id>', methods=['POST'])  # get v post
def edit_companion():
    """Edit companions individually."""

    # NEED A WAY TO DELETE PETS
    # companion_obj = Companion.query.filter(Companion.name==values_dict["name"], Companion.user_id == session["user_id"]).first()

    # return render_template("/pet_detail.html", companion_obj=companion_obj)
    pass
    return redirect("/")


##############################################################################
# Helper functions

if __name__ == "__main__":
    app.debug = True

    connect_to_db(app)

    # To use the DebugToolbar, uncomment below:
    # DebugToolbarExtension(app)

    app.run()
