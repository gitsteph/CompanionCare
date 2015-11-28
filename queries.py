from model import db, User, Companion, PetVet, Veterinarian, PetMedication, Medication, Alert, AlertLog, Image
from flask import session


def get_companion_obj(companion_name):
    companion_obj = Companion.query.filter(Companion.name == companion_name, Companion.user_id == session.get("user_id")).first()
    return companion_obj

def get_companion_obj_by_id(companion_id):
    companion_obj = Companion.query.filter(Companion.id == companion_id, Companion.user_id == session.get("user_id")).first()
    return companion_obj

def get_photo_obj(photo_id):
    photo_obj = Image.query.filter(Image.id == photo_id, Image.user_id == session.get("user_id")).first()
    return photo_obj


def get_all_user_companions():
    user_companions_list = Companion.query.filter(Companion.user_id == session.get("user_id")).all()
    return user_companions_list


def get_petvet_id_list(companion_id):
    companion_petvet_list = db.session.query(PetVet.id, PetVet.pet_id, PetVet.vet_id).filter(PetVet.pet_id == companion_id).all()
    print companion_petvet_list, "<<< COMP PETVET LIST"
    petvet_id_list = []
    for petvet_tuple in companion_petvet_list:
        # petvet_tuple[0] is the petvet id.
        petvet_id_list.append(petvet_tuple[0])
    # print petvet_id_list, "<<< PETVET ID LIST"
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
