from model import connect_to_db, db, Medication
from flask import Flask
from sqlalchemy import update, delete, exc
import datetime
import json

app = Flask(__name__)

app.secret_key = "###"

all_meds_dict = {}
with open('./medications.json', 'r') as fp:
    all_meds_dict = json.load(fp)

all_meds_list = sorted(all_meds_dict.items())

## TODO: Need to refactor how side_effects... is stored/parsed.

def strip_and_stringify_med_vals(med_values_list):
    med_val_str = ('\n').join(med_values_list)
    for unicode_str in [u'\xa0', u'\u2019', u'\u2014', u'\xc2', u'\xae']:
        med_val_str = med_val_str.replace(unicode_str, "")
    return med_val_str

@app.route('/')
def write_med_to_db():
    for med_name, med_attribute_dict in all_meds_list:
        med_dict = {}
        med_dict["name"] = med_name
        for key_attr_value, med_values_list in med_attribute_dict.iteritems():
            if key_attr_value == "General Description":
                med_val_str = strip_and_stringify_med_vals(med_values_list)
                med_dict["general_description"] = str(med_val_str)
            elif key_attr_value == "Missed Dose?":
                med_val_str = strip_and_stringify_med_vals(med_values_list)
                med_dict["missed_dose"] = str(med_val_str)
            elif key_attr_value == "Storage Information":
                med_val_str = strip_and_stringify_med_vals(med_values_list)
                med_dict["storage_information"] = str(med_val_str)
            elif key_attr_value == "How It Works":
                med_val_str = strip_and_stringify_med_vals(med_values_list)
                med_dict["how_it_works"] = str(med_val_str)
            elif key_attr_value == "Side Effects and Drug Reactions":
                med_val_str = strip_and_stringify_med_vals(med_values_list)
                med_dict["side_effects_and_drug_interactions"] = str(med_val_str)
            med_dict["created_at"] = datetime.datetime.now()
        if med_dict["name"]:
            new_med = Medication(**med_dict)
            db.session.add(new_med)
            db.session.commit()
    return (""" hihi """)


if __name__ == "__main__":
    app.debug = True

    connect_to_db(app)
    app.run()
