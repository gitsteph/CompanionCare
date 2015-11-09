import os
from twilio.rest import TwilioRestClient

account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
twilio_number = os.environ['TWILIO_NUMBER']

client = TwilioRestClient(account_sid, auth_token)


def send_sms_message(msg_body):
    # Running this will send a text message.
    sms_message = client.messages.create(to="+12168323813", from_="+12163507084",
                                         body=str(msg_body))

def send_mms_message(msg_body, media_url1="", media_url2=""):
    # Running this will send an mms message!
    mms_message = client.messages.create(to="+12163927548", from_="+12163507084",
                                         body=msg_body,
                                         media_url=[str(media_url1), str(media_url2)])
