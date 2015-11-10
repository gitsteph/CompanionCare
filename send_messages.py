import os
from twilio.rest import TwilioRestClient
from twilio import twiml
from flask import request


account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
twilio_number = os.environ['TWILIO_NUMBER']

client = TwilioRestClient(account_sid, auth_token)


def standardize_phone_number(phone_number):
    phone_number = phone_number.strip()
    if phone_number[0] != "+":
        phone_number = "+" + str(phone_number)
    if phone_number[1] != "1":
        phone_number = phone_number[:1] + "1" + phone_number[1:]
    return phone_number

def send_sms_message(msg_body, phone_number):
    # Running this will send a text message.
    phone_number = standardize_phone_number(phone_number)
    sms_message = client.messages.create(to=phone_number, from_="+12163507084",
                                         body=str(msg_body))

def send_mms_message(msg_body, media_url1="", media_url2=""):
    # Running this will send an mms message!
    phone_number = standardize_phone_number(phone_number)

    mms_message = client.messages.create(to=phone_number, from_="+12163507084",
                                         body=msg_body,
                                         media_url=[str(media_url1), str(media_url2)])

def reply_to_user(user_name=""):
    # Will reply to messages received.
    # Users.query.filter(phone=)
    resp = twiml.Response()
    message = user_name + ", your response has been received."
    resp.message(message)
    return str(resp)
