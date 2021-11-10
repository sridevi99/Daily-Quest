"""."""

import os
import ast
import atexit
from functools import wraps
from datetime import datetime, timedelta
#from zoneinfo import ZoneInfo  # alternative to thirdparty pytz

# from apscheduler.schedulers.background import BackgroundScheduler
import flask
from flask import Flask, render_template, request

import firebase_admin
from firebase_admin import db
from firebase_admin import auth
from firebase_admin import credentials
import google.oauth2.id_token
from google.auth.transport import requests
from werkzeug.utils import redirect

from logger import GCPLogging


app = Flask(__name__)


CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
certs = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '').strip()
#certs = certs1.strip()

parsed_json = ast.literal_eval(str(certs))
cred = credentials.Certificate(parsed_json)
firebase_admin.initialize_app(cred, {
    'databaseURL':
    'https://dailyquest-9d678-default-rtdb.firebaseio.com/'
})

app.secret_key = os.getenv("secret_key")


logme = GCPLogging(parsed_json)
# Disable them in production
if os.getenv("dev") == "local":
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

firebase_request_adapter = requests.Request()


@app.before_request
def before_request():
    if 'DYNO' in os.environ:  # Only runs when on heroku
        logme.info(f"Headers: {request.headers=}")
        if request.url.startswith('http://') and request.headers.get(
                'X-Forwarded-Proto', "") == "http":
            url = request.url.replace('http://', 'https://', 1)
            code = 301

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


def create_subtopics(topic_id, subtopic):
    ref = db.reference(f"/Topic_List/{topic_id}/sub_topics")
    ref.push(subtopic)


def is_role(role):
    logme.info(f"{role} in is_role")
    return True if is_allowed(role) else False


def is_allowed(role):
    """."""
    flg, user_data = get_user_details()
    logme.info(f"in is_allowed: {flg=}\n{user_data=}")
    if not flg and not user_data:
        return False
    user_email = user_data.get('email', "")
    user_id = user_data.get('user_id', "")
    ref_url = f"/access_control_list/{role}"
    return (user_id, user_email) in db.reference(ref_url).get().items()


def need_role(role):
    def decorator(fun):
        @wraps(fun)
        def wrapper(*args, **kwargs):
            if is_allowed(role):
                return fun(*args, **kwargs)
            return flask.redirect('/')
        return wrapper
    return decorator


def auth_required(func):
    """."""
    def _inner_(*args):
        """."""
        user_data = ""
        try:
            id_token = request.cookies.get("token")
            logme.info(f"{id_token=}")
        except ValueError as ve:
            logme.error(f"{ve=}")
            id_token = None
        if id_token:
            try:
                while not user_data:
                    user_data = google.oauth2.id_token.verify_firebase_token(
                        id_token, firebase_request_adapter)
                result = func(user_data=user_data, *args)
                logme.info(f"{user_data=}")
                return result
            except Exception as error:
                logme.error(f"Failed in auth_required: {error=}")
                user_data = None
        logme.error(f"redirecting to logout as {id_token=} and {user_data=}")
        return redirect("/logout")

    # Renaming the function name:
    _inner_.__name__ = func.__name__
    return _inner_


# def get_topics():
#     logme.info("inside get_topics")
#     ref = db.reference("/QuestionBank")
#     logme.info("Lets get the topics from QuestionBank")
#     topics = tuple(ref.get('QuestionBank')[0].keys())
#     logme.info(f"Topics {topics=}")
#     return topics


