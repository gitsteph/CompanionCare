from model import db, User, Companion, PetVet, Veterinarian, PetMedication, Medication, Alert, AlertLog, Image
from collections import defaultdict
import datetime
from flask import session


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

######## SQLALCHEMY/POSTGRESQL QUERIES ########


def get_companion_obj(companion_name):
    companion_obj = Companion.query.filter(Companion.name == companion_name, Companion.user_id == session.get("user_id")).first()
    return companion_obj


def get_companion_obj_by_id(companion_id):
    companion_obj = Companion.query.filter(Companion.id == companion_id, Companion.user_id == session.get("user_id")).first()
    return companion_obj


def get_all_user_companions():
    user_companions_list = Companion.query.filter(Companion.user_id == session.get("user_id")).all()
    return user_companions_list


def get_all_alerts():
    # Query for list of all user's companions.
    user_companions_list = get_all_user_companions()

    # Iterate through list of user's companions to generate a list of petmed IDs and related info to show user for alerts.
    alert_dict = objtree()
    inactive_alert_dict = objtree()

    # Creates a defaultdict with the companion, medication, alert, and last scheduled alertlog entry for each petmed.
    for companion_obj in user_companions_list:
        companion_petvets_list = companion_obj.petvets  # returns list of petvets per pet
        for petvet in companion_petvets_list:
            petmeds_list = petvet.petmeds  # returns list of petmeds per petvet
            for petmed in petmeds_list:
                medication = petmed.medication
                alerts = petmed.alerts
                if alerts:
                    for alert in alerts:
                        # Active Alerts
                        if datetime.datetime.now() < alert.alert_datetime_end:
                            alertlog = most_recent_alertlog_given_alert_id(alert.id)
                            if not alertlog:
                                print "invalid alert id", alert.id, alert
                            alert_dict[companion_obj][medication][alert] = alertlog
                        # Inactive Alerts
                        else:
                            inactive_alert_dict[companion_obj][medication][alert] = most_recent_alertlog_given_alert_id(alert.id)
                # PetMedications never assigned alerts
                elif medication not in inactive_alert_dict[companion_obj]:
                        inactive_alert_dict[companion_obj][medication] = objtree()
    alert_dict = dd2dr(alert_dict)
    inactive_alert_dict = dd2dr(inactive_alert_dict)
    return alert_dict, inactive_alert_dict


def get_alerts_sorted_by_time():
    # Query for list of all user's companions.
    user_companions_list = get_all_user_companions()

    # Iterate through list of user's companions to generate a list of petmed IDs and related info to show user for alerts.
    alert_list = []

    # Creates a defaultdict with the companion, medication, alert, and last scheduled alertlog entry for each petmed.
    for companion_obj in user_companions_list:
        companion_petvets_list = companion_obj.petvets  # returns list of petvets per pet
        for petvet in companion_petvets_list:
            petmeds_list = petvet.petmeds  # returns list of petmeds per petvet
            for petmed in petmeds_list:
                medication = petmed.medication
                alerts = petmed.alerts
                if alerts:
                    for alert in alerts:
                        # Active Alerts
                        if datetime.datetime.now() < alert.alert_datetime_end:
                            alertlog = most_recent_alertlog_given_alert_id(alert.id)
                            if not alertlog:
                                print "invalid alert id", alert.id, alert
                            alert_list.append( (companion_obj, medication, alert, alertlog) )
    return sorted(alert_list,key=lambda v: v[3].scheduled_alert_datetime)


def most_recent_alertlog_given_alert_id(alert_id):
    alertlog = db.session.query(AlertLog).filter(AlertLog.alert_id == alert_id).order_by(AlertLog.updated_at.desc()).first()
    return alertlog


def most_recent_alertlog_id_given_alert_id(alert_id):
    alertlog_id = most_recent_alertlog_given_alert_id(alert_id).id
    return alertlog_id


def get_petvet_id_list(companion_id):
    companion_petvet_list = db.session.query(PetVet.id, PetVet.pet_id, PetVet.vet_id).filter(PetVet.pet_id == companion_id).all()
    print companion_petvet_list, "<<< COMP PETVET LIST"
    petvet_id_list = []
    for petvet_tuple in companion_petvet_list:
        # petvet_tuple[0] is the petvet id.
        petvet_id_list.append(petvet_tuple[0])
    return petvet_id_list


def get_petmed_list_by_companion(companion_id):
    petvet_id_list = get_petvet_id_list(companion_id)
    petmed_list = PetMedication.query.filter(PetMedication.petvet_id.in_(petvet_id_list)).all()
    # print petmed_list, "<<< COMP PETMED OBJECT LIST"
    return petmed_list


def get_petmed_medication_by_petmed_id_list(petmed_list):
    petmed_med_dict = {}
    for petmed_id in petmed_list:
        # print petmed_list, "<<< PETMED LIST BEING PASSED THROUGH"
        petmed_obj = PetMedication.query.get(petmed_id)
        med_obj = petmed_obj.medication
        petmed_med_dict[petmed_obj] = med_obj
        # print petmed_med_dict, "<<< PETMED MED DICT"
    return petmed_med_dict


def get_photo_obj(photo_id):
    photo_obj = Image.query.filter(Image.id == photo_id, Image.user_id == session.get("user_id")).first()
    return photo_obj
