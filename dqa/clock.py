"""."""

import os
import ast
import atexit
from functools import wraps
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # alternative to thirdparty pytz

# from apscheduler.schedulers.background import BackgroundScheduler
# import flask
import firebase_admin
from firebase_admin import db
from firebase_admin import auth
from firebase_admin import credentials
import google.oauth2.id_token
from google.auth.transport import requests
from werkzeug.utils import redirect

from logger import GCPLogging
from apscheduler.schedulers.blocking import BlockingScheduler

sched = BlockingScheduler(timezone='Asia/Kolkata')

# app = Flask(__name__)


CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
certs = rf"{os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')}".strip()

parsed_json = ast.literal_eval(str(certs))
cred = credentials.Certificate(parsed_json)
firebase_admin.initialize_app(cred, {
    'databaseURL':
    'https://basic-python-quests-default-rtdb.asia-southeast1.firebasedatabase.app'
})

logme = GCPLogging(parsed_json)
# Disable them in production
if os.getenv("dev") == "local":
  os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
  os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

firebase_request_adapter = requests.Request()


def tomorrow():
  next_date = datetime.today() + timedelta(days=1)
  return next_date.strftime("%Y/%m/%d")


def get_date():
  """Returns date time for url format in firebase"""
  return (datetime.now(ZoneInfo('Asia/Kolkata')) +
          timedelta(hours=6, minutes=30)).strftime("%Y/%m/%d")


def get_user_details():
  id_token = request.cookies.get("token")
  user_data = {}
  flg = False
  if id_token:
    try:
      user_data = google.oauth2.id_token.verify_firebase_token(
          id_token, firebase_request_adapter)
      flg = True
    except Exception as error:
      logme.error(f"Sorry, Error in getting user_data: {error}")
  return flg, user_data


def create_topics(topic):
  if not get_topic(topic):
    ref = db.reference("/Topic_List")

    ref.push({
        'name': topic
    })


def get_topics():
  ref = db.reference("/Topic_List")
  return {key: value['name'] for key, value in ref.get().items()}


def get_topic(topic):
  ref = db.reference("/Topic_List")
  topic_id = ""
  for key in ref.order_by_child('name').equal_to(topic).get():
    topic_id = key
  return topic_id


def get_latest_quest(topic_id):
  logme.info("inside get_todays_quest")
  name = quest = None
  # date = get_date()Display and manage the top processestop
  # logme.info(f"Todays date: {today}")
  past = 0
  while not (qid:= get_value(f"/Topics/{topic_id}/{get_date(past)}",
                              "qid", False)):
    past -= 1

  # Now lets find the quest details to display
  logme.info("Now lets find the quest details to display")
  url = f"/QuestionBank/{topic_id}/{qid}"
  name = get_value(url, "name", "")
  quest = get_value(url, "quest", "")
  return qid, name, quest, get_date(past)


def get_solution(topic: str, qid: str) -> str:
  ref = db.reference(f"/QuestionBank/{topic}/{qid}")
  return ref.get() if ref else None


def get_value(url, key, default_value):
  ref = db.reference(f"/{url}")
  return data.get(key) if (data:= ref.get()) else default_value


def get_cutoftime(topic_id):
  return get_value(f"/QuestDuration/{topic_id}", "cutoftime", 1750)


def get_repeat(topic_id):
  return get_value(f"/QuestDuration/{topic_id}", "repeat", 1)


# def log_me(msg, log_type):
#     # Emits the data using the standard logging module
#     logging.warning(msg)


def get_date(future_in=0):
  next_date = datetime.today() + timedelta(days=future_in)
  return next_date.strftime("%Y/%m/%d")


def to_update(topic_id):
  """
  """
  latest = get_value(f"/QuestDuration/{topic_id}", "latest", 1)
  repeat = get_value(f"/QuestDuration/{topic_id}", "repeat", 1)
  today = get_date()
  next_date = get_date(repeat)
  logme.info(f"{today=}  {next_date=}")
  # if next_date is already present then dont do anywhing

  val = get_value(f"/Topics/{topic_id}/{next_date}", "qid", False)
  logme.info(f"to do or not to do: {val=}")
  return next_date if not val else False


def get_fresh_quest(topic_id):
  """
  """
  key = ""
  ref = db.reference(f"/QuestionBank/{topic_id}")
  data = ref.order_by_child("used").equal_to(0).limit_to_first(1).get()
  logme.info(f"got the next free quest,{data=}")
  if data:
    key = list(data.keys())[0]
    #     logme.info(f"Adding {key=}")
    #     next_date = tomorrow()
    #     logme.info(f"{next_date=}")
    #     quest_ref = db.reference(f"/Topics/{topic}/{next_date}")
    #     quest_ref.set({
    #         "qid": key
    #     })

    # Now lets update the questionbank # Code working
    child = ref.child(key)
    child.update({
        "used": 1
    })
  return key


def use_quest(quest_id, topic_id, next_date):
  try:
    quest_ref = db.reference(f"/Topics/{topic_id}/{next_date}")
    quest_ref.set({
        "qid": quest_id
    })
    # lets update the latest
    ref = db.reference(f"/QuestDuration/{topic_id}")
    ref.update({
        "latest": next_date
    })

    return True
  except Exception as e:
    logme.error(e)
    return False


@sched.scheduled_job('cron', day_of_week='mon-fri', hour=1, minute=55)
def populate_quests():
  """
  Step 1: Get the next date for the quest based on `latest` and `repeat`
  Step 2. Do we need to populate next quest and skip if not
  3. if yes, then obtain the first unused quest for topic
  4. populate the quest with previous questdetails
  5. Update the quest as used.

  """
  logme.info("Lets start populating the quests for next valid date")
  # Lets find all the quests we have
  for topic_id in get_topics():
    logme.info(f"\nChecking {topic_id=} if it need updating")
    if(next_date:= to_update(topic_id)):
      """
      Lets update the quest
      """
      logme.info(
          f"lets updat the topic with quest for date: {next_date}")
      if (quest_id:= get_fresh_quest(topic_id)):
        logme.info(f"Found the quest: {quest_id=}")
        use_quest(quest_id, topic_id, next_date)


sched.start()