def get_todays_quest(topic):
    logme.info("inside get_todays_quest")
    name = quest = None
    today = get_date()
    logme.info(f"Todays date: {today}")
    ref = db.reference(f"/Topics/{topic}/{today}")
    logme.info(f"2. Todays date: {today} - {ref=}")
    qid = ""
    if ref:
        logme.info("Lets start to find the qid from topics")
        logme.info(f"Lets get from  Topics/{topic}/{today} with {ref=}")
        qid = ref.get('qid')
        logme.info(f"{qid=} and {None not in qid}")
        if qid and None not in qid:
            qid = qid[0].get('qid') if ref else None
            logme.info(f"{qid=}..")
            url = f"/QuestionBank/{topic}/{qid}"
            logme.info(f"{url=}")
            ref = db.reference(url)
            if ref:
                logme.info(f"{ref=}")
                data = ref.get()
                logme.info(f"{data=}")
                if data and None not in data:
                    name = data.get("name", "")
                    quest = data.get("quest", "")
                logme.info(f">{name=}")
            logme.info(f"{name=},\n{quest=}\n{qid=}")
    logme.info(f"{qid=}, {name=}, {quest=}")
    return qid, name, quest


def get_latest_quest(topic_id):
    logme.info("inside get_todays_quest")
    name = quest = None
    # date = get_date()
    # logme.info(f"Todays date: {today}")
    past = 0
    while not (qid := get_value(f"/Topics/{topic_id}/{get_date(past)}", "qid", False)):
        past -= 1

    # Now lets find the quest details to display
    logme.info("Now lets find the quest details to display")
    url = f"/QuestionBank/{topic_id}/{qid}"
    name = get_value(url, "name", "")
    quest = get_value(url, "quest", "")
    return qid, name, quest, get_date(past)

    # ref = db.reference(f"/Topics/{topic}/{today}")
    # logme.info(f"2. Todays date: {today} - {ref=}")
    # qid = ""
    # if ref:
    #     logme.info("Lets start to find the qid from topics")
    #     logme.info(f"Lets get from  Topics/{topic}/{today} with {ref=}")
    #     qid = ref.get('qid')
    #     logme.info(f"{qid=} and {None not in qid}")
    #     if qid and None not in qid:
    #         qid = qid[0].get('qid') if ref else None
    #         logme.info(f"{qid=}..")
    #         url = f"/QuestionBank/{topic}/{qid}"
    #         logme.info(f"{url=}")
    #         ref = db.reference(url)
    #         if ref:
    #             logme.info(f"{ref=}")
    #             data = ref.get()
    #             logme.info(f"{data=}")
    #             if data and None not in data:
    #                 name = data.get("name", "")
    #                 quest = data.get("quest", "")
    #             logme.info(f">{name=}")
    #         logme.info(f"{name=},\n{quest=}\n{qid=}")
    # logme.info(f"{qid=}, {name=}, {quest=}")
    # return qid, name, quest


def get_solution(topic: str, qid: str) -> str:
    ref = db.reference(f"/QuestionBank/{topic}/{qid}")
    return ref.get() if ref else None


@app.route("/submit_solution", methods=['POST'])
@auth_required
def submit_solution(user_data=None):
    """."""
    logme.info(f"{user_data=}")
    proposed_solution = request.form['proposed_solution']
    topic, qid, quest_date = request.form['quest_date'].split("::")
    user_id = user_data.get("user_id", "")
    month, date = quest_date.rsplit("/", 1)
    url = f"/history/{topic}/{month}"
    ref = db.reference(url)
    ref.push({
        "date": date,
        "uid": user_id,
        "q_id": qid,
        "proposed": proposed_solution,
        "result": "Not Evaluated"  # Not Evaluated, Fail, Pass
    })

    return """<html><body>Thanks for Submitting the solution,
    click <a href='/'> me </a> to return back to home</body></html>"""


