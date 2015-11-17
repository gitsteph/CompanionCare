import datetime
from model import db, User, Companion, PetVet, Veterinarian, PetMedication, Medication, Alert, AlertLog
import send_messages
from sqlalchemy import update, delete, exc

def most_recent_alertlog_given_alert_id(alert_id):
    alertlog = db.session.query(AlertLog).filter(AlertLog.alert_id == alert_id).order_by(AlertLog.updated_at.desc()).first()


def most_recent_alertlog_id_given_alert_id(alert_id):
    alertlog_id = most_recent_alertlog_given_alert_id(alert_id).id
    return alertlog_id


def schedule_alert(alert_id, scheduled_alert_datetime, secondary_contact=None):
    """Creates an alertlog entry given alert_id and scheduled_alert_datetime obj from form."""
    scheduled_alert = {}
    scheduled_alert["alert_id"] = alert_id
    scheduled_alert["scheduled_alert_datetime"] = scheduled_alert_datetime
    scheduled_alert["alert_issued"] = None
    scheduled_alert["created_at"] = datetime.datetime.now()
    scheduled_alert["updated_at"] = None

    if secondary_contact:
        scheduled_alert["recipient"] = "secondary"
    else:
        scheduled_alert["recipient"] = "primary"

    scheduled_alert = AlertLog(**scheduled_alert)
    db.session.add(scheduled_alert)
    db.session.commit()

    # Returns the alertlog_id of scheduled alert.
    alertlog_id = most_recent_alertlog_id_given_alert_id(alert_id)
    return alertlog_id


def issue_alert_and_update_alertlog(alertlog_id):
    alertlog_obj = db.session.query(AlertLog).get(alertlog_id)
    recipient = alertlog_obj.recipient
    print recipient, "<<< RECIP"
    if recipient == "primary":
        print type(recipient), "<<< TYPE"
        recipient_contact = db.session.query(Alert).get(alertlog_obj.alert_id).primary_alert_phone
        print recipient_contact
    else:
        print "else printed here"
        recipient_contact = db.session.query(Alert).get(alertlog_obj.alert_id).secondary_alert_phone
    send_messages.send_sms_message(msg_body="Item is due!", phone_number=recipient_contact)
    # TODO: THIS NEEDS TO PULL INFO.
    print "sent text msg for alertlog.id ", alertlog_id

    update_alertlog_issued = update(AlertLog.__table__).where(AlertLog.id == alertlog_id).values({AlertLog.alert_issued: datetime.datetime.now(),
                                                                                                  AlertLog.updated_at: datetime.datetime.now()})
    db.session.execute(update_alertlog_issued)
    db.session.commit()


def process_user_response(alert_id, user_response):
    update_alertlog_with_user_response(alert_id, user_response)
    create_alertlog_entry_based_on_user_response(alert_id, user_response)
    new_alertlog_datetime = most_recent_alertlog_given_alert_id(alert_id).scheduled_alert_datetime
    return new_alertlog_datetime


def update_alertlog_with_user_response(alert_id, user_response):
    """ User response will be recorded to the designated alertlog entry. """
    # Function will only be run when user responds.
    alertlog_id = most_recent_alertlog_id_given_alert_id(alert_id)
    update_alertlog = update(AlertLog.__table__).where(AlertLog.id == alertlog_id).values({AlertLog.action_taken: user_response,
                                                                                           AlertLog.response_timestamp: datetime.datetime.now(),
                                                                                           AlertLog.updated_at: datetime.datetime.now()})
    db.session.execute(update_alertlog)
    db.session.commit()
    return alertlog_id, user_response


def create_alertlog_entry_based_on_user_response(alert_id, user_response):
    """ Based on user response, the next_alert_datetime in alerts will be generated. """
    current_datetime = datetime.datetime.now()
    if user_response == "given":
        alert_frequency = Alert.query.get(alert_id).petmedication.frequency
        scheduled_alert_datetime = current_datetime + datetime.timedelta(hours=alert_frequency)
        schedule_alert(alert_id, scheduled_alert_datetime)
    elif user_response == "delay":
        scheduled_alert_datetime = current_datetime + datetime.timedelta(hours=2)
        schedule_alert(alert_id, scheduled_alert_datetime)
    elif user_response == "forward":
        scheduled_alert_datetime = current_datetime
        secondary_contact = db.session.query(Alert).get(alert_id).secondary_alert_phone
        schedule_alert(alert_id, scheduled_alert_datetime, secondary_contact)
    elif user_response == "cancel":
        update(Alert.__table__).where(Alert.id == alert_id).values({Alert.current: "No",
                                                                    AlertLog.updated_at: datetime.datetime.now()})