@app.route("/my_history", methods=["GET", "POST"])
@auth_required
def my_history(user_data=None):
    topics = get_topics()
    admin = is_role("admins")
    if request.method == 'POST':
        month = request.form.get("month")
        topic = request.form.get("topic")
        user_id = user_data.get("user_id", "")
        url = f"/history/{topic}/{month}"
        logme.info(f"{url=} -- {user_id=}")
        ref = db.reference(url)
        monthly_data = {}
        if ref.get():
            for key, value in ref.order_by_child(
                    'uid').equal_to(user_id).get().items():
                logme.info(f"{key=}\n{value=}")
                solution_data = get_solution(topic, value['q_id'])
                logme.info(f"{solution_data=}")
                value.update(solution_data)
                logme.info(f"updated {value=}")
                monthly_data[key] = value
        return render_template("history.html", admin=admin,
                               user_data=user_data,
                               data=monthly_data,
                               topics=topics)
    else:
        return render_template("history.html", user_data=user_data,
                               admin=admin, topics=topics, data={})


@app.route("/add_quest", methods=["GET", "POST"])
@need_role("admins")
@auth_required
def add_quest(user_data=None):
    admin = is_role("admins")
    if request.method == 'POST':
        topic = request.form.get("topic")
        name = request.form.get("name", "")
        quest = request.form.get("quest", "")
        solution = request.form.get("solution", "")
        logme.info(f"{topic=}\n{name=}\n{quest=}")
        ref = db.reference(f"/QuestionBank/{topic}")

        ref.push({'name': name.strip(), 'quest': quest.strip(), 'solution':
                  solution.strip(), "used": 0})
    topics = get_topics()
    return flask.render_template("add_quest.html", user_data=user_data,
                                 admin=admin, title="Enter New Quest",
                                 topics=topics)


@app.route("/todays_quest", methods=["GET", "POST"])
@auth_required
def todays_quest(user_data=None):
    admin = is_role("admins")
    logme.info(f"Reached todays_quest with {request.method=}")
    if request.method == 'POST':
        topic = request.form.get("topic")
        logme.info(f"today's {topic=}")
        # qid, name, quest = get_todays_quest(topic)
        qid, name, quest, date = get_latest_quest(topic)
        if all((qid,  name, quest)):
            logme.info(f"{qid=} -- {name=} -- {quest=}")
            return flask.render_template("todays_quest.html",
                                         title="Enter Daily Quest",
                                         quest_date=date, topic=topic,
                                         admin=admin, user_data=user_data,
                                         qid=qid, name=name, quest=quest)
        else:
            logme.info("Sorry no quest available")
            return "<html><body>Sorry, no new quest for today</body></html>"
    else:
        logme.info("user tried GET method for /todays_quest")
        return flask.redirect('/')


def get_value(url, key, default_value):
    ref = db.reference(f"/{url}")
    return data.get(key) if (data := ref.get()) else default_value


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


# def get_date():
#     """Returns date time for url format in firebase"""
#     return (datetime.now(ZoneInfo('Asia/Kolkata')) +
#             timedelta(hours=6, minutes=30)).strftime("%Y/%m/%d")


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
        if(next_date := to_update(topic_id)):
            """
            Lets update the quest
            """
            logme.info(
                f"lets updat the topic with quest for date: {next_date}")
            if quest_id := get_fresh_quest(topic_id):
                logme.info(f"Found the quest: {quest_id=}")
                use_quest(quest_id, topic_id, next_date)


# def get_next_free_quest():
#     """Use Push to add the questions else this will fail :("""
#     topics = get_topics()
#     logme.info(f"In get_next_free_quest: {topics}")
#     for topic in topics:
#         ref = db.reference(f"/QuestionBank/{topic}")
#         data = ref.order_by_child("used").equal_to(0).limit_to_first(1).get()
#         logme.info(f"{data=}")
#         if data:
#             key = list(data.keys())[0]
#             logme.info(f"Adding {key=}")
#             next_date = tomorrow()
#             logme.info(f"{next_date=}")
#             quest_ref = db.reference(f"/Topics/{topic}/{next_date}")
#             quest_ref.set({
#                 "qid": key
#             })

#             # Now lets update the questionbank
#             child = ref.child(key)
#             child.update({
#                 "used": 1
#             })


def schedule_quest():
    logme.info("Starting the logging")
    scheduler = BackgroundScheduler(timezone='Asia/Kolkata', daemon=True)
    scheduler.add_job(populate_quests,  'cron',
                      hour='09', minute='30', second="00")
    scheduler.start()
    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())


@app.route("/evaluate", methods=['POST'])
@need_role("admins")
@auth_required
def evaluation(user_data=None):
    #    topic = request.form.get("topic")
    month = request.form.get("selected_month")
    topic = request.form.get("selected_topic")
    logme.info(f"{month=}  {topic=}")
    logme.info(f"{request.form=}")
    url = f"/history/{topic}/{month}"
    for key in request.form:
        if key.startswith("-"):
            _url = f"{url}/{key}"
            child = db.reference(_url)
            logme.info(f"Updating child: {key} -> {request.form.get(key)=}")
            child.update({
                "result": request.form.get(key)
            })

    return flask.redirect('/eval')


@app.route("/eval", methods=['GET', 'POST'])
@need_role("admins")
@auth_required
def eval_quest(user_data=None):
    topics = get_topics()
    admin = is_role("admins")
    if request.method == 'POST':
        month = request.form.get("month")
        topic = request.form.get("topic")
        # user_id = user_data.get("user_id", "")
        url = f"/history/{topic}/{month}"
        # logme.info(f"{url=} -- {user_id=}")
        ref = db.reference(url)
        monthly_data = {}
        if ref.get():
            for key, value in ref.order_by_child('date').get().items():
                logme.info(f"{key=}\n{value=}")
                solution_data = get_solution(topic, value['q_id'])
                logme.info(f"{solution_data=}")
                value.update(solution_data)
                logme.info(f"updated {value=}")
                monthly_data[key] = value
        return render_template("evaluate.html",
                               user_data=user_data, month=month, topic=topic,
                               data=monthly_data, admin=admin,
                               topics=topics)
    else:
        return render_template("evaluate.html", user_data=user_data,
                               admin=admin, topics=topics, data={})


@app.route("/logout")
def logout():
    """."""
    logme.info(f"{flask.request.cookies=}")
    id_token = flask.request.cookies.get('token')
    try:
        if id_token:
            logme.info(f"{id_token=}")
            decoded_claims = google.oauth2.id_token.verify_firebase_token(
                id_token, firebase_request_adapter)
            # decoded_claims = auth.verify_session_cookie(session_cookie)

            auth.revoke_refresh_tokens(decoded_claims['sub'])
            response = flask.make_response(flask.redirect('/login'))
            response.set_cookie('token', "", expires=-1)
            return response
    except auth.InvalidSessionCookieError as error:
        logme.error(f"Error: {error}")
    except ValueError as ve:
        logme.error(f"Value Error {ve=}")
        response = flask.make_response(flask.redirect('/login'))
        response.set_cookie('token', "", expires=-1)
        return response
    return flask.redirect('/login')


@app.route("/", methods=["GET"])
@auth_required
def index(user_data=None):
    admin = is_role("admins")
    logme.info(f"1. {admin=}")
    if user_data:
        logme.info(">> Getting topics")
        topics = get_topics()

        logme.info(f"1. user: {user_data=}\n{topics=}")
        return flask.render_template("index.html", title="Daily Quest",
                                     admin=admin, user_data=user_data,
                                     topics=topics)
    return redirect("/logout")


@app.route("/login")
def login():
    # if  flask.request.cookies.get('token'):
    #     return redirect("/logout")
    return flask.render_template("login.html", title="Please Login")


def get_past_quests(topic, month):
    url = f"/history/{topic}/{month}"
    # Lets get details of every user for month of
    topic_ref = db.reference(url)
    solution = topic_ref.order_by_child("date").get()
    return solution


def main():
    logme.info("Inside main")
    # schedule_quest()

    if __name__ == '__main__':
        port = int(os.getenv('PORT', "5000"))
        app.run(host='0.0.0.0', port=port, debug=False)


main()
